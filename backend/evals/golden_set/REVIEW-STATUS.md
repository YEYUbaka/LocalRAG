# Golden Set v1 Review Status

> 状态：机器起草，建议人工抽查 ≥10% 后视为可信基线。

正式集共 120 条，至少应由人工抽查 12 条后，才能把它作为可信基线。当前自动检查只能证明 JSONL 结构、精确配额、连续 ID、来源文件存在和问题无重复，不能替代对事实、locator、不可回答性和问题表述的人工判断。

## Integrator 裁决

- 2026-08-23 裁决采用补充真实表格语料方案，题型名和 15 条配额不变。
- Phase 1 的 `ocr_table` 指依据 DOCX、XLSX、CSV 或 PDF 原生数字表格出题。
- 扫描件和图片 OCR 样本延后到 Phase 2 OCR 能力落地时补充。
- 原始 PDF/DOCX 无表格或图片的停线记录保留在 `docs/quality/p1-01-ocr-table-blocker.md`。

## 建议抽查样本

建议至少覆盖以下 12 条：

- factoid：`gs-v1-0001`、`gs-v1-0063`、`gs-v1-0071`
- multi_span：`gs-v1-0006`、`gs-v1-0087`、`gs-v1-0091`
- exact_term：`gs-v1-0009`、`gs-v1-0092`
- ocr_table：`gs-v1-0094`、`gs-v1-0099`、`gs-v1-0104`
- unanswerable：`gs-v1-0118`

抽查应逐条确认问题可读、答案要点正确、locator 能定位原文、来源文档合理；不可回答题还应确认 24 份受控语料均无答案依据。

## 已知解析链路缺陷

新增表格语料本身已通过原生结构和可视化检查，但当前生产解析链路存在以下缺陷，必须在基线中如实暴露，不能通过改写 Golden 问题规避：

1. `Git常用命令对照表.xlsx`：`UnstructuredExcelLoader` 因环境缺少 `unstructured` 抛出 `ModuleNotFoundError`；文件可由 openpyxl 和 Microsoft Excel 正常读取。
2. `Linux文本处理三剑客.csv`：`CSVLoader` 未显式指定 UTF-8，在中文 Windows 上按 GBK 解码并抛出 `UnicodeDecodeError`；文件按 UTF-8 使用标准库可完整读取 16 行、4 列。
3. `HTTP状态码速查表.docx`：现有 `Docx2txtLoader` 可解析，抽取 1 个文档、1522 个字符。

解析问题和数据问题已经区分记录；不得为了提高指标改变题目或语料事实。
