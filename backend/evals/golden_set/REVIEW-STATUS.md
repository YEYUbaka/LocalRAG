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

## 解析链路缺陷与处理结果

新增表格语料本身已通过原生结构和可视化检查。P1-05 首次真实基线确认并修复以下生产解析缺陷，Golden 问题和语料事实未做迎合性修改：

1. `Git常用命令对照表.xlsx`：原 `UnstructuredExcelLoader` 因环境缺少 `unstructured` 抛出 `ModuleNotFoundError`；现使用项目已有 `openpyxl` 按工作表读取原生单元格。
2. `Linux文本处理三剑客.csv`：原 `CSVLoader` 在中文 Windows 上按 GBK 解码并抛出 `UnicodeDecodeError`；现显式使用 UTF-8。
3. `HTTP状态码速查表.docx`：现有 `Docx2txtLoader` 可解析，抽取 1 个文档、1522 个字符。

修复后 24/24 份语料成功进入真实索引。15 条 `ocr_table` 的 rewrite-off Recall@20 为 0.733333，4 条未命中已如实记录在 `docs/quality/phase-1-baseline.md`；不得为了提高指标改变题目或语料事实。
