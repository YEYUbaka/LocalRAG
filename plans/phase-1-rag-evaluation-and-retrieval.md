# Phase 1 RAG Evaluation and Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立可复现的 Golden Set 评测体系、稳定 Canonical Chunk Repository，以及 Dense/Sparse/多查询/Reranker 共用身份的统一检索链路，并以不可退化门禁决定配置是否可推广。

**Architecture:** 先冻结 `GoldenCase`、`ChunkRecord`、`SearchCandidate` 与 run manifest 契约，再将 MySQL canonical chunks 设为 Dense 和 Sparse 索引的共同事实来源。原查询与改写查询只做候选召回，统一 fusion 后以原问题执行一次 rerank；评测 CLI 对每次运行保存完整配置指纹并与已接受 baseline 比较。

**Tech Stack:** Python 3.11、pytest、Pydantic、SQLAlchemy/MySQL、Alembic、ChromaDB、rank-bm25/jieba、SentenceTransformers、FlagEmbedding、JSONL。

## Global Constraints

- 冻结设计：`E:\AI_projects\LocalRAG\docs\superpowers\specs\2026-08-02-localrag-quality-program-design.md`，实现不得改变其中的 Domain 契约语义。
- 产品边界是“高质量、中文优化、隐私优先的个人本地知识库”；不引入 GraphRAG、Agent、Workflow、MCP、Redis/Celery、外部向量数据库或多 OCR 后端。
- Python 只使用 `localrag` conda 环境；所有命令从 `E:\AI_projects\LocalRAG` 执行，不使用 base 或 Windows Store Python。
- 所有新行为使用 TDD：先提交会因缺失行为失败的定向测试，再写最小实现，再运行定向与相关回归。
- `backend\app\domain\` 归 Contract Agent，`backend\app\models.py` 与 `backend\alembic\` 归 Data Agent，`backend\app\main.py`、`backend\requirements.txt` 与 CI 汇总归 Integrator；其他 Agent 不得修改这些文件。
- `backend\app\config.py`、`backend\app\services\document_service.py`、`backend\app\services\rag_service.py`、`backend\app\core\vectorstore.py` 是冲突热点；同一时刻只能有一个明确 Owner 修改。
- 新 schema 只做 additive migration；旧向量、旧 BM25 和旧检索路径保留到 feature flag 切换成功，禁止本阶段删除历史字段或索引。
- 每次任务提交只包含本任务拥有的文件；不得回退或整理其他 Agent 的未提交变更。
- Golden Set 不得包含真实用户私密文档、凭据或对话；所有固定语料来自 `test_docs` 或经审查的合成样本。

---

## File and Contract Map

| Area | Owner | Files | Responsibility |
|---|---|---|---|
| Eval contracts | RAG Agent | `E:\AI_projects\LocalRAG\backend\evals\schema.py`, `dataset.py` | Golden JSONL 的加载、验证与版本约束 |
| Metrics/manifest | RAG Agent | `E:\AI_projects\LocalRAG\backend\evals\metrics.py`, `manifest.py`, `report.py` | 确定性指标、运行指纹、报告与比较 |
| Eval CLI | RAG Agent | `E:\AI_projects\LocalRAG\backend\evals\cli.py` | `validate/retrieval/compare/accept` 命令 |
| Domain contracts | Contract Agent | `E:\AI_projects\LocalRAG\backend\app\domain\chunks.py`, `retrieval.py` | 稳定 chunk/provenance/candidate 类型 |
| Persistence | Data Agent | `E:\AI_projects\LocalRAG\backend\app\models.py`, `E:\AI_projects\LocalRAG\backend\alembic\versions\*canonical_chunks*.py` | Canonical chunk 与 index manifest 持久化 |
| Repositories | RAG Agent | `E:\AI_projects\LocalRAG\backend\app\application\retrieval\chunk_repository.py`, `index_manifest_repository.py` | Domain 与 SQLAlchemy 隔离 |
| Index adapters | RAG Agent | `E:\AI_projects\LocalRAG\backend\app\core\vectorstore.py`, `bm25_search.py` | 以 canonical chunk ID upsert/search/rebuild |
| Retrieval orchestration | RAG Agent | `E:\AI_projects\LocalRAG\backend\app\application\retrieval\pipeline.py`, `fusion.py` | 多查询统一融合与单次 rerank |
| Integration | Integrator | `E:\AI_projects\LocalRAG\backend\app\services\rag_service.py`, `config.py`, CI | feature flag、旧路径兼容与阶段门禁 |

### Frozen interfaces produced by this phase

```python
@dataclass(frozen=True)
class ChunkProvenance:
    document_id: int
    document_key: str
    document_version: str
    parent_chunk_id: str | None
    block_ids: tuple[str, ...]
    page_start: int | None
    page_end: int | None
    char_start: int
    char_end: int

