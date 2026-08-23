# T3.5 召回缺口归因报告

> 分支：`feat/T3.5-recall-gap`<br>
> 取证日期：2026-08-24<br>
> 正式基线：`20260823T160713.237533Z-baseline-v1-off-run1`、`20260823T164429.309252Z-baseline-v1-off-run2`<br>
> 范围：仅归因；未修改 Golden Set、语料、解析器、分块器、指标或生产检索代码。

## 结论摘要

正式 rewrite-off 基线中共有 19 条 `Recall@20 < 1` 的题目；它们包含 24 个期望文档对，其中 22 个未命中对。两次正式运行的 `details` 结构完全相同，因而本报告归因的现象具有确定性。

主要失分不是语料未入索引、不是 `similarity_threshold=0.7` 截杀，也不是四条原生表格题的解析失败：所有 24 个期望文档对均存在于评测数据库、Chroma 和重建后的 BM25 语料中。22 个未命中对中：

- 21 个已经进入 RRF 候选池，但在 `rerank_threshold=1.0` 过滤时被全部移除；
- 1 个（`gs-v1-0088` 的 `Python编程笔记.txt`）同时位于 Dense 第 24、BM25 第 38，未进入任一 top-20 候选池；
- `similarity_threshold` 对本组没有截杀：每个进入 Dense top-20 的期望文档距离均不大于 0.7；
- 本组没有实际触发「Dense 空而丢弃 BM25-only」分支，也没有已进入候选池的目标被 RRF 淘汰。

这说明 T5 应先落实统一候选池、跨通路稳定 ID 去重、单次原问题 rerank 和 BM25-only 保留；阈值的数值校准不是本任务可修改的融合项，保留为后续基线数据驱动的提案，不能为了本次指标改全局默认值或改题。

## 取证方法与可复核范围

### 固定输入

- 正式 run1/run2 的 `manifest.json`：运行参数均为 rewrite-off、`top_k=20`、语料 24 份；run1 汇总指标为 Recall@20 `0.82`、MRR@10 `0.803333`、nDCG@10 `0.81`、rerank Recall@5 `0.82`、Unanswerable Recall `1.0`。
- 隔离数据库：`localrag_p105_eval_20260823`；隔离 Chroma：`C:\Users\21239\AppData\Local\Temp\localrag-p105-eval-data-20260823`。
- 临时只读脚本：`plans/t35-recall-diagnostics.py`，输出未提交的 `plans/t35-recall-diagnostic-output.json`。脚本没有摄取、删除或持久化任何评测数据；`rebuild_from_db()` 仅在进程内重建 BM25。

### 逐层采集

对 19 题依次采集全量 Dense 原始位次、Dense top-20 经 0.7 过滤后的结果、全量 BM25 位次/分数、当前 top-20 RRF、rerank 前后、`rerank_threshold=1.0` 后结果，并与冻结 manifest 的生产最终结果交叉核对。

当前隔离索引读到 209 个 Chroma chunk（均带 stable metadata）和 209 个 BM25 chunk（均使用 legacy `doc_<id>_chunk_<n>` ID）。后者来自 `bm25_search.rebuild_from_db()` 未调用 `build_stable_chunk_metadata()` 的既有实现；正式 manifest 中同一文件同时出现 stable 与 legacy ID 也直接佐证了跨索引去重未统一。

## 逐题归因

表中 `D` 为目标文档的原始 Dense 位次/距离，`B` 为 BM25 位次，`R` 为 RRF 位次，`RR` 为 rerank 位次/分数。`—` 表示未进入对应 top-20 阶段。所有「阈值移除」均指 rerank 阈值，不是 similarity 阈值。

