# Phase 2 Structured Document Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 以统一 `CanonicalDocument` 接入 Docling 与单一 RapidOCR 后端，建立结构感知父子分块、表格/图片 provenance、持久摄取 Worker，并通过固定解析与检索评测证明复杂文档能力。

**Architecture:** Parser 层只将文件转换为带稳定 block/locator 的 CanonicalDocument，OCR 由 `auto/force/off` policy 控制且只有 RapidOCR 一个 backend；Chunker 层消费 canonical blocks 生成 parent/child `ChunkBundle`，不调用 Docling。摄取 Application Service 通过租约 Worker 编排 parse→persist canonical artifact→chunk→persist chunks→双索引，在每个可恢复 stage 写 TaskProgress，并继续使用 Phase 1 的稳定 chunk identity 和评测门禁。

**Tech Stack:** Python 3.11、pytest、Pydantic/dataclasses、Docling 2.x、RapidOCR ONNX Runtime、SQLAlchemy/MySQL、Alembic、ChromaDB、rank-bm25、Phase 1 eval CLI。

## Global Constraints

- 冻结设计：`E:\AI_projects\LocalRAG\docs\superpowers\specs\2026-08-02-localrag-quality-program-design.md`；Phase 1 handoff 与 accepted baseline 必须存在后才能开始集成。
- 产品边界保持个人本地知识库；不实现 GraphRAG、Agent、Workflow、MCP、多 OCR 后端、Redis/Celery 或外部向量数据库。
- Docling 是唯一结构解析入口；OCR backend 固定为 RapidOCR，使用 ONNX Runtime CPU 路径作为最低保证，GPU provider 仅为可选加速且不得改变输出契约。
- Parser 不负责 chunk；Chunker 不依赖 Docling 类型；Infrastructure adapter 不得泄漏到 `backend\app\domain\`。
- Python 只使用 `localrag` conda 环境；所有命令从 `E:\AI_projects\LocalRAG` 执行。
- 所有行为 TDD 红绿推进；解析 fixture 必须是小型、可再分发、无敏感数据的固定文件，禁止测试依赖网络下载。
- `backend\app\domain\` 归 Contract Agent，`backend\app\models.py` 与 `backend\alembic\` 归 Data Agent，`backend\app\main.py`、`backend\requirements.txt`、Compose 归 Integrator。
- `backend\app\services\document_service.py` 只由 Integrator 修改；RAG Agent 在 `core\parsing`、`core\chunking` 和 `application\ingestion` 内工作，不顺手重构 API、认证或前端。
- 新表/字段采用 expand→backfill→switch；保留旧 `parsed_content/page_breaks/chunk_count`、旧后台处理函数和旧索引，直到结构化摄取 flag 验收。
- 文档内容、OCR 文本与图片不得发送到外部服务；日志只记录 ID、stage、计数、耗时和错误码，不记录正文。
- 任何模型首次下载必须在安装/准备步骤显式完成；离线测试和 Worker 运行不得隐式访问网络。

---

## File and Contract Map

| Area | Owner | Files | Responsibility |
|---|---|---|---|
| Canonical contracts | Contract Agent | `E:\AI_projects\LocalRAG\backend\app\domain\documents.py` | parser-independent document/block/table/image/locator types |
| Parser boundary | RAG Agent | `E:\AI_projects\LocalRAG\backend\app\core\parsing\base.py`, `router.py`, `docling_parser.py` | source→CanonicalDocument |
| OCR policy | RAG Agent | `E:\AI_projects\LocalRAG\backend\app\core\parsing\ocr.py` | `auto/force/off` 决策与 RapidOCR adapter |
| Provenance normalization | RAG Agent | `E:\AI_projects\LocalRAG\backend\app\core\parsing\normalizer.py` | Docling item→ordered canonical blocks |
| Parent/child chunking | RAG Agent | `E:\AI_projects\LocalRAG\backend\app\core\chunking\parent_child.py`, `table_chunker.py` | CanonicalDocument→ChunkBundle |
| Canonical persistence | Data/RAG Agent | models/migration plus `application\ingestion\canonical_repository.py` | canonical artifact metadata and blob/reference storage |
| Worker orchestration | Ingestion Agent | `E:\AI_projects\LocalRAG\backend\app\application\ingestion\processor.py`, `worker.py` | leased task stage execution and recovery |
| Integration | Integrator | `document_service.py`, `config.py`, `requirements.txt`, startup | feature flag and dependency/startup wiring |
| Evaluation | RAG/QA Agent | `E:\AI_projects\LocalRAG\backend\evals\parsing_runner.py`, `ingestion_runner.py` | parser/OCR/provenance/retrieval regression |

### Frozen interfaces produced by this phase

```python
@dataclass(frozen=True)
class BlockLocator:
    page_index: int | None
    char_start: int
    char_end: int
    bbox: tuple[float, float, float, float] | None
    page_width: float | None
    page_height: float | None

