# LocalRAG

[简体中文](README.md) | English

A local-first personal knowledge base built on RAG (Retrieval-Augmented Generation). It upgrades keyword search into semantic Q&A: upload documents, and the system automatically parses, chunks, and vectorizes them so you can ask questions in natural language and get answers with cited sources.

**Local-first**: your original documents and vector indexes never leave your machine — only sanitized retrieved snippets are sent to the cloud LLM you configure.

## Features

- **Multi-format ingestion**: PDF, Word, Excel, PPT, Markdown, TXT with automatic parsing and chunking
- **URL import**: single URL, batch import, and full-site crawling (sitemap)
- **Hybrid retrieval**: dense vectors (bge-small-zh) + BM25 keyword search fused via RRF, re-ranked locally by bge-reranker
- **LLM query rewriting**: rewrites each question into 2–3 variants to boost recall (toggleable)
- **Web search fallback**: automatically supplements results with DuckDuckGo when local snippets are insufficient (toggleable)
- **Knowledge base management**: multi-KB isolation, tagging, document search and status filters
- **Multi-turn conversations**: keeps the last 5 turns with streaming output (SSE)
- **Source citations**: answers cite retrieved sources; click to inspect original snippets
- **Deep thinking & image analysis**: supports thinking mode and image upload analysis

## Tech Stack

| Layer | Technology |
|----|------|
| Backend | Python 3.11 / FastAPI / LangChain / SQLAlchemy + MySQL |
| Vector store | ChromaDB (local) |
| Frontend | TypeScript + React / Vite / Ant Design |
| Embedding | BAAI/bge-small-zh-v1.5 (local CPU, ~90MB) |
| Reranker | BAAI/bge-reranker-v2-m3 (local) |
| LLM | Any OpenAI-compatible API — set base_url + api_key + model to use Qwen / DeepSeek / Moonshot / Ollama, etc. |
| Auth | JWT (python-jose + passlib/bcrypt) |
| Deployment | Docker Compose (backend + frontend/nginx + MySQL) |

## Architecture

```
Frontend (React+TS) --REST+SSE--> Backend (FastAPI) --> ChromaDB (vectors)
                                       |                    MySQL (metadata)
                                       |                    bge-small-zh (local embedding)
                                       |                    bge-reranker-v2-m3 (local reranker)
                                       v
                                  Cloud LLM API (Qwen/OpenAI)
```

## Quick Start

### Requirements

- Python 3.11+ (conda virtual environment recommended)
- Node.js 18+
- MySQL 8.0

### 1. Set up the backend

```bash
# Create and activate a virtual environment
conda create -n localrag python=3.11
conda activate localrag

# Install dependencies
cd backend
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
# Edit .env with your LLM API settings and MySQL connection info
```

On first startup the embedding model (bge-small-zh-v1.5) is downloaded automatically to `data/models/`.

### 3. Initialize the database

```bash
mysql -u root -p -e "CREATE DATABASE localrag CHARACTER SET utf8mb4;"
```

### 4. Start the backend

```bash
conda activate localrag
cd backend
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### 5. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 . On first use, switch to “Sign up” on the login page to create an account (registration is only open while the database has no users; for multiple accounts, insert rows into the users table manually or reset the database).

### Docker deployment (full stack)

```bash
docker-compose up --build
```

The frontend is served at http://localhost:80 by nginx, which reverse-proxies API calls to the backend.

## Retrieval Pipeline

```
User question → LLM query rewriting (2–3 variants)
             → per variant: vector(top 20) + BM25(top 20) → RRF fusion
             → merge & dedupe
             → bge-reranker fine-grained ranking
             → threshold filter (results with rerank_score < threshold are dropped)
             → top 5
```

Each stage can be toggled in the settings panel: `query_rewrite_enabled`, `hybrid_search`, `rerank_enabled`, `rerank_threshold`.

## Key Parameters

| Parameter | Default | Description |
|------|--------|------|
| chunk_size | 500 | Chunk size in characters |
| chunk_overlap | 50 | Overlap between chunks |
| top_k | 5 | Number of snippets returned |
| retrieval_top_k | 20 | Candidates per retrieval path |
| rerank_top_k | 5 | Final count after reranking |
| rerank_threshold | 1.0 | Reranker score threshold; lower scores are filtered out |
| query_rewrite_enabled | true | Enable LLM query rewriting |
| web_search_enabled | false | Enable web search fallback (DuckDuckGo) |
| temperature | 0.7 | LLM sampling temperature |
| max_tokens | 2048 | Max generation length |

Multi-turn chat: keeps the last 5 turns; history plus retrieved snippets are capped at 60% of the model context window.

## SSE Event Protocol

`POST /api/chat` streams Server-Sent Events in this order:

1. `event: thinking` → `{"status": "started|reasoning|completed", "message": "..."}` — deep-thinking / image-analysis progress
2. `event: token` → `{"content": "..."}` — streamed answer tokens
3. `event: sources` → `{"sources": [...]}` — citation sources
4. `event: done` → `{"conversation_id": ...}` — completion marker
5. `event: error` → `{"message": "..."}` — error details

## Project Structure

```
backend/
  app/
    api/          # FastAPI routes (documents, chat, settings, knowledge_bases, auth, export, tags)
    auth.py       # JWT auth module
    services/     # Business logic (document_service, rag_service, llm_service, query_rewrite, web_search_service)
    core/         # Infrastructure (embedding, vectorstore, bm25_search, reranker, prompts, web_fetcher)
    models.py     # SQLAlchemy models (Document, Conversation, Message)
  tests/          # pytest suite
frontend/
  src/
    components/   # React components (ChatPanel, DocumentList, DocumentPreviewPanel, SourcePanel, Sidebar, SettingsPanel)
    services/     # API clients and SSE wrappers
    types/        # TypeScript types
data/             # Local data (chromadb/, uploads/, models/)
test_docs/        # Sample & evaluation corpus (24 files: Markdown/TXT/PDF/DOCX/XLSX/CSV)
docs/             # Design docs and quality-program records
.github/workflows/quality-gates.yml   # CI: five quality gates
```

## Testing

```bash
cd backend
conda run -n localrag python -m pytest tests/ -v
```

## Security Notes

- Never commit `.env` or any file containing real secrets (already excluded in `.gitignore`)
- All local configuration is done by copying `.env.example` to `.env`
- Original documents and vector indexes stay local; the cloud LLM only receives sanitized retrieved snippets

## Documentation

- Overall design: `docs/superpowers/specs/2026-06-11-localrag-design.md`
- Quality hardening design: `docs/superpowers/specs/2026-06-13-quality-hardening-design.md`
- Web search & reranker fix design: `docs/superpowers/specs/2026-06-17-web-search-reranker-fix-design.md`
- Stabilization design: `docs/superpowers/specs/2026-06-19-stabilization-design.md`
- Quality program design (frozen, Phases 0–4): `docs/superpowers/specs/2026-08-02-localrag-quality-program-design.md`
- Phase 1 execution handbook: `docs/quality/phase-1-plan.md` (Chinese; the task specs are language-independent code/paths)

## Contributing

Contributions of every kind are welcome: bug reports, feature ideas, documentation, and code PRs. Before starting, please read [CONTRIBUTING](CONTRIBUTING.en.md) and our [Code of Conduct](CODE_OF_CONDUCT.en.md); use the Issue templates for bugs and feature requests. Please do not disclose security vulnerabilities publicly — see [SECURITY](SECURITY.en.md).

## License

Released under the [MIT](LICENSE) license.