| 题目 | 类型 | 期望文档与阶段证据 | 生产结果与主因 |
| --- | --- | --- | --- |
| gs-v1-0024 | factoid | `interview-mock-qa.md`：D 6/0.402，B 1，R 2，RR 1/0.883 | 阈值移除；正式结果空 |
| gs-v1-0028 | factoid | `interview-network-basics.md`：D 1/0.445，B 1，R 1，RR 1/-1.692 | 阈值移除；正式结果空 |
| gs-v1-0034 | exact_term | `interview-project-star.md`：D 1/0.456，B 1，R 1，RR 3/-0.648 | 阈值移除；正式结果空 |
| gs-v1-0043 | exact_term | `interview-resume-tips.md`：D 1/0.369，B 1，R 1，RR 1/-0.331 | 阈值移除；正式结果空 |
| gs-v1-0071 | factoid | `机器学习基础.pdf`：D 1/0.341，B 1，R 1，RR 1/0.426 | 阈值移除；正式结果空 |
| gs-v1-0073 | factoid | `机器学习基础.pdf`：D 2/0.471，B 1，R 2，RR 1/-0.528 | 阈值移除；正式结果空 |
| gs-v1-0074 | factoid | `机器学习基础.pdf`：D 7/0.480，B 1，R 2，RR 1/0.076 | 阈值移除；正式结果空 |
| gs-v1-0076 | factoid | `机器学习基础.pdf`：D 54/0.528（未进 Dense20），B 1，R 2，RR 1/-3.758 | BM25 已救回，随后阈值移除；正式结果空 |
| gs-v1-0082 | factoid | `interview-ai-engineer.md`：D 1/0.345，B 1，R 1，RR 1/0.195 | 阈值移除；正式结果空 |
| gs-v1-0087 | multi_span | `RAG技术入门.md`：D 1/0.392，B 1，R 1，RR 1/-1.541；`interview-ai-engineer.md`：D 3/0.410，B 6，R 5，RR 5/-2.710 | 两个目标均在候选池，均被阈值移除；正式结果空 |
| gs-v1-0088 | multi_span | `interview-python-core.md`：D 1/0.363，B 1，R 1，RR 1/1.196，最终第 1；`Python编程笔记.txt`：D 24/0.481，B 38，未进候选池 | 部分命中 1/2；未命中对的主因是 Dense/BM25 候选深度不足 |
| gs-v1-0089 | multi_span | `机器学习基础.pdf`：D 74/0.535，B 3，R 6，RR 6/-1.093；`RAG技术入门.md`：D 1/0.370，B 2，R 1，RR 1/0.301 | BM25 已救回两个目标，均被阈值移除；正式结果空 |
| gs-v1-0090 | multi_span | `Python编程笔记.txt`：D 1/0.396，B 3，R 1，RR 1/0.051；`Git命令手册.docx`：D 4/0.419，B 4，R 7，RR 4/-2.057 | 两个目标均在候选池，均被阈值移除；正式结果空 |
| gs-v1-0091 | multi_span | `interview-test-dev.md`：D 1/0.311，B 1，R 1，RR 1/1.746，最终第 1；`interview-behavioral.md`：D 6/0.421，B 2，R 4，RR 5/-2.032 | 部分命中 1/2；未命中对被阈值移除 |
| gs-v1-0093 | exact_term | `RAG技术入门.md`：D 1/0.338，B 1，R 1，RR 1/0.815 | 阈值移除；正式结果空 |
| gs-v1-0094 | ocr_table | `HTTP状态码速查表.docx`：D 2/0.432，B 1，R 2，RR 1/-0.934 | 阈值移除；正式结果空 |
| gs-v1-0097 | ocr_table | `HTTP状态码速查表.docx`：D 2/0.421，B 1，R 2，RR 1/0.871 | 阈值移除；正式结果空 |
| gs-v1-0098 | ocr_table | `HTTP状态码速查表.docx`：D 3/0.440，B 1，R 2，RR 1/0.850 | 阈值移除；正式结果空 |
| gs-v1-0103 | ocr_table | `Git常用命令对照表.xlsx`：D 3/0.440，B 1，R 2，RR 1/-1.189 | 阈值移除；正式结果空 |

## 模式统计

