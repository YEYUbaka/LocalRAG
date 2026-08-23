# Phase 1 检索基线报告

> 状态：部分完成（rewrite-off 已完成确定性验证；rewrite-on 被外部 LLM HTTP 502 阻塞）
> 首次执行日期：2026-08-23
> P1-05 补跑日期：2026-08-24

## 1. 结论

P1-05 已解除 `Document.md5_hash` 全局唯一约束，并修复 XLSX/CSV 生产解析缺陷。隔离评测环境成功索引 24/24 份语料，rewrite-off 连续完成两轮；两轮 120 题逐题结果完全一致。

rewrite-off 的 Recall@20 与 rerank Recall@5 未达到 Phase 1 门槛，其余三项达到门槛。15 条 `ocr_table` 全部保留原题，Recall@20 为 0.733333；这证明原生表格已进入真实解析与检索链路，同时如实暴露 4 条未命中问题。

rewrite-on 在独立运行中连续 13 次收到外部 LLM HTTP 502。生产改写逻辑自动退回原问题，因此该轮已主动中止且未生成 run 目录，避免把“名为 on、实为 off”的结果写成基线。rewrite-on 两轮与其确定性结论仍待外部服务恢复后补齐。

## 2. 测试输入与环境

| 项目 | 值 |
| --- | --- |
| 检索实现 commit | `10cb58ea4f24cc4ec2589a75ccf1a158455b3e69` |
| 第二轮运行时 HEAD | `5ec5b6a3976c70de356f660354e3add096f2a89f`（并发的 docs-only 提交；后端未变化） |
| Golden Set | `backend/evals/golden_set/v1.jsonl`，120 条 |
| Golden SHA-256 | `f50394abb9707afe3ed133d85ba0241287a1e03ccc12235b90524cca4a4d5baf` |
| 语料 | `test_docs/` 顶层 24 份生产解析器支持的文件 |
| 语料 SHA-256 指纹 | `7c823244ed4caa2a353112d51bdab5f7537986040c3357fef95e891f26066757` |
| Python | 3.11.15 |
| 平台 | Windows 10.0.26200 |
| ChromaDB | 1.5.9，隔离目录中的嵌入式 `PersistentClient` |
| FlagEmbedding | 1.4.0 |
| LangChain | 1.3.16 |
| SQLAlchemy | 2.0.35 |
| 数据库 | 隔离 MySQL 库，Alembic head=`20260802_0004` |
| 评测租户 | 保留的本地专用 tenant；自动创建不可登录的随机密码评测用户以满足外键 |

未使用用户现有 Chroma 索引；未修改或删除用户文档。运行结束前，隔离数据库与临时 Chroma 仅用于本次评测。

## 3. 执行结果

### 3.1 P1-05 前置阻塞

最初的 rewrite-off/on 命令均在索引阶段因全局 MD5 唯一约束安全停止。冲突文件为 `Git命令手册.docx`，MD5 为 `10f8c5fc66e1a498f72238a12fbbda74`。P1-05 将唯一约束改为 `(user_id, kb_id, md5_hash)` 后，隔离租户可以索引相同内容，同一租户内仍保持去重。

### 3.2 表格解析诊断与修复

首次诊断区分出两个生产解析缺陷，而非语料损坏：

- XLSX：`UnstructuredExcelLoader` 缺少未声明的 `unstructured` 依赖；改用项目已有 `openpyxl` 按工作表读取原生单元格。
- CSV：`CSVLoader` 在中文 Windows 使用 GBK；改为显式 UTF-8。
- DOCX：原 `Docx2txtLoader` 可正常抽取，无需修改。

修复后 24/24 文档均完成解析、分块、Dense upsert 与 BM25 建索引。没有修改 Golden Set 问题或答案。

### 3.3 rewrite off

正式运行目录：