@dataclass(frozen=True)
class CanonicalBlock:
    block_id: str
    block_type: Literal["heading", "paragraph", "list", "table", "image", "code"]
    text: str
    heading_path: tuple[str, ...]
    reading_order: int
    locator: BlockLocator
    table: CanonicalTable | None
    image: CanonicalImage | None
    ocr_confidence: float | None

@dataclass(frozen=True)
class CanonicalDocument:
    document_key: str
    document_version: str
    content_hash: str
    parser_name: str
    parser_version: str
    blocks: tuple[CanonicalBlock, ...]
```

```python
class Parser(Protocol):
    def parse(self, source: DocumentSource, options: ParseOptions) -> CanonicalDocument: ...

class ParentChildChunker:
    def chunk(self, document: CanonicalDocument, config: ChunkingConfig) -> ChunkBundle: ...

class IngestionProcessor:
    def execute(self, task: LeasedTask) -> ProcessingResult: ...
```

`ParseOptions.ocr_mode` is exactly `auto|force|off`. `ChunkBundle.children` uses the Phase 1 `ChunkRecord`; its ID formula and scope fields may not change.

## Task 1: Freeze CanonicalDocument Domain Contracts

**Files:**
- Create (Contract Agent): `E:\AI_projects\LocalRAG\backend\app\domain\documents.py`
- Create (Contract Agent): `E:\AI_projects\LocalRAG\backend\app\domain\ingestion.py`
- Create: `E:\AI_projects\LocalRAG\backend\tests\test_canonical_document_contract.py`

**Interfaces:**
- Consumes: Phase 1 `TenantScope`, `ChunkProvenance`, and the frozen shapes above.
- Produces: `DocumentSource`, `ParseOptions`, `BlockLocator`, `CanonicalCell`, `CanonicalTable`, `CanonicalImage`, `CanonicalBlock`, `CanonicalDocument`, `ParseError` and `UnsupportedSourceError`.

- [ ] **Step 1: Write invariant and serialization tests**

```python
def test_canonical_document_rejects_overlapping_reading_order(block_factory):
    blocks = (block_factory(block_id="b1", order=0), block_factory(block_id="b2", order=0))
    with pytest.raises(ValueError, match="reading_order"):
        CanonicalDocument.create("doc", "v1", "sha256:x", "docling", "2.x", blocks)

def test_locator_requires_half_open_span():
    with pytest.raises(ValueError, match="char_start"):
        BlockLocator(page_index=0, char_start=9, char_end=9, bbox=None, page_width=None, page_height=None)

def test_contract_round_trip_preserves_table_and_image(canonical_document):
    assert CanonicalDocument.from_dict(canonical_document.to_dict()) == canonical_document
```

- [ ] **Step 2: Verify RED**

Run: `conda run -n localrag python -m pytest E:\AI_projects\LocalRAG\backend\tests\test_canonical_document_contract.py -v`

Expected: FAIL because `app.domain.documents` does not exist.

- [ ] **Step 3: Implement dependency-free immutable contracts**

Use frozen dataclasses and JSON-safe `to_dict/from_dict`; do not import Docling, SQLAlchemy, FastAPI or Chroma. Enforce unique `block_id`, strictly increasing reading order, zero-based non-negative page indexes, half-open character spans, normalized bbox coordinates inside page dimensions, rectangular tables with explicit row/column indices, and image records containing optional caption plus source block locator rather than image bytes.

- [ ] **Step 4: Verify GREEN and Phase 1 compatibility**

Run: `conda run -n localrag python -m pytest E:\AI_projects\LocalRAG\backend\tests\test_canonical_document_contract.py E:\AI_projects\LocalRAG\backend\tests\test_chunk_repository.py -v`

Expected: PASS; importing Domain contracts does not import Docling/SQLAlchemy, and Phase 1 chunk contracts remain unchanged.

- [ ] **Step 5: Commit**

```powershell
git -C E:\AI_projects\LocalRAG add backend/app/domain/documents.py backend/app/domain/ingestion.py backend/tests/test_canonical_document_contract.py
git -C E:\AI_projects\LocalRAG commit -m "feat: define canonical document contracts"
```

## Task 2: Docling Parser and ParserRouter Without OCR

**Files:**
- Create: `E:\AI_projects\LocalRAG\backend\app\core\parsing\__init__.py`
- Create: `E:\AI_projects\LocalRAG\backend\app\core\parsing\base.py`
- Create: `E:\AI_projects\LocalRAG\backend\app\core\parsing\router.py`
- Create: `E:\AI_projects\LocalRAG\backend\app\core\parsing\docling_parser.py`
- Create: `E:\AI_projects\LocalRAG\backend\app\core\parsing\normalizer.py`
- Modify (Integrator): `E:\AI_projects\LocalRAG\backend\requirements.txt`
- Create: `E:\AI_projects\LocalRAG\backend\tests\parsing\fixtures\digital-two-page.pdf`
- Create: `E:\AI_projects\LocalRAG\backend\tests\parsing\fixtures\structured.docx`
- Create: `E:\AI_projects\LocalRAG\backend\tests\parsing\test_docling_parser.py`

**Interfaces:**
- Consumes: Task 1 contracts.
- Produces: `ParserRouter.register(suffixes, parser)`, `ParserRouter.parse(source, options)`, `DoclingParser.parse(...)`; no OCR invocation in this task.

- [ ] **Step 1: Write fixture-based parser tests**

```python
def test_digital_pdf_preserves_pages_headings_and_order(parser, fixtures):
    doc = parser.parse(fixtures / "digital-two-page.pdf", ParseOptions(ocr_mode="off"))
    assert [b.reading_order for b in doc.blocks] == list(range(len(doc.blocks)))
    assert {b.locator.page_index for b in doc.blocks if b.text} == {0, 1}
    assert any(b.block_type == "heading" and b.heading_path for b in doc.blocks)