@dataclass(frozen=True)
class ChunkRecord:
    chunk_id: str
    scope: TenantScope
    text: str
    ordinal: int
    chunker_version: str
    content_hash: str
    provenance: ChunkProvenance

@dataclass(frozen=True)
class SearchCandidate:
    chunk_id: str
    dense_score: float | None
    sparse_score: float | None
    fusion_score: float
    rerank_score: float | None
    provenance: ChunkProvenance
```

```python
class ChunkRepository(Protocol):
    def replace_document(self, scope: TenantScope, document_id: int, chunks: Sequence[ChunkRecord]) -> None: ...
    def get(self, scope: TenantScope, chunk_id: str) -> ChunkRecord | None: ...
    def list_document(self, scope: TenantScope, document_id: int) -> list[ChunkRecord]: ...
    def iter_scope(self, scope: TenantScope) -> Iterator[ChunkRecord]: ...
    def delete_document(self, scope: TenantScope, document_id: int) -> None: ...
```

## Task 1: Golden Set Schema and Dataset Validation

**Files:**
- Create: `E:\AI_projects\LocalRAG\backend\evals\__init__.py`
- Create: `E:\AI_projects\LocalRAG\backend\evals\schema.py`
- Create: `E:\AI_projects\LocalRAG\backend\evals\dataset.py`
- Create: `E:\AI_projects\LocalRAG\backend\tests\evals\test_dataset.py`
- Create: `E:\AI_projects\LocalRAG\backend\evals\golden\v1.jsonl`

**Interfaces:**
- Consumes: files under `E:\AI_projects\LocalRAG\test_docs` and the frozen minimum category counts.
- Produces: `GoldenCase`, `Qrel`, `EvidenceLocator`, `load_dataset(path) -> list[GoldenCase]`, `validate_distribution(cases) -> DistributionReport`.

- [ ] **Step 1: Write failing schema and distribution tests**

```python
def test_rejects_answerable_case_without_qrels(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"case_id":"x","dataset_version":"v1","corpus_revision":"r1","kb_key":"k","query":"q","language":"zh-CN","category":"fact","difficulty":"easy","answerability":"answerable","expected_facts":[],"qrels":[],"tags":[]}\n', encoding="utf-8")
    with pytest.raises(DatasetValidationError, match="answerable.*qrels"):
        load_dataset(path)

def test_v1_distribution_requires_120_cases(valid_case_factory):
    cases = valid_case_factory.fact(55) + valid_case_factory.multi(15) + valid_case_factory.exact(15) + valid_case_factory.ocr_table(15) + valid_case_factory.unanswerable(20)
    report = validate_distribution(cases)
    assert report.total == 120
    assert report.is_valid
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `conda run -n localrag python -m pytest E:\AI_projects\LocalRAG\backend\tests\evals\test_dataset.py -v`

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'evals'`.

- [ ] **Step 3: Implement strict Pydantic models and JSONL loader**

Implement discriminated `answerability` values `answerable|unanswerable`; require answerable cases to contain at least one relevance `1..3` qrel and one required fact; require each qrel locator to contain `document_key`, `block_id`, zero-based `page_index`, `char_start`, `char_end`, and non-empty `quote`; reject duplicate `case_id` and invalid spans. `validate_distribution` must enforce exactly the frozen lower bounds: fact 55, multi-fragment 15, exact-term 15, OCR/table 15, unanswerable 20, total at least 120.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `conda run -n localrag python -m pytest E:\AI_projects\LocalRAG\backend\tests\evals\test_dataset.py -v`

Expected: PASS; invalid JSONL reports line number and field path.

- [ ] **Step 5: Add the reviewed v1 annotation set**

Create 120 records using stable filenames/content hashes from `test_docs`; every qrel must be verified against the checked-in corpus, unanswerable cases must have empty qrels and at least one `forbidden_claim`, and no case may contain credentials or user data. Run the distribution validator before review; annotation review samples every OCR/table case and 20% of all other cases.

- [ ] **Step 6: Commit**

```powershell
git -C E:\AI_projects\LocalRAG add backend/evals backend/tests/evals/test_dataset.py
git -C E:\AI_projects\LocalRAG commit -m "test: add versioned rag golden set schema"
```

## Task 2: Deterministic Metrics and Immutable Run Manifest

**Files:**
- Create: `E:\AI_projects\LocalRAG\backend\evals\metrics.py`
- Create: `E:\AI_projects\LocalRAG\backend\evals\manifest.py`
- Create: `E:\AI_projects\LocalRAG\backend\evals\report.py`
- Create: `E:\AI_projects\LocalRAG\backend\tests\evals\test_metrics.py`
- Create: `E:\AI_projects\LocalRAG\backend\tests\evals\test_manifest.py`

**Interfaces:**
- Consumes: `list[GoldenCase]`, ranked `chunk_id`/qrel relevance results, elapsed stage timings, explicit model/config descriptors.
- Produces: `recall_at`, `mrr_at`, `ndcg_at`, `exact_term_recall_at`, `RunManifest.create(...)`, `EvaluationReport`, canonical JSON serialization and SHA-256 run ID.

- [ ] **Step 1: Write metric edge-case tests**

```python
def test_rank_metrics_use_stable_qrel_identity():
    ranked = ["c3", "c1", "c2"]
    qrels = {"c1": 3, "c2": 1}
    assert recall_at(ranked, qrels, 2) == pytest.approx(0.5)
    assert mrr_at(ranked, qrels, 10) == pytest.approx(0.5)
    assert ndcg_at(ranked, qrels, 3) == pytest.approx(0.6590018)

