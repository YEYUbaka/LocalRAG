# P1-04 统一多查询融合 — 续跑清单

> 状态：实现已完成，评测未跑（等机器空闲时执行）。
> 更新日期：2026-08-29。本文件为工作清单，任务完成后可归档或删除。

## 1. 已完成

- [x] 分支 `feat/P1-04-unified-fusion`，实现提交 `dac78d4`
- [x] 手册 5 个实施要点全部覆盖：
  1. Feature flag `unified_fusion_enabled`（config.py + .env.example，默认 false）
  2. `similarity_threshold` 改为融合后可选过滤（`post_fusion_similarity_filter_enabled`，默认关）
  3. rerank 从 `hybrid_search` 内部抽出为 `rerank_candidates`，`unified_search` 以原始问题单次精排
  4. `generalized_rrf` 统一候选池 + 稳定 ID 去重（chunk_id 优先）
  5. BM25-only 命中保留有测试固化（`backend/tests/test_unified_fusion.py`）
- [x] `run_evals.py` 支持 `--enable-unified-fusion` / `--enable-post-fusion-similarity-filter` 实验 flag
- [x] 后端测试 256 passed（localrag conda env，JWT_SECRET 已设置）
- [x] 隔离评测环境就绪（见 §4），语料已索引 24/24

## 2. 待办（按顺序，已按 2026-08-29 独立评审结论修订）

- [ ] **[P1] 补测试**：Dense 完全为空时 BM25-only 保留的字面边界用例；flag-off 等价性回归（flag=False 断言仍走逐查询 hybrid_search）；rerank 异常降级为 RRF 序的用例
- [ ] **[P2] run_evals manifest 补记 ambient 参数**（rerank_enabled/rerank_threshold/similarity_threshold/bm25_weight/hybrid_search），防 on/off 对比静默偏斜；同步 test_run_evals.py 的确定性参数测试
- [ ] 跑 flag off 评测 ×1~2 轮（命令见 §4）
- [ ] 跑 flag on 评测 ×1~2 轮（加 `--enable-unified-fusion`）；报告中说明局限：`--no-rewrite` 下 on 组只覆盖单查询融合路径（去内联阈值+去重+后过滤+单次精排），多变体统一池需 rewrite-on 才在评测路径上
- [ ] 对比基线（§5），指标不得低于基线；若 on 组有回退，先修再跑
- [ ] 报告中说明 `rerank_threshold` 生产默认 1.0 对低分 BM25-only 命中的既有影响（沿袭 master 语义，非本 PR 引入）
- [ ] 写 P1-04 评测报告（建议 `docs/quality/p1-04-acceptance.md`，含 run 目录、耗时、五指标表）
- [ ] 更新 `docs/quality/phase-1-plan.md` §7 状态表 P1-04 行
- [ ] 评测报告与状态表随本 PR 落地后，方可点合并（P1-04 §4 是硬门槛，不拆后续 PR）
- [ ] 合并前考虑：启用 UNIFIED_FUSION_ENABLED 的部署需重索引旧库（pre-P1-03 文档的 Chroma metadata 无 chunk_id，融合去重会失效），在报告或 .env.example 注释中声明
- [ ] 合并后小项（可拆 follow-up）：.env.example 注明 POST_FUSION_SIMILARITY_FILTER_ENABLED 依赖 unified_fusion；`generalized_rrf` 回退键改名 `_fusion_key` 避免与 P1-05 chunk_id 语义混淆

## 3. 环境坑（跑之前必读）

- Git Bash 默认 python 是 3.9，**必须用** `D:/miniconda3/envs/localrag/python.exe`
- pytest 需 `export JWT_SECRET='phase-zero-ci-secret-with-at-least-32-bytes'`
- 评测命令后台跑时 `| tail` 会吞真实退出码，看日志文件末尾确认「评测完成」
- 单轮评测约 30–40 分钟且 CPU 满载，机器会热；确保接电、别休眠（休眠会中断且耗时数据作废）
- 主库 `localrag` 已于 2026-08-29 升级到 alembic head `20260802_0004`（本清单建立时完成）；评测仍用 §4 隔离库，不要连主库
- 主库升级过程：此前版本号被误标为 0004 但 DDL 从未执行（实际停在 0001）。已 `alembic stamp 20260802_0001` 后重放 0002→0004。
  0002 因多用户 + 遗留 NULL 归属行按设计 fail-closed 一次；证据核查后人工补归属（KB 1「默认知识库」与 6 条
  遗留会话归 user 1=YEYU，唯一人类用户，4 份文档全在其名下；评测用户 2147483647 仅拥有 KB 2），随后重放成功。
  升级后已验证：documents 三列齐全、ingestion_jobs 表存在、md5 全局唯一已换为 `uq_documents_scope_md5` 复合唯一，ORM 读写正常。

## 4. 隔离评测环境与命令

已就绪（勿删）：

- MySQL 库 `localrag_p104_eval_20260828`，已迁移到 head `20260802_0004`
- 语料已索引：该库 documents 表 24 行；Chroma 集合在 `data/eval_p104_isolated/chromadb`

命令（Git Bash，仓库根目录）：

```bash
export JWT_SECRET='phase-zero-ci-secret-with-at-least-32-bytes'
export DATABASE_URL='mysql+pymysql://root:<见本地 .env>@localhost:3306/localrag_p104_eval_20260828'
export DATA_DIR='./data/eval_p104_isolated'

# off 组（对照，跑 2 轮取 run1/run2）
D:/miniconda3/envs/localrag/python.exe backend/scripts/run_evals.py \
  --golden backend/evals/golden_set/v1.jsonl \
  --label p104-unified-fusion-off-run1 --no-rewrite

# on 组（label 改 p104-unified-fusion-on-run1/-run2）
D:/miniconda3/envs/localrag/python.exe backend/scripts/run_evals.py \
  --golden backend/evals/golden_set/v1.jsonl \
  --label p104-unified-fusion-on-run1 --no-rewrite --enable-unified-fusion
```

索引已建好会自动跳过（同 MD5 幂等），直接进入检索评测。run 产物落 `backend/evals/runs/`（不入库）。

## 5. 基线对照数字

来源 `backend/evals/runs/20260823T*baseline-v1-*` 与 `docs/quality/phase-1-baseline.md`。
Golden Set 120 条（SHA256 `f50394ab…`），语料 24 份（SHA256 `7c823244…`）。

| 指标 | rewrite off | rewrite on | 门槛 |
| --- | ---: | ---: | --- |
| Recall@20 | 0.820000 | 0.820000 | ≥0.90（未达） |
| MRR@10 | 0.803333 | 0.803333 | ≥0.70（达标） |
| nDCG@10 | 0.810000 | 0.810000 | ≥0.75（达标） |
| rerank Recall@5 | 0.820000 | 0.820000 | ≥0.85（未达） |
| Unanswerable Recall | 1.000000 | 1.000000 | ≥0.90（达标） |

P1-04 验收线：**on 组任一指标不得低于上表 off 列对应值**。Recall@20 / rerank Recall@5 本就未达门槛，
P1-04 不要求补齐门槛，只要求不回退。