def test_router_rejects_unregistered_extension(router, tmp_path):
    with pytest.raises(UnsupportedSourceError):
        router.parse(DocumentSource(tmp_path / "x.exe", "x"), ParseOptions(ocr_mode="off"))
```

- [ ] **Step 2: Verify RED**

Run: `conda run -n localrag python -m pytest E:\AI_projects\LocalRAG\backend\tests\parsing\test_docling_parser.py -v`

Expected: FAIL because parsing adapters are absent.

- [ ] **Step 3: Integrator adds bounded dependencies and performs offline model preparation**

Add `docling>=2,<3` and `rapidocr-onnxruntime>=1.4,<2` to the project dependency input, resolve them in `localrag`, record the exact installed versions in the dependency lock/acceptance manifest, and pre-download Docling artifacts into the configured local model directory. Runtime tests must set offline mode and fail with `PARSER_MODEL_MISSING`, not attempt a network request.

- [ ] **Step 4: Implement router and Docling adapter**

Route `.pdf`, `.docx`, `.pptx`, `.xlsx` to one `DoclingParser`. Compute `content_hash` from file bytes; derive `document_version` from content hash plus parser fingerprint. Convert Docling output immediately through `normalizer.py`; expose no Docling object beyond the adapter. Sort by page then reading order supplied by Docling, retaining source provenance and using deterministic `block_id = "blk_" + sha256(document_version, page_index, reading_order, normalized_text)[:24]`.

- [ ] **Step 5: Verify GREEN**

Run: `conda run -n localrag python -m pytest E:\AI_projects\LocalRAG\backend\tests\parsing\test_docling_parser.py -v`

Expected: PASS offline; parsing the same file twice produces byte-identical canonical JSON and IDs.

- [ ] **Step 6: Commit by file owner**

```powershell
git -C E:\AI_projects\LocalRAG add backend/app/core/parsing backend/tests/parsing backend/requirements.txt
git -C E:\AI_projects\LocalRAG commit -m "feat: add deterministic docling parser"
```

## Task 3: Single RapidOCR Backend and Auto/Force/Off Policy

**Files:**
- Create: `E:\AI_projects\LocalRAG\backend\app\core\parsing\ocr.py`
- Create: `E:\AI_projects\LocalRAG\backend\tests\parsing\fixtures\scanned-clear-zh.pdf`
- Create: `E:\AI_projects\LocalRAG\backend\tests\parsing\fixtures\scanned-degraded-zh.pdf`
- Create: `E:\AI_projects\LocalRAG\backend\tests\parsing\test_ocr_policy.py`
- Create: `E:\AI_projects\LocalRAG\backend\tests\parsing\test_rapidocr_adapter.py`

**Interfaces:**
- Consumes: `ParseOptions.ocr_mode`, Docling page diagnostics and Task 1 locator contracts.
- Produces: `OcrDecision`, `OcrPageResult`, `RapidOcrBackend.recognize(page_image)`, `OcrPolicy.pages_to_ocr(diagnostics, mode)`.

- [ ] **Step 1: Write decision-table tests**

```python
@pytest.mark.parametrize(("mode","native_chars","image_ratio","expected"), [
    ("off", 0, 1.0, False),
    ("force", 500, 0.0, True),
    ("auto", 20, 0.95, True),
    ("auto", 500, 0.10, False),
])
def test_ocr_policy(mode, native_chars, image_ratio, expected):
    decision = OcrPolicy(min_native_chars=80, image_ratio_threshold=0.80).decide(PageDiagnostics(native_chars, image_ratio), mode)
    assert decision.use_ocr is expected