def test_manifest_hash_changes_when_embedding_changes(base_manifest):
    changed = replace(base_manifest, embedding_model="other-model")
    assert base_manifest.run_id != changed.run_id
```

- [ ] **Step 2: Verify RED**

Run: `conda run -n localrag python -m pytest E:\AI_projects\LocalRAG\backend\tests\evals\test_metrics.py E:\AI_projects\LocalRAG\backend\tests\evals\test_manifest.py -v`

Expected: FAIL because metric and manifest modules do not exist.

- [ ] **Step 3: Implement metrics and manifest**

Use zero-based ranked lists but conventional rank `index + 1` in MRR/DCG. The manifest must require corpus hash, dataset hash, git SHA, parser/OCR/chunker/embedding/tokenizer/reranker/rewrite versions, all top-k/weights, hardware label, warm/cold flag, creation timestamp, and stage latency summary. Hash canonical JSON with sorted keys; do not read mutable global settings inside metric functions.

- [ ] **Step 4: Verify GREEN and determinism**

Run: `conda run -n localrag python -m pytest E:\AI_projects\LocalRAG\backend\tests\evals\test_metrics.py E:\AI_projects\LocalRAG\backend\tests\evals\test_manifest.py -v`

Expected: PASS twice with byte-identical report JSON except the explicitly supplied timestamp.

- [ ] **Step 5: Commit**

```powershell
git -C E:\AI_projects\LocalRAG add backend/evals backend/tests/evals
git -C E:\AI_projects\LocalRAG commit -m "feat: add deterministic rag metrics and manifests"
```

## Task 3: Evaluation CLI and Baseline Comparison Contract

**Files:**
- Create: `E:\AI_projects\LocalRAG\backend\evals\cli.py`
- Create: `E:\AI_projects\LocalRAG\backend\tests\evals\test_cli.py`
- Create: `E:\AI_projects\LocalRAG\backend\evals\thresholds.json`

**Interfaces:**
- Consumes: Tasks 1–2 and a retrieval callback `retrieve(case: GoldenCase) -> RetrievalObservation`.
- Produces: exit-code-stable commands `validate`, `retrieval`, `compare`, `accept`; candidate reports under `data\evals\runs`, accepted pointer under `data\evals\accepted.json`.

- [ ] **Step 1: Write failing CLI tests**

```python
def test_compare_fails_on_quality_regression(cli_runner, baseline_report, regressed_report):
    result = cli_runner("compare", "--baseline", baseline_report, "--candidate", regressed_report, "--fail-on-regression")
    assert result.exit_code == 2
    assert "Recall@20" in result.stdout

def test_accept_requires_passing_candidate(cli_runner, regressed_report):
    result = cli_runner("accept", "--candidate", regressed_report)
    assert result.exit_code == 2