| 归因模式 | 未命中期望文档对 | 证据 |
| --- | ---: | --- |
| 已进入 RRF，rerank 阈值移除 | 21 / 22 | 目标在 RRF（第 1–7）且 rerank 后分数均小于 1.0；过滤后不在生产最终 sources |
| Dense/BM25 均未进 top-20 | 1 / 22 | gs-v1-0088 的 `Python编程笔记.txt`：Dense 24、BM25 38 |
| 语料/索引缺失 | 0 / 22 | 所有期望对均有 DB 文档 1 条，且在 Chroma 与 BM25 均有至少 1 个 chunk |
| similarity 阈值截杀 | 0 / 22 | 进入 Dense top-20 的目标距离均 ≤ 0.7；过滤前后 Dense 候选数均为 20 |
| RRF 淘汰已入池目标 | 0 / 22 | 除候选深度不足项外，所有目标均保留在 RRF top-20 |
| Dense 空导致 BM25-only 丢失 | 0 / 22（本次未触发） | 所有 19 题均有 Dense 结果；代码路径仍存在，见下节 |

四条 `ocr_table` 全部属于第一行模式：DOCX/XLSX 均已被解析为 4 个 chunk，目标在 Dense 前 3、BM25 第 1、RRF 第 2、rerank 第 1；没有任何证据表明它们是原生表格解析或分块失败。因此本次不把表格语料问题列为 Phase 2 parser/chunker 缺陷，也不改题目或语料。

## 事实、推断与限制

### 事实

1. 两个正式 rewrite-off run 的逐题 `details` 完全一致；基线缺口可重复。
2. 22 个未命中文档对中，21 个到达 RRF 与 rerank，但分数小于现行 `rerank_threshold=1.0`，最终被过滤。
3. `vector_search()` 在融合前以 `similarity_threshold` 过滤，`hybrid_search()` 在 Dense 为空时返回空列表，且 BM25 重建使用 legacy ID；这些均可由当前源码直接复核。
4. 现有正式结果对同一文件会同时出现 stable ID 与 `doc_*` legacy ID，和 BM25 重建后的 209 个 legacy ID 相一致。

### 推断

1. 当前基线的大部分 Recall@20 缺口的直接触发点是 rerank 阈值，而不是粗召回质量；因为目标在 RRF 的最高第 1–7 位且 rerank 自身也多为第 1 位。
2. 统一跨查询融合、跨通路 ID 去重及单次 rerank 可消除重复候选和变体间多次阈值处理的结构问题，但不能证明会在不校准阈值的情况下消除所有 21 个阈值移除项。

### 限制

- 正式 manifest 未保存 raw Dense/BM25/RRF 的完整中间排名，故这些阶段由保持相同隔离 DB/Chroma 的只读重放补充；冻结 manifest 仍是生产最终结果的权威证据。
- 本报告不将 rerank 阈值数值本身改为结论性修复：其默认值未获标定，且本任务及 T5 禁止调整全局默认值。它应在后续以独立实验和 Golden Set 数据校准。
- 候选深度不足仅在一条文档对中观察到；不应据此扩大 `retrieval_top_k` 或修改指标公式，除非 T5 的受控融合实验给出不低于基线的证据。

## 对 T5 的融合层建议

1. 按 flag-on 规格让原问题与改写变体先各自产出 Dense/BM25 候选，再合入单一候选池；不要在每个变体内提前 rerank 或提前截断。
2. 在 BM25 重建与 Dense 之间统一 `chunk_id`，按该稳定 ID 去重再做一次 RRF。这样才能避免同一 chunk 以 stable/legacy 两个 ID 占据候选名额。
3. 保留 BM25-only 候选：即使本次 19 题没有触发 Dense 空分支，`hybrid_search()` 的现有空返回仍违反 P1-04 红线，须用测试固化。
4. 将 rerank 上提为对统一候选池、以原始问题执行的一次调用；这属于融合阶段重构，避免变体间重复 rerank/重复阈值过滤。
5. 按既定决策树增加「similarity 作为融合后可选过滤」实验组，默认关闭；本组没有 0.7 截杀证据，不能以修复名义改变它的全局默认值。
6. 在 T5 评测报告中单列「RRF 入池但 rerank 阈值移除」数量。若 flag-on 五指标不低于基线，才将统一融合作为可推广方案；否则保持默认关闭并如实记录部分达成。

## Phase 2 跟踪建议

本次没有发现需立即修复的解析/分块缺陷。Phase 2 仍应为 PDF/DOCX/XLSX/CSV 保存块级 provenance（页、sheet、行/表格坐标）并为表格增加解析质量回归测试；这是可观测性与长期质量工作，不是为了回填或重写这 15 条 `ocr_table` 标注。