```

- [ ] **Step 2: Verify RED**

Run: `conda run -n localrag python -m pytest E:\AI_projects\LocalRAG\backend\tests\parsing\test_ocr_policy.py E:\AI_projects\LocalRAG\backend\tests\parsing\test_rapidocr_adapter.py -v`

Expected: FAIL because OCR policy/backend do not exist.

- [ ] **Step 3: Implement one backend and explicit provider selection**

`RapidOcrBackend` accepts a provider list at construction. Prefer CUDA only when explicitly configured and available; otherwise use `CPUExecutionProvider`. Do not fall back to a second OCR library. Normalize each recognized line into text, confidence, pixel bbox and reading order; transform bbox to document page coordinates and retain page width/height. `auto` uses exactly the tested thresholds and works page-by-page, so digital pages in a mixed PDF are not OCRed.

- [ ] **Step 4: Verify OCR accuracy and offline behavior**

Run: `conda run -n localrag python -m pytest E:\AI_projects\LocalRAG\backend\tests\parsing\test_ocr_policy.py E:\AI_projects\LocalRAG\backend\tests\parsing\test_rapidocr_adapter.py -v`

Expected: PASS; clear Chinese fixture character accuracy ≥0.95, degraded fixture ≥0.90, all OCR blocks have confidence and bbox, and no test performs a network request.

- [ ] **Step 5: Commit**

```powershell
git -C E:\AI_projects\LocalRAG add backend/app/core/parsing/ocr.py backend/tests/parsing
git -C E:\AI_projects\LocalRAG commit -m "feat: add rapidocr policy and provenance"
```

## Task 4: Table and Image Provenance Normalization

**Files:**
- Modify: `E:\AI_projects\LocalRAG\backend\app\core\parsing\normalizer.py`
- Create: `E:\AI_projects\LocalRAG\backend\tests\parsing\fixtures\table-and-image.pdf`
- Create: `E:\AI_projects\LocalRAG\backend\tests\parsing\fixtures\table-and-image.pptx`
- Create: `E:\AI_projects\LocalRAG\backend\tests\parsing\test_structured_provenance.py`

**Interfaces:**
- Consumes: Docling table/picture items, OCR line results and Task 1 `CanonicalTable/CanonicalImage`.
- Produces: rectangular cell matrices, repeated/merged cell coordinates, image caption/alt text, page locator and global half-open character offsets.

- [ ] **Step 1: Write table, image and offset tests**

```python
def test_table_cells_keep_coordinates_and_header(parsed_fixture):
    table = next(b.table for b in parsed_fixture.blocks if b.block_type == "table")
    assert [(c.row, c.column, c.text) for c in table.cells[:2]] == [(0, 0, "项目"), (0, 1, "金额")]
    assert table.header_rows == (0,)

def test_every_text_block_round_trips_global_span(parsed_fixture):
    canonical_text = parsed_fixture.render_text()
    for block in parsed_fixture.blocks:
        assert canonical_text[block.locator.char_start:block.locator.char_end] == block.text