```

- [ ] **Step 2: Verify RED**

Run: `conda run -n localrag python -m pytest E:\AI_projects\LocalRAG\backend\tests\evals\test_cli.py -v`

Expected: FAIL because `evals.cli` does not exist.

- [ ] **Step 3: Implement commands and fixed thresholds**

Write `thresholds.json` with `recall_at_20: 0.90`, `mrr_at_10: 0.70`, `ndcg_at_10: 0.75`, `rerank_recall_at_5: 0.85`, `exact_term_recall_at_20: 0.95`; comparison additionally rejects any accepted metric drop greater than `0.01` and retrieval p95 increase greater than `20%`. `compare --candidate X --thresholds Y` performs the initial absolute gate when no baseline exists; adding `--baseline B` also applies non-regression checks. Exit codes: `0` pass, `1` invalid input/runtime error, `2` quality gate failure. `accept --candidate X --output Y` first performs the absolute gate, then copies the immutable report, writes its SHA-256, and atomically updates `data\evals\accepted.json`.

- [ ] **Step 4: Verify GREEN**

Run: `conda run -n localrag python -m pytest E:\AI_projects\LocalRAG\backend\tests\evals\test_cli.py -v`

Expected: PASS and all four commands expose `--help` without importing Chroma or loading ML models.

- [ ] **Step 5: Commit**

```powershell
git -C E:\AI_projects\LocalRAG add backend/evals backend/tests/evals/test_cli.py
git -C E:\AI_projects\LocalRAG commit -m "feat: add reproducible rag evaluation cli"
```

## Task 4: Stable Chunk Contracts and Canonical Repository

**Files:**
- Create (Contract Agent): `E:\AI_projects\LocalRAG\backend\app\domain\scope.py`
- Create (Contract Agent): `E:\AI_projects\LocalRAG\backend\app\domain\chunks.py`
- Create (Contract Agent): `E:\AI_projects\LocalRAG\backend\app\domain\retrieval.py`
- Modify (Data Agent): `E:\AI_projects\LocalRAG\backend\app\models.py`
- Create (Data Agent): `E:\AI_projects\LocalRAG\backend\alembic\versions\20260802_01_add_canonical_chunks.py`
- Create: `E:\AI_projects\LocalRAG\backend\app\application\retrieval\chunk_repository.py`
- Create: `E:\AI_projects\LocalRAG\backend\tests\test_chunk_repository.py`

**Interfaces:**
- Consumes: frozen `TenantScope` and ChunkRecord shapes in this plan.
- Produces: stable `make_chunk_id(...)`, `SqlChunkRepository` implementing the protocol in the File and Contract Map, additive `canonical_chunks` and `index_manifests` tables.

- [ ] **Step 1: Write contract and tenant-isolation tests**

```python
def test_chunk_id_is_stable_and_version_sensitive():
    first = make_chunk_id("doc-key", "v1", "pc-v1", 3, "sha256:text")
    assert first == make_chunk_id("doc-key", "v1", "pc-v1", 3, "sha256:text")
    assert first != make_chunk_id("doc-key", "v2", "pc-v1", 3, "sha256:text")

def test_repository_never_returns_other_owner(repository, chunk_for):
    repository.replace_document(TenantScope(1, 7), 9, [chunk_for(1, 7, 9)])
    assert repository.get(TenantScope(2, 7), chunk_for(1, 7, 9).chunk_id) is None