1. `backend/evals/runs/20260823T160713.237533Z-baseline-v1-off-run1`，耗时 2192.098092 秒；
2. `backend/evals/runs/20260823T164429.309252Z-baseline-v1-off-run2`，耗时 2179.512998 秒。

两轮聚合指标完全一致，逐题 `details` JSON 完全一致。两份 `summary.json` 的文件 hash 不同，仅因为 summary 内含 Git commit：运行期间协作者向同一分支加入 `5ec5b6a` docs-only 提交；该提交未改变后端、语料或评测参数。因而本报告将“检索结果 payload 完全一致”作为确定性证据，不把跨 commit 的原始文件误写为逐字节相同。

### 3.4 rewrite on

命令已使用 `--enable-rewrite` 启动，但查询改写接口连续 13 次返回 HTTP 502。生产逻辑每次记录 `Query rewrite failed, using original` 并退回原问题。为避免生成误导性 on 结果，进程已中止；没有生成 run 目录。

恢复条件：外部 LLM 改写接口可稳定返回两个有效变体后，按相同 commit、语料指纹和隔离环境连续补跑两次，并比较逐题 queries 与 results。

## 4. 五指标与门槛判定

| 组别 | Recall@20 ≥0.90 | MRR@10 ≥0.70 | nDCG@10 ≥0.75 | rerank Recall@5 ≥0.85 | Unanswerable Recall ≥0.90 |
| --- | ---: | ---: | ---: | ---: | ---: |
| rewrite off run1 | 0.820000（失败） | 0.803333（通过） | 0.810000（通过） | 0.820000（失败） | 1.000000（通过） |
| rewrite off run2 | 0.820000（失败） | 0.803333（通过） | 0.810000（通过） | 0.820000（失败） | 1.000000（通过） |
| rewrite on | 未测定（HTTP 502） | 未测定 | 未测定 | 未测定 | 未测定 |

rewrite-off 整体门槛判定为失败，不因完成运行而视为通过。citation precision 与 locator round-trip 属于后续契约指标，不在当前 CLI 五指标范围内。

## 5. 分题型结果

| 题型 | 数量 | Recall@20 | MRR@10 | nDCG@10 | rerank Recall@5 |
| --- | ---: | ---: | ---: | ---: | ---: |
| factoid | 55 | 0.872727 | 0.845455 | 0.854545 | 0.872727 |
| multi_span | 15 | 0.733333 | 0.800000 | 0.800000 | 0.733333 |
| exact_term | 15 | 0.800000 | 0.711111 | 0.733333 | 0.800000 |
| ocr_table | 15 | 0.733333 | 0.733333 | 0.733333 | 0.733333 |
| unanswerable | 20 | — | — | — | — |

`ocr_table` 未命中的 4 条为 `gs-v1-0094`、`gs-v1-0097`、`gs-v1-0098`、`gs-v1-0103`。这是当前检索/阈值表现，不是数据生成失败；题目保持不变。

## 6. 稳定 ID 与迁移证据

- Alembic 隔离 MySQL 验证完成 `0003 → 0004 → 0003 → 0004`。
- 跨租户相同 MD5 可写入；同租户范围由复合唯一约束保护。
- chunk ID 规范为 `{document_key}-v{document_version}-c{chunker_version}-{ordinal:06d}`。
- Chroma 使用稳定 ID `upsert`，metadata 同时保存 `chunk_id`、`document_key`、`document_version`、`chunker_version` 与 `content_hash`。
- BM25 复用同一 `chunk_id`；旧 metadata 缺键时继续使用 legacy ID。
- 全量后端回归：229 passed。

## 7. 待补工作

1. 外部 LLM 恢复后补跑 rewrite-on 两次，回填 run 目录、queries 差异、五指标和确定性结论。
2. T5 统一融合重构必须以本报告 rewrite-off 数字为比较基线，不能低于当前结果；rewrite-on 对比在有效改写基线补齐前保持未判定。
3. run 产物保留在已忽略的 `backend/evals/runs/`，不提交仓库。