```

- [ ] **Step 2: Verify RED**

Run: `conda run -n localrag python -m pytest E:\AI_projects\LocalRAG\backend\tests\parsing\test_structured_provenance.py -v`

Expected: FAIL because current normalizer lacks table/image structures or exact offsets.

- [ ] **Step 3: Normalize structured items deterministically**

Render canonical text with exactly one `\n\n` separator and include separators in subsequent offsets. Table text uses tab-separated cells and newline-separated rows; merged cells retain row/column spans. Image blocks store caption/alt text and locator but never base64 or raw pixels. Empty decorative images may have empty captions but must not become retrieval children. Human-facing page number is never stored; only zero-based `page_index` is canonical.

- [ ] **Step 4: Verify GREEN and 99% locator round-trip**

Run: `conda run -n localrag python -m pytest E:\AI_projects\LocalRAG\backend\tests\parsing\test_structured_provenance.py E:\AI_projects\LocalRAG\backend\tests\test_canonical_document_contract.py -v`

Expected: PASS; all deterministic fixtures round-trip exactly and aggregate locator round-trip ≥0.99.

- [ ] **Step 5: Commit**

```powershell
git -C E:\AI_projects\LocalRAG add backend/app/core/parsing/normalizer.py backend/tests/parsing
git -C E:\AI_projects\LocalRAG commit -m "feat: preserve table and image provenance"
```

## Task 5: Structure-aware Parent/Child Chunking

**Files:**
- Create: `E:\AI_projects\LocalRAG\backend\app\core\chunking\__init__.py`
- Create: `E:\AI_projects\LocalRAG\backend\app\core\chunking\parent_child.py`
- Create: `E:\AI_projects\LocalRAG\backend\app\core\chunking\table_chunker.py`
- Create: `E:\AI_projects\LocalRAG\backend\tests\chunking\test_parent_child_chunker.py`
- Create: `E:\AI_projects\LocalRAG\backend\tests\chunking\test_table_chunker.py`

**Interfaces:**
- Consumes: `CanonicalDocument`, Phase 1 `ChunkRecord/make_chunk_id`, `ChunkingConfig(parent_tokens=1600, child_tokens=400, overlap_tokens=60, chunker_version="parent-child-v1")`.
- Produces: `ChunkBundle(parents, children)`; children are retrieval units and every child has parent/block/span/page provenance.

- [ ] **Step 1: Write boundary and table-header tests**

```python
def test_children_reference_parent_and_source_blocks(chunker, canonical_document):
    bundle = chunker.chunk(canonical_document, CONFIG)
    assert bundle.children
    assert all(c.provenance.parent_chunk_id for c in bundle.children)
    assert all(c.provenance.block_ids for c in bundle.children)

def test_long_table_repeats_header_without_splitting_row(table_chunker, long_table):
    groups = table_chunker.split(long_table, max_tokens=120)
    assert len(groups) > 1
    assert all(group.rows[0] == long_table.rows[0] for group in groups)
    assert sorted(row for group in groups for row in group.rows[1:]) == sorted(long_table.rows[1:])
```

- [ ] **Step 2: Verify RED**

Run: `conda run -n localrag python -m pytest E:\AI_projects\LocalRAG\backend\tests\chunking -v`

Expected: FAIL because chunking package does not exist.

- [ ] **Step 3: Implement heading-aware parent and child construction**

Parents align to heading sections and target 1200–2000 tokens; children target 250–500 tokens with at most 60-token overlap. Never join across top-level headings. Preserve code blocks and normal tables atomically when within budget. For oversized tables split only between rows and repeat header rows. Child retrieval text begins with heading path but provenance spans only source content. Tokenizer is injected and its name/version becomes part of chunker fingerprint.

- [ ] **Step 4: Preserve Phase 1 stable identity**

Call Phase 1 `make_chunk_id(document_key, document_version, chunker_version, ordinal, content_hash)` without local ID logic. Parsing the same document/config twice must produce identical parent/child IDs; changing OCR/parser/document/chunker version must change affected IDs. Decorative image-only blocks must not generate empty children; captioned images may generate children with image block provenance.

- [ ] **Step 5: Verify GREEN**

Run: `conda run -n localrag python -m pytest E:\AI_projects\LocalRAG\backend\tests\chunking E:\AI_projects\LocalRAG\backend\tests\test_chunk_repository.py -v`

Expected: PASS; 100% children have document/parent/block/span provenance, no row loss or duplicate data rows, and stable IDs remain compatible with Phase 1.

- [ ] **Step 6: Commit**

```powershell
git -C E:\AI_projects\LocalRAG add backend/app/core/chunking backend/tests/chunking
git -C E:\AI_projects\LocalRAG commit -m "feat: add structure-aware parent child chunking"
```

## Task 6: Canonical Artifact Persistence and Index Integration

**Files:**
- Modify (Data Agent): `E:\AI_projects\LocalRAG\backend\app\models.py`
- Create (Data Agent): `E:\AI_projects\LocalRAG\backend\alembic\versions\20260802_02_add_canonical_documents.py`
- Create: `E:\AI_projects\LocalRAG\backend\app\application\ingestion\canonical_repository.py`
- Create: `E:\AI_projects\LocalRAG\backend\app\application\ingestion\pipeline.py`
- Create: `E:\AI_projects\LocalRAG\backend\tests\integration\test_structured_ingestion.py`

**Interfaces:**
- Consumes: ParserRouter, ParentChildChunker, Phase 1 ChunkRepository/IndexService.
- Produces: `CanonicalDocumentRepository.put/get`, `StructuredIngestionPipeline.prepare(scope, document_id, source, options) -> PreparedIngestion`, `commit(prepared) -> IngestionReceipt`.

- [ ] **Step 1: Write atomicity and rebuild tests**

```python
def test_indexes_are_not_switched_before_chunks_commit(pipeline, index_service):
    pipeline.chunk_repository.replace_document.side_effect = RuntimeError("db failed")
    with pytest.raises(RuntimeError):
        pipeline.ingest(TASK)
    index_service.activate_manifest.assert_not_called()

