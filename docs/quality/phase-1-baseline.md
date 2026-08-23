# Phase 1 检索基线报告

> 状态：已执行，指标暂缓（全局 MD5 唯一约束阻断）
> 首次执行日期：2026-08-23
> 补跑条件：P1-05 租户级去重迁移合入后

## 1. 结论

rewrite-off 与 rewrite-on 两组真实基线命令均已执行，但都在评测语料索引阶段触发 `Document.md5_hash` 全局唯一约束冲突，并在修改其他租户数据前安全停止。当前没有生成 run 目录或 `summary.json`，五项指标和逐字节确定性均不可测定。

这是任务书明确允许暂缓的已知阻塞项。P1-05 完成租户级去重修复后，必须按本报告第 6 节补跑四次并用真实结果替换“未测定”；不得推测指标，不得修改 Golden 问题迎合解析或检索能力。

## 2. 测试输入与环境

| 项目 | 值 |
| --- | --- |
| Git commit | `b9a6c42b38e691b8d672907c6cec3d0123e40355`（PR #10 合并提交） |
| Golden Set | `backend/evals/golden_set/v1.jsonl`，120 条 |
| Golden SHA-256 | `f50394abb9707afe3ed133d85ba0241287a1e03ccc12235b90524cca4a4d5baf` |
| 语料 | `test_docs/` 顶层 24 份生产解析器支持的文件 |
| 语料 SHA-256 指纹 | `7c823244ed4caa2a353112d51bdab5f7537986040c3357fef95e891f26066757` |
| Python | 3.11.15 |
| 平台 | Windows 10.0.26200 |
| ChromaDB | 1.5.9，嵌入式 `PersistentClient` |
| FlagEmbedding | 1.4.0 |
| LangChain | 1.3.16 |
| SQLAlchemy | 2.0.35 |
| 评测租户 | 保留的本地专用 tenant，未创建登录用户 |

## 3. 执行结果

### 3.1 rewrite off

```powershell
python backend/scripts/run_evals.py `
  --golden backend/evals/golden_set/v1.jsonl `
  --label baseline-v1
```

结果：失败退出，未生成 run 目录。冲突文件为 `Git命令手册.docx`，MD5 为 `10f8c5fc66e1a498f72238a12fbbda74`；同内容文档已存在于非评测租户。

### 3.2 rewrite on

```powershell
python backend/scripts/run_evals.py `
  --golden backend/evals/golden_set/v1.jsonl `
  --label baseline-rewrite-on `
  --enable-rewrite
```

结果：在同一索引前置阶段以同一 MD5 冲突失败退出，尚未调用查询改写，未生成 run 目录。

## 4. 五指标与门槛判定

| 组别 | Recall@20 ≥0.90 | MRR@10 ≥0.70 | nDCG@10 ≥0.75 | rerank Recall@5 ≥0.85 | Unanswerable Recall ≥0.90 |
| --- | ---: | ---: | ---: | ---: | ---: |
| rewrite off | 未测定 | 未测定 | 未测定 | 未测定 | 未测定 |
| rewrite on | 未测定 | 未测定 | 未测定 | 未测定 | 未测定 |

门槛判定：两组均为“不可判定”，不能视为通过或失败。citation precision 与 locator round-trip 属于上游设计的后续契约指标，不在当前评测 CLI 的五指标输出范围内。

## 5. 根因与后续风险

### 5.1 当前阻塞：全局 MD5 去重

现有评测索引按 MD5 全局查询 `Document`。相同内容已被其他用户/知识库摄取时，评测器为保护用户数据主动抛出 `CorpusIndexError`。数据库模型的全局唯一约束也不允许评测租户新增同 MD5 行。

P1-05 必须把去重边界改为租户作用域，并保持迁移 additive、可升级、可降级。修复后评测租户应能独立索引同内容文档，且不得删除或复用其他租户记录。

### 5.2 预计下一阻塞：表格解析链路

P1-01 已把以下生产解析缺陷写入 `backend/evals/golden_set/REVIEW-STATUS.md`：

- XLSX 使用 `UnstructuredExcelLoader`，当前环境缺少 `unstructured`。
- CSV 使用默认系统编码，中文 Windows 上对 UTF-8 语料按 GBK 解码失败。
- DOCX 可由 `Docx2txtLoader` 正常解析。

MD5 修复后若全量索引继续因 XLSX/CSV 失败，应区分解析能力与数据问题并如实记录；不得改写表格题或删除语料来获得更好指标。

## 6. P1-05 合入后的强制补跑

1. rewrite-off 连续运行两次，保留两个不同 run 目录，比较 `summary.json` 逐字节一致。
2. rewrite-on 连续运行两次，比较 `summary.json` 逐字节一致；若查询改写存在抖动，记录具体差异。
3. 把四个 run 目录相对路径、五指标、总耗时、commit 和新的语料指纹回填本报告。
4. 对照第 4 节门槛逐项给出通过/失败，不把“完成运行”误写成“达到门槛”。
5. run 产物继续留在已忽略的 `backend/evals/runs/`，不提交仓库。
