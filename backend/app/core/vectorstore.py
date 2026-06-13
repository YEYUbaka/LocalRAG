import chromadb
from app.config import settings
from app.core.embedding import embed_texts

_client: chromadb.ClientAPI | None = None
_collection: chromadb.Collection | None = None

COLLECTION_NAME = "localrag"


def get_chroma_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        settings.chromadb_dir.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(settings.chromadb_dir))
    return _client


def get_collection() -> chromadb.Collection:
    global _collection
    if _collection is None:
        client = get_chroma_client()
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def add_documents(doc_id: int, texts: list[str], metadatas: list[dict]) -> None:
    collection = get_collection()
    embeddings = embed_texts(texts)
    ids = [f"doc_{doc_id}_chunk_{i}" for i in range(len(texts))]
    metadata_with_doc = [{**m, "doc_id": doc_id} for m in metadatas]
    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadata_with_doc,
    )


def vector_search(query: str, top_k: int | None = None) -> list[dict]:
    """Pure vector search using ChromaDB."""
    collection = get_collection()
    if collection.count() == 0:
        return []

    k = top_k or settings.retrieval_top_k
    query_embedding = embed_texts([query])
    results = collection.query(
        query_embeddings=query_embedding,
        n_results=k,
        include=["documents", "metadatas", "distances"],
    )

    if not results["ids"][0]:
        return []

    items = []
    for i in range(len(results["ids"][0])):
        dist = results["distances"][0][i]
        if dist > settings.similarity_threshold:
            continue
        items.append({
            "id": results["ids"][0][i],
            "document": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "distance": dist,
        })
    return items


def rrf_fusion(
    vector_results: list[dict],
    bm25_results: list[dict],
    vector_weight: float = 0.5,
    bm25_weight: float = 0.5,
    k: int = 60,
    top_n: int = 5,
) -> list[dict]:
    """Reciprocal Rank Fusion of vector and BM25 results."""
    doc_lookup: dict[str, dict] = {}
    for item in vector_results:
        doc_lookup[item["id"]] = item

    scores: dict[str, float] = {}
    for rank, item in enumerate(vector_results):
        doc_id = item["id"]
        scores[doc_id] = scores.get(doc_id, 0) + vector_weight / (k + rank)

    for rank, item in enumerate(bm25_results):
        doc_id = item["id"]
        if doc_id not in doc_lookup:
            doc_lookup[doc_id] = {
                "id": doc_id,
                "document": item["document"],
                "metadata": {"doc_id": item.get("doc_id")},
            }
        scores[doc_id] = scores.get(doc_id, 0) + bm25_weight / (k + rank)

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_n]
    return [doc_lookup[doc_id] for doc_id, _ in ranked if doc_id in doc_lookup]


def hybrid_search(query: str) -> list[dict]:
    """Hybrid search: vector + BM25 with RRF fusion, or pure vector if hybrid is disabled."""
    if not settings.hybrid_search:
        return vector_search(query, top_k=settings.rerank_top_k)

    from app.core.bm25_search import bm25_search

    retrieval_k = settings.retrieval_top_k
    vector_results = vector_search(query, top_k=retrieval_k)
    bm25_results = bm25_search(query, top_k=retrieval_k)

    if not bm25_results:
        return vector_results[:settings.rerank_top_k]
    if not vector_results:
        return []

    vector_weight = 1 - settings.bm25_weight
    return rrf_fusion(
        vector_results,
        bm25_results,
        vector_weight=vector_weight,
        bm25_weight=settings.bm25_weight,
        top_n=settings.rerank_top_k,
    )


def search(query: str, top_k: int | None = None) -> list[dict]:
    """Main search entry point. Uses hybrid_search when enabled."""
    if top_k is not None:
        return vector_search(query, top_k=top_k)
    return hybrid_search(query)


def delete_by_doc_id(doc_id: int) -> None:
    collection = get_collection()
    collection.delete(where={"doc_id": doc_id})