```

- [ ] **Step 2: Verify RED**

Run: `conda run -n localrag python -m pytest E:\AI_projects\LocalRAG\backend\tests\test_chunk_repository.py -v`

Expected: FAIL because domain contracts and repository are absent.

- [ ] **Step 3: Implement deterministic identity and repository**

`make_chunk_id` returns `chk_` plus the first 32 hexadecimal characters of SHA-256 over UTF-8 fields joined with ASCII unit separator. Store `owner_id`, `kb_id`, `document_id`, `document_key`, `document_version`, `chunk_id`, `parent_chunk_id`, ordinal, text, content hash, chunker version and JSON provenance; unique keys are `(owner_id, kb_id, chunk_id)` and `(owner_id, kb_id, document_id, ordinal, chunker_version)`. `replace_document` performs a transaction and never deletes another scope.

- [ ] **Step 4: Add and verify additive Alembic migration**

Run: `conda run -n localrag alembic -c E:\AI_projects\LocalRAG\backend\alembic.ini upgrade head`

Expected: PASS; existing `documents`, Chroma files and BM25 state remain untouched.

- [ ] **Step 5: Verify GREEN**

Run: `conda run -n localrag python -m pytest E:\AI_projects\LocalRAG\backend\tests\test_chunk_repository.py -v`

Expected: PASS including same-KB/different-user isolation, idempotent replacement and rollback-on-error cases.

- [ ] **Step 6: Commit by owner**

```powershell
git -C E:\AI_projects\LocalRAG add backend/app/domain backend/app/application/retrieval/chunk_repository.py backend/app/models.py backend/alembic backend/tests/test_chunk_repository.py
git -C E:\AI_projects\LocalRAG commit -m "feat: add stable canonical chunk repository"
```

## Task 5: Dense and Sparse Index Identity Consistency

**Files:**
- Modify: `E:\AI_projects\LocalRAG\backend\app\core\vectorstore.py`
- Modify: `E:\AI_projects\LocalRAG\backend\app\core\bm25_search.py`
- Create: `E:\AI_projects\LocalRAG\backend\app\application\retrieval\index_service.py`
- Create: `E:\AI_projects\LocalRAG\backend\tests\test_index_consistency.py`
- Create: `E:\AI_projects\LocalRAG\backend\tests\integration\test_index_restart_consistency.py`

**Interfaces:**
- Consumes: `ChunkRepository.iter_scope`, stable `ChunkRecord.chunk_id`, `TenantScope`.
- Produces: `IndexService.upsert_document(scope, chunks)`, `delete_document(scope, document_id)`, `rebuild_scope(scope, manifest)`, and both adapters returning the same chunk IDs.

- [ ] **Step 1: Write real ID and BM25-only regression tests**

```python
def test_dense_and_sparse_return_same_chunk_id(indexed_chunk, dense, sparse):
    assert dense.search(indexed_chunk.scope, "专有词", 20)[0].chunk_id == indexed_chunk.chunk_id
    assert sparse.search(indexed_chunk.scope, "专有词", 20)[0].chunk_id == indexed_chunk.chunk_id

def test_sparse_hit_survives_empty_dense(index_service, scope):
    candidates = index_service.retrieve(scope, "ZX-991", dense_results=[], sparse_results=[sparse_hit("c1")])
    assert [item.chunk_id for item in candidates] == ["c1"]
```

- [ ] **Step 2: Verify RED against the existing global-corpus BM25 ID**

Run: `conda run -n localrag python -m pytest E:\AI_projects\LocalRAG\backend\tests\test_index_consistency.py -v`

Expected: FAIL showing BM25 ID differs from the canonical chunk ID or sparse-only result is empty.

- [ ] **Step 3: Implement scope-aware upsert and rebuild**

Chroma metadata must include `owner_id`, `kb_id`, `document_id`, `document_version`, `chunk_id`. Sparse corpus records store the supplied canonical ID rather than `_corpus` index. Both search methods require `TenantScope`; no adapter accepts a bare `kb_id`. Remove the pre-fusion cosine-distance filter from coarse retrieval. Rebuild only from committed canonical chunks and record manifest compatibility before switching the active generation.

- [ ] **Step 4: Verify restart consistency**

Run: `conda run -n localrag python -m pytest E:\AI_projects\LocalRAG\backend\tests\test_index_consistency.py E:\AI_projects\LocalRAG\backend\tests\integration\test_index_restart_consistency.py -v`

Expected: PASS; before/after restart top-20 ID set equality is `1.0`, sparse-only and dense-only results both survive, and cross-scope results are empty.

- [ ] **Step 5: Commit**

```powershell
git -C E:\AI_projects\LocalRAG add backend/app/core/vectorstore.py backend/app/core/bm25_search.py backend/app/application/retrieval/index_service.py backend/tests/test_index_consistency.py backend/tests/integration/test_index_restart_consistency.py
git -C E:\AI_projects\LocalRAG commit -m "fix: unify dense and sparse chunk identity"
```

## Task 6: Unified Multi-query Fusion and Single-pass Reranking

**Files:**
- Create: `E:\AI_projects\LocalRAG\backend\app\application\retrieval\fusion.py`
- Create: `E:\AI_projects\LocalRAG\backend\app\application\retrieval\pipeline.py`
- Modify: `E:\AI_projects\LocalRAG\backend\app\services\query_rewrite.py`
- Create: `E:\AI_projects\LocalRAG\backend\tests\test_retrieval_pipeline.py`

**Interfaces:**
- Consumes: `TenantScope`, adapters from Task 5, `rewrite_query(question) -> list[str]`, `rerank(original_question, texts) -> list[float]`.
- Produces: `RetrievalPipeline.retrieve(scope, question, config) -> RetrievalResult`; `RetrievalResult` includes candidates and stage timings.

- [ ] **Step 1: Write ordering and call-count tests**

```python
async def test_rewrites_fuse_before_one_original_query_rerank(pipeline, reranker):
    result = await pipeline.retrieve(SCOPE, "原问题", CONFIG)
    reranker.assert_called_once()
    assert reranker.call_args.args[0] == "原问题"
    assert result.candidates[0].chunk_id == "shared-hit"