def test_rebuild_reads_persisted_chunks_not_source_file(pipeline, source_path):
    receipt = pipeline.ingest(TASK)
    source_path.unlink()
    assert pipeline.rebuild_indexes(receipt.scope, receipt.manifest_id).chunk_count == receipt.child_count
```

- [ ] **Step 2: Verify RED**

Run: `conda run -n localrag python -m pytest E:\AI_projects\LocalRAG\backend\tests\integration\test_structured_ingestion.py -v`

Expected: FAIL because canonical repository and ingestion pipeline are absent.

- [ ] **Step 3: Add additive canonical artifact schema**

Store document/scope/version/parser fingerprint/content hash, canonical JSON artifact path or compressed JSON blob, block count and created timestamp. Unique key is `(owner_id, kb_id, document_id, document_version)`. Never overwrite a different version; do not remove legacy document columns. Migration downgrade may remove only the new empty tables and is not used for production rollback.

- [ ] **Step 4: Implement staged persistence and indexing**

Order is parse→persist immutable canonical artifact→build bundle→transactionally replace canonical chunks→upsert inactive Dense/Sparse generation→validate counts/manifest→activate generation. If index validation fails, canonical artifact/chunks remain for explicit retry; active old generation remains unchanged. Rebuild reads repository chunks even when the upload file is unavailable.

- [ ] **Step 5: Verify migration and GREEN**

```powershell
conda run -n localrag alembic -c E:\AI_projects\LocalRAG\backend\alembic.ini upgrade head
conda run -n localrag python -m pytest E:\AI_projects\LocalRAG\backend\tests\integration\test_structured_ingestion.py E:\AI_projects\LocalRAG\backend\tests\integration\test_index_restart_consistency.py -v
```

Expected: PASS; index counts equal child count, restart result IDs are identical, and deleted source file does not prevent index rebuild.

- [ ] **Step 6: Commit by owner**

```powershell
git -C E:\AI_projects\LocalRAG add backend/app/models.py backend/alembic backend/app/application/ingestion backend/tests/integration/test_structured_ingestion.py
git -C E:\AI_projects\LocalRAG commit -m "feat: persist canonical ingestion artifacts"
```

## Task 7: Persistent Worker Integration and Recovery

**Files:**
- Create: `E:\AI_projects\LocalRAG\backend\app\application\ingestion\processor.py`
- Create: `E:\AI_projects\LocalRAG\backend\app\application\ingestion\worker.py`
- Modify (Integrator): `E:\AI_projects\LocalRAG\backend\app\services\document_service.py`
- Modify (Integrator): `E:\AI_projects\LocalRAG\backend\app\config.py`
- Modify (Integrator): worker startup entry point owned by the ingestion/Integrator handoff.
- Create: `E:\AI_projects\LocalRAG\backend\tests\integration\test_ingestion_worker.py`

**Interfaces:**
- Consumes: Track A `TaskRepository.lease/heartbeat/succeed/fail/cancel`, frozen TaskProgress states, Task 6 pipeline.
- Produces: `IngestionProcessor.execute(LeasedTask)`, `IngestionWorker.run_once() -> WorkerOutcome`, setting `structured_ingestion_enabled: bool = False`.

- [ ] **Step 1: Write lease, idempotency and recovery tests**

```python
def test_worker_recovers_expired_running_task(worker, tasks, clock):
    task = tasks.seed_running(lease_until=clock.now_minus(seconds=1), stage="chunk")
    outcome = worker.run_once()
    assert outcome.task_id == task.id
    assert tasks.get(task.id).status == "succeeded"

def test_retry_upserts_without_duplicate_chunks(worker, tasks, chunk_repository):
    task = tasks.seed_failed_retryable(idempotency_key="ingest:doc-9:v2")
    worker.run_once()
    first_ids = chunk_repository.ids(task.scope, task.document_id)
    tasks.retry(task.id)
    worker.run_once()
    assert chunk_repository.ids(task.scope, task.document_id) == first_ids
