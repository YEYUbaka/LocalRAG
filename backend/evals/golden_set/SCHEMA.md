# Golden Set v1 Schema

`v1.jsonl` 使用 UTF-8 JSON Lines：每个非空行都是一个完整 JSON 对象。正式集固定为 120 行，ID 从 `gs-v1-0001` 连续到 `gs-v1-0120`。

## 字段

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `id` | string | `gs-v1-` 加四位序号；全局唯一且连续 |
| `question` | string | 非空、无重复的问题文本 |
| `type` | string | `factoid` / `multi_span` / `exact_term` / `ocr_table` / `unanswerable` |
| `source_docs` | string[] | 可回答题至少一个受控语料文件；不可回答题为空数组 |
| `locator` | string | 可回答题填写小节、页码、表号、工作表或数据行；不可回答题为空字符串 |
| `expected_answer_points` | string[] | 可回答题 2–5 条非空要点；不可回答题严格为 `["库内无相关依据"]` |
| `unanswerable` | boolean | 仅 `type=unanswerable` 时为 `true` |
| `notes` | string | 标注与复核备注 |

## 固定配额

| 题型 | 数量 |
| --- | ---: |
| `factoid` | 55 |
| `multi_span` | 15 |
| `exact_term` | 15 |
| `ocr_table` | 15 |
| `unanswerable` | 20 |

`ocr_table` 在 Phase 1 指依据 DOCX、XLSX、CSV 或 PDF 原生数字表格出题。扫描件和图片 OCR 样本延后到 Phase 2 OCR 能力落地时补充。

## 校验

```powershell
python backend/scripts/validate_golden.py backend/evals/golden_set/v1.jsonl
```

格式校验只是最低门槛；来源存在性、locator、配额、问题去重和不可回答题语料搜索仍需单独审计。