async def test_rewrite_failure_keeps_original_query(pipeline_with_failed_rewriter):
    result = await pipeline_with_failed_rewriter.retrieve(SCOPE, "原问题", CONFIG)
    assert result.query_plan.queries == ("原问题",)
```

- [ ] **Step 2: Verify RED**

Run: `conda run -n localrag python -m pytest E:\AI_projects\LocalRAG\backend\tests\test_retrieval_pipeline.py -v`

Expected: FAIL because current code reranks separately per rewritten query and truncates by query order.

- [ ] **Step 3: Implement deterministic query plan and fusion**

Normalize and deduplicate rewrites while always keeping the original first. For every query retrieve dense and sparse top-20 without a relevance threshold. Accumulate weighted RRF using rank `1..N`, key solely by canonical chunk ID, and retain dense/sparse scores plus contributing queries in trace metadata. Deduplicate to top-20, fetch canonical text once, call reranker exactly once with the original question, then return top-5. Ties sort by `fusion_score`, then `chunk_id` for repeatability.

- [ ] **Step 4: Verify GREEN and existing regressions**

Run: `conda run -n localrag python -m pytest E:\AI_projects\LocalRAG\backend\tests\test_retrieval_pipeline.py E:\AI_projects\LocalRAG\backend\tests\test_hybrid_search.py E:\AI_projects\LocalRAG\backend\tests\test_query_rewrite.py -v`

Expected: PASS; reranker call count is one and BM25-only candidates remain present.

- [ ] **Step 5: Commit**

```powershell
git -C E:\AI_projects\LocalRAG add backend/app/application/retrieval backend/app/services/query_rewrite.py backend/tests/test_retrieval_pipeline.py
git -C E:\AI_projects\LocalRAG commit -m "feat: unify multi-query retrieval and reranking"
```

## Task 7: Feature-flagged RAG Service Integration

**Files:**
- Modify (Integrator): `E:\AI_projects\LocalRAG\backend\app\config.py`
- Modify (Integrator): `E:\AI_projects\LocalRAG\backend\app\services\rag_service.py`
- Modify (Integrator): `E:\AI_projects\LocalRAG\backend\app\services\document_service.py`
- Create: `E:\AI_projects\LocalRAG\backend\tests\test_retrieval_integration.py`

**Interfaces:**
- Consumes: `RetrievalPipeline`, `IndexService`, legacy `hybrid_search` fallback.
- Produces: persisted setting `retrieval_v2_enabled: bool = False`; ingestion dual-writes canonical chunks/indexes while legacy path remains readable.

- [ ] **Step 1: Write flag and fallback tests**

```python
async def test_v2_flag_uses_tenant_scoped_pipeline(service, settings, pipeline):
    settings.retrieval_v2_enabled = True
    await service.retrieve(question="q", user_id=4, kb_id=7)
    pipeline.retrieve.assert_awaited_once_with(TenantScope(4, 7), "q", ANY)

async def test_v2_failure_falls_back_without_deleting_v1(service, settings, pipeline, legacy):
    settings.retrieval_v2_enabled = True
    pipeline.retrieve.side_effect = IndexManifestMismatch("stale")
    assert await service.retrieve(question="q", user_id=4, kb_id=7) == legacy.results