```

- [ ] **Step 2: Verify RED or explicit dependency block**

Run: `conda run -n localrag python -m pytest E:\AI_projects\LocalRAG\backend\tests\integration\test_ingestion_worker.py -v`

Expected: FAIL because Worker integration is absent. If Track A `TaskRepository` is not merged, stop this task and record the exact missing contract; do not create a competing task table or in-memory queue.

- [ ] **Step 3: Implement stage-aware processor**

Stages are `parse`, `persist_canonical`, `chunk`, `persist_chunks`, `index_dense`, `index_sparse`, `validate_manifest`, `activate`. Heartbeat before and after every stage. Map deterministic errors to `UNSUPPORTED_FORMAT`, `PARSER_MODEL_MISSING`, `OCR_FAILED`, `CORRUPT_DOCUMENT`, `INDEX_FAILED`; store sanitized details. Cancellation is checked between stages and never activates a partial generation. Idempotency key is `ingest:{owner_id}:{kb_id}:{document_id}:{document_version}:{pipeline_version}`.

- [ ] **Step 4: Integrate behind the flag**

When `structured_ingestion_enabled=false`, retain the existing BackgroundTasks path. When true, API/document service only validates ownership/source and enqueues the persistent task; Worker owns processing. Reprocessing the same version reuses canonical artifacts/chunks and upserts indexes. Do not start the Worker inside every Uvicorn web worker; provide one explicit process entry point.

- [ ] **Step 5: Verify GREEN and restart recovery**

Run: `conda run -n localrag python -m pytest E:\AI_projects\LocalRAG\backend\tests\integration\test_ingestion_worker.py E:\AI_projects\LocalRAG\backend\tests\integration\test_structured_ingestion.py E:\AI_projects\LocalRAG\backend\tests\test_document_service.py -v`

Expected: PASS; expired leases recover, cancellation never activates, retry produces no duplicate chunk IDs, and false flag preserves legacy behavior.

- [ ] **Step 6: Commit**

```powershell
git -C E:\AI_projects\LocalRAG add backend/app/application/ingestion backend/app/services/document_service.py backend/app/config.py backend/tests/integration/test_ingestion_worker.py
git -C E:\AI_projects\LocalRAG commit -m "feat: run structured ingestion in recoverable worker"
```

## Task 8: Parsing, Ingestion and Retrieval Evaluation Gate

**Files:**
- Create: `E:\AI_projects\LocalRAG\backend\evals\parsing_runner.py`
- Create: `E:\AI_projects\LocalRAG\backend\evals\ingestion_runner.py`
- Create: `E:\AI_projects\LocalRAG\backend\tests\evals\test_parsing_runner.py`
- Create: `E:\AI_projects\LocalRAG\backend\evals\baselines\v1-structured-ingestion.json`
- Create: `E:\AI_projects\LocalRAG\docs\quality\phase-2-acceptance.md`
- Create: `E:\AI_projects\LocalRAG\docs\quality\phase-2-handoff.md`

**Interfaces:**
- Consumes: fixed digital/OCR/table/image fixtures, Golden v1 OCR/table subset, Phase 1 retrieval baseline and Tasks 1–7.
- Produces: parser and end-to-end ingestion observations, candidate report, acceptance/rollback evidence and Phase 3 handoff.

- [ ] **Step 1: Write deterministic parser metric tests**

```python
def test_parsing_report_counts_locator_round_trips(runner, annotated_fixture):
    report = runner.run([annotated_fixture])
    assert report.locator_total > 0
    assert report.locator_round_trip == pytest.approx(1.0)

def test_ingestion_report_links_every_child_to_block(runner, structured_fixture):
    report = runner.run([structured_fixture])
    assert report.children_without_provenance == 0
