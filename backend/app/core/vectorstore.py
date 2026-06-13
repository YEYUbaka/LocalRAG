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


def search(query: str, top_k: int | None = None) -> list[dict]:
    collection = get_collection()
    if collection.count() == 0:
        return []

    k = top_k or settings.top_k
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


def delete_by_doc_id(doc_id: int) -> None:
    collection = get_collection()
    collection.delete(where={"doc_id": doc_id})