```

- [ ] **Step 2: Verify RED**

Run: `conda run -n localrag python -m pytest E:\AI_projects\LocalRAG\backend\tests\test_retrieval_integration.py -v`

Expected: FAIL because `retrieval_v2_enabled` and the scoped integration do not exist.

- [ ] **Step 3: Integrate without removing V1**

Add only an additive flag defaulting false. Require `user_id` and `kb_id` before V2 retrieval. During document processing persist canonical chunks first, commit, then upsert both indexes; failures leave document retryable and never mark an incomplete index generation active. Log `request_id`, manifest ID and stage timings, but never log source text or API keys.

- [ ] **Step 4: Verify GREEN and service regression**

Run: `conda run -n localrag python -m pytest E:\AI_projects\LocalRAG\backend\tests\test_retrieval_integration.py E:\AI_projects\LocalRAG\backend\tests\test_rag_service.py E:\AI_projects\LocalRAG\backend\tests\test_document_service.py -v`

Expected: PASS with the default flag exercising unchanged V1 behavior and enabled flag enforcing owner plus KB scope.

- [ ] **Step 5: Commit**

```powershell
git -C E:\AI_projects\LocalRAG add backend/app/config.py backend/app/services/rag_service.py backend/app/services/document_service.py backend/tests/test_retrieval_integration.py
git -C E:\AI_projects\LocalRAG commit -m "feat: integrate tenant-scoped retrieval v2"
```

## Task 8: Golden Retrieval Baseline and Non-regression Gate

**Files:**
- Create: `E:\AI_projects\LocalRAG\backend\evals\retrieval_runner.py`
- Create: `E:\AI_projects\LocalRAG\backend\tests\evals\test_retrieval_runner.py`
- Create: `E:\AI_projects\LocalRAG\backend\evals\baselines\v1-retrieval.json`
- Modify (QA/Infra Agent): repository CI workflow owning backend quality gates.

**Interfaces:**
- Consumes: Tasks 1–7, frozen v1 corpus and `RetrievalPipeline`.
- Produces: case-level observations, aggregate accepted baseline and CI comparison result.

- [ ] **Step 1: Write runner isolation and manifest tests**

```python
def test_runner_records_every_case_and_stage(fake_pipeline, golden_cases):
    report = run_retrieval(golden_cases, fake_pipeline, MANIFEST_INPUT)
    assert len(report.observations) == len(golden_cases)
    assert all(o.stage_timings for o in report.observations)
    assert report.manifest.dataset_hash

def test_runner_never_calls_generation(fake_pipeline, forbidden_llm):
    run_retrieval(CASES, fake_pipeline, MANIFEST_INPUT)
    forbidden_llm.assert_not_called()
