# Golden Set 机器草稿

> **机器起草、待人工复核。不得直接复制为正式 `v1.jsonl`。**

本目录是 P1-01 的标注辅助产物。`interview-machine-draft.jsonl` 基于 `test_docs/` 中全部 17 篇 `interview-*.md` 起草，共 56 条：

| 题型 | 数量 |
| --- | ---: |
| factoid | 25 |
| multi_span | 10 |
| exact_term | 13 |
| unanswerable | 8 |
| 合计 | 56 |

本草稿不包含 `ocr_table`。PDF 与 DOCX 的页码、表格及 OCR 题必须由人工阅读原始渲染结果后标注。

人工复核至少需要完成：

1. 逐条确认问题表达没有直接照抄标题，且答案要点都能在 locator 指向的位置找到。
2. 在当前完整评测语料中逐条搜索 unanswerable 问题，确认不存在可支持回答的依据。
3. 实际运行检索，检查可回答题能否命中全部预期文档，并修正含糊或过宽的问题。
4. 完成交叉抽查和正式配额编排后，才能分配最终 ID 并写入 `backend/evals/golden_set/v1.jsonl`。

格式校验命令：

```powershell
& 'D:\miniconda3\envs\localrag\python.exe' 'E:\AI_projects\LocalRAG\backend\scripts\validate_golden.py' 'E:\AI_projects\LocalRAG\backend\evals\golden_set\drafts\interview-machine-draft.jsonl'
```