```

- [ ] **Step 2: Verify RED**

Run: `conda run -n localrag python -m pytest E:\AI_projects\LocalRAG\backend\tests\evals\test_parsing_runner.py -v`

Expected: FAIL because structured evaluation runners do not exist.

- [ ] **Step 3: Implement deterministic parsing metrics**

Measure ingest success, annotated block text recall, OCR character accuracy using normalized Levenshtein distance, table cell exact-match accuracy, provenance coverage, locator round-trip, child provenance coverage and index ID/count consistency. Include parser/OCR/provider/chunker fingerprints and hardware label in the Phase 1 manifest; no LLM judge is used for these metrics.

- [ ] **Step 4: Run full structured candidate**

```powershell
conda run -n localrag python -m pytest E:\AI_projects\LocalRAG\backend\tests -v
conda run -n localrag python -m backend.evals.cli validate --dataset E:\AI_projects\LocalRAG\backend\evals\golden\v1.jsonl
conda run -n localrag python -m backend.evals.ingestion_runner --dataset E:\AI_projects\LocalRAG\backend\evals\golden\v1.jsonl --output E:\AI_projects\LocalRAG\data\evals\runs\phase2-structured-candidate.json
```

Expected: PASS/exit `0`; ingest success ≥0.98, digital document block text recall ≥0.98, clear Chinese OCR accuracy ≥0.95, degraded OCR accuracy ≥0.90, annotated table cell accuracy ≥0.90, child provenance coverage `1.0`, locator round-trip ≥0.99, and restart ID consistency `1.0`.

- [ ] **Step 5: Verify retrieval does not regress**

Run: `conda run -n localrag python -m backend.evals.cli compare --baseline E:\AI_projects\LocalRAG\backend\evals\baselines\v1-retrieval.json --candidate E:\AI_projects\LocalRAG\data\evals\runs\phase2-structured-candidate.json --fail-on-regression`

Expected: exit `0`; overall Recall@20/MRR@10/nDCG@10 remain above Phase 1 gates with no metric drop >0.01, OCR/table subset Recall@20 ≥0.90, and warm retrieval p95 regression ≤20%.

- [ ] **Step 6: Exercise feature rollback and Worker recovery**

Back up MySQL, uploads, Chroma, canonical artifacts and manifests. Enable structured ingestion only for the evaluation KB; ingest all fixtures, terminate the Worker during `index_sparse`, restart it and verify lease recovery. Then disable the flag, ingest one legacy text document, and confirm legacy preview/retrieval still works. Restore the backup into a fresh data directory and compare counts/hashes.

Expected: interrupted task succeeds exactly once after recovery; no duplicate chunk IDs; disabling flag needs no schema downgrade; restored hashes match.

- [ ] **Step 7: Record handoff and commit/tag**

Handoff lists commits/files, exact installed Docling/RapidOCR/ONNX providers, fixtures and licenses, Domain interfaces, migration head, raw commands/output, report hashes, known unsupported/corrupt formats, rollback path, and Phase 3 prerequisites for CitationV2 to consume `BlockLocator`/Chunk provenance without parser imports.

```powershell
git -C E:\AI_projects\LocalRAG add backend/evals backend/tests/evals docs/quality/phase-2-acceptance.md docs/quality/phase-2-handoff.md
git -C E:\AI_projects\LocalRAG commit -m "test: accept structured document ingestion"
git -C E:\AI_projects\LocalRAG tag phase-2-structured-ingestion-accepted
```

Expected: tag points to the commit whose structured and Phase 1 retrieval report hashes appear in the handoff.

## Phase 2 Acceptance Criteria

- Docling is the only parser adapter for PDF/DOCX/PPTX/XLSX; RapidOCR is the only OCR backend, with CPU fallback and no runtime network access.
- `auto/force/off` behavior is covered by a decision table; mixed digital/scanned PDFs OCR only the selected pages.
- Parsing the same bytes with the same fingerprint produces identical canonical JSON, block IDs and child IDs.
- Ingest success ≥0.98; digital block text recall ≥0.98; clear/degraded Chinese OCR accuracy ≥0.95/0.90; table cell accuracy ≥0.90.
- Every retrieval child has parent, document version, block IDs, half-open span and page provenance; locator round-trip ≥0.99.
- Long tables repeat headers without losing/duplicating data rows; captioned images retain locator, decorative images do not create empty chunks.
- Canonical artifacts and chunks commit before index generation activation; index rebuild succeeds without the original upload.
- Worker restart recovers expired leases, explicit retry is idempotent, cancellation never activates a partial generation.
- Phase 1 retrieval gates remain met and no accepted metric drops by more than 0.01; warm retrieval p95 regression ≤20%.
- Structured ingestion stays off by default until acceptance; legacy ingestion remains usable after disabling it.

## Rollback Strategy

1. Set `structured_ingestion_enabled=false` and stop the standalone Worker after its current lease expires; do not kill a commit/activation transaction midway.
2. Keep new canonical tables/artifacts and inactive index generations; route new ingestion to the legacy BackgroundTasks path.
3. Point active Dense/Sparse manifests back to the Phase 1 accepted generation; do not delete the rejected Phase 2 report.
4. Deploy the previous application version without downgrading additive tables. Restore MySQL/uploads/Chroma/artifacts only from the joint pre-phase backup into a fresh directory, then verify hashes.
5. If OCR/parser dependencies break startup, remove them only in a dedicated Integrator rollback commit after the flag is off; Domain contracts and stored canonical artifacts remain readable JSON.

## Execution Handoff

Task 1 is a contract gate. Tasks 2 and Worker-contract preparation may proceed in parallel after it; Task 3 depends on Task 2 diagnostics, Task 4 depends on Tasks 2–3, Task 5 depends on Tasks 1 and 4, Task 6 depends on Phase 1 repositories plus Task 5, Task 7 depends on Track A TaskRepository and Task 6, and Task 8 is the Integrator gate. Contract/Data/Integrator-owned files must be merged through their owners rather than edited by RAG workers. Every handoff includes completed/omitted work, exact files and commits, contract changes, raw test output, fixture provenance/licenses, risks, rollback evidence and the next task's prerequisites.