```

- [ ] **Step 2: Verify RED**

Run: `conda run -n localrag python -m pytest E:\AI_projects\LocalRAG\backend\tests\evals\test_retrieval_runner.py -v`

Expected: FAIL because retrieval runner does not exist.

- [ ] **Step 3: Implement runner and run the full v1 baseline**

The runner must create a fresh evaluation KB, ingest only the frozen corpus, wait for committed canonical chunks and compatible active manifests, warm models once, then measure five repeated retrieval runs per case and report p50/p95. It must not call the answer LLM. Save per-case ranked IDs/scores/query plan, failures, manifest and aggregates.

Run: `conda run -n localrag python -m backend.evals.cli retrieval --dataset E:\AI_projects\LocalRAG\backend\evals\golden\v1.jsonl --output E:\AI_projects\LocalRAG\data\evals\runs\phase1-candidate.json`

Expected: exit `0`; output has 120+ observations and no missing manifest field.

- [ ] **Step 4: Apply absolute gates and bootstrap the reviewed v1 baseline**

```powershell
conda run -n localrag python -m backend.evals.cli compare --candidate E:\AI_projects\LocalRAG\data\evals\runs\phase1-candidate.json --thresholds E:\AI_projects\LocalRAG\backend\evals\thresholds.json --fail-on-regression
conda run -n localrag python -m backend.evals.cli accept --candidate E:\AI_projects\LocalRAG\data\evals\runs\phase1-candidate.json --output E:\AI_projects\LocalRAG\backend\evals\baselines\v1-retrieval.json
```

Expected: both commands exit `0`; Recall@20 ≥ 0.90, MRR@10 ≥ 0.70, nDCG@10 ≥ 0.75, rerank Recall@5 ≥ 0.85, exact-term Recall@20 ≥ 0.95, warm retrieval p95 ≤ 4 seconds on the declared reference machine, and the accepted baseline SHA-256 equals the candidate report SHA-256.

- [ ] **Step 5: Add CI compare and commit**

CI validates JSONL and runs deterministic unit fixtures on every PR; the hardware/model baseline job runs on the labelled self-hosted runner and is required before promoting retrieval defaults.

```powershell
git -C E:\AI_projects\LocalRAG add backend/evals backend/tests/evals
git -C E:\AI_projects\LocalRAG commit -m "test: gate retrieval changes on golden baseline"
```

## Task 9: Phase Acceptance, Rollback Drill, and Handoff

**Files:**
- Create: `E:\AI_projects\LocalRAG\docs\quality\phase-1-acceptance.md`
- Create: `E:\AI_projects\LocalRAG\docs\quality\phase-1-handoff.md`

**Interfaces:**
- Consumes: all Phase 1 commits, test logs, migration revision, index manifest and accepted eval report.
- Produces: signed acceptance record, rollback evidence, and Phase 2 prerequisites.

- [ ] **Step 1: Run complete backend and quality gates**

```powershell
conda run -n localrag python -m pytest E:\AI_projects\LocalRAG\backend\tests -v
conda run -n localrag python -m backend.evals.cli validate --dataset E:\AI_projects\LocalRAG\backend\evals\golden\v1.jsonl
conda run -n localrag python -m backend.evals.cli compare --baseline E:\AI_projects\LocalRAG\backend\evals\baselines\v1-retrieval.json --candidate E:\AI_projects\LocalRAG\data\evals\runs\phase1-candidate.json --fail-on-regression
```

Expected: all tests PASS; both CLI commands exit `0`; no cross-scope candidate, duplicate stable ID, missing manifest, or metric regression.

- [ ] **Step 2: Exercise rollback before enabling the flag**

Back up MySQL, `data\chromadb`, canonical manifest and accepted report into a timestamped directory outside active data. Enable V2 for the evaluation KB, verify a known query, disable `retrieval_v2_enabled`, restart the API, and verify the legacy query still succeeds. Restore into a fresh directory and compare document count, canonical chunk count and accepted manifest hash.

Expected: disabling the flag requires no schema downgrade; V1 remains readable; restore counts and hashes equal the backup.

- [ ] **Step 3: Record the handoff contract**

The handoff must list completed and omitted items, exact commits/files, migration head, four frozen interfaces, commands with unedited output, baseline report hash, known risks, rollback location, and the Phase 2 prerequisite: `CanonicalDocument` must map into the existing `ChunkRecord` without changing its stable-ID semantics.

- [ ] **Step 4: Create integration tag and commit documentation**

```powershell
git -C E:\AI_projects\LocalRAG add docs/quality/phase-1-acceptance.md docs/quality/phase-1-handoff.md
git -C E:\AI_projects\LocalRAG commit -m "docs: record phase one quality acceptance"
git -C E:\AI_projects\LocalRAG tag phase-1-rag-quality-accepted
```

Expected: tag points to a commit whose accepted baseline hash matches the handoff.

## Phase 1 Acceptance Criteria

- Golden v1 contains at least 120 validated cases with the frozen category distribution and no sensitive data.
- Every evaluation report contains an immutable run manifest and case-level observations.
- Dense, Sparse, Reranker, repository and retrieval responses use one canonical chunk ID; restart set consistency is 100%.
- BM25-only and Dense-only hits survive fusion; cross-user and cross-KB hits are zero.
- All rewrites fuse before exactly one rerank against the original question.
- Recall@20 ≥0.90, MRR@10 ≥0.70, nDCG@10 ≥0.75, rerank Recall@5 ≥0.85, exact-term Recall@20 ≥0.95.
- Candidate regression is ≤0.01 per accepted quality metric and warm retrieval p95 regression is ≤20%.
- V2 remains off by default until acceptance; disabling it restores V1 without data deletion or downgrade.

## Rollback Strategy

1. Set `retrieval_v2_enabled=false`; do not drop canonical tables or delete V2 index generations.
2. Point the active index manifest back to the last accepted generation; immutable older generations remain available.
3. If an additive migration caused runtime incompatibility, deploy the previous application commit while retaining new nullable tables.
4. Restore MySQL, Chroma and manifest only from the jointly captured phase backup; verify hashes before routing traffic.
5. Never overwrite `backend\evals\baselines\v1-retrieval.json`; reject the candidate and retain its report for diagnosis.

## Execution Handoff

Execute Tasks 1–3 first to make every later change measurable. Task 4 requires Contract and Data Agent review before Tasks 5–7 start. Tasks 5 and Golden annotation can proceed in parallel after Task 4; Task 6 depends on Task 5, Task 7 depends on Tasks 4–6, and Tasks 8–9 are Integrator gates. Every Agent must provide completed items, files, contract changes, raw test output, risks and prerequisites; the Integrator alone edits shared startup/dependency/CI files and promotes the accepted baseline.
