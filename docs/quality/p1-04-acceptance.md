# P1-04 统一多查询融合 — 评测验收报告

> 状态：完成（验收通过）
> 执行日期：2026-09-24
> 关联清单：[p1-04-todolist.md](p1-04-todolist.md)
> 基线依据：[phase-1-baseline.md](phase-1-baseline.md)（rewrite-off，2026-08-23）

## 1. 结论

`unified_fusion_enabled` 的 on 组两轮**没有任何指标低于 off 组**，P1-04 验收通过。

- **off 组精确复现基线**：两轮的五项指标与 2026-08-23 基线逐位一致（6 位小数），证明本次执行环境与基线环境等价，on/off 对比成立。
- **on 组无回退且小幅提升**：Recall@20、rerank Recall@5、Unanswerable Recall 持平；MRR@10 由 0.803333 提升到 0.810000（+0.006667），nDCG@10 由 0.810000 提升到 0.815237（+0.005237）。
- **确定性成立**：同组两轮逐题 payload 完全相同（off-run1≡off-run2，on-run1≡on-run2）。
- **Phase 1 门槛**：Recall@20（0.820000 < 0.90）与 rerank Recall@5（0.820000 < 0.85）仍未达门槛。这是 P1-04 之前就存在的基线缺口，[p1-04-todolist.md](p1-04-todolist.md) §5 明确 P1-04 不要求补齐门槛、只要求不回退，故不影响本次验收判定。

**本报告不构成「可以打开生产开关」的建议**：`unified_fusion_enabled` 是否转正由维护者决定，且需先满足 §6 的重索引前提。

## 2. 测试输入与环境

| 项目 | 值 |
| --- | --- |
| 检索实现 commit | `6d8a45dff2e0d859576d33d49d164bff4fc4153d` |
| Golden Set | `backend/evals/golden_set/v1.jsonl`，120 条 |
| Golden SHA-256 | `f50394abb9707afe3ed133d85ba0241287a1e03ccc12235b90524cca4a4d5baf` |
| 语料 | `test_docs/` 顶层 24 份生产解析器支持的文件 |
| 语料 SHA-256 指纹 | `7c823244ed4caa2a353112d51bdab5f7537986040c3357fef95e891f26066757` |
| 执行平台 | Linux 5.4.0-162-generic x86_64 / glibc 2.31（AutoDL 容器），48 核，RTX 3080 Ti |
| Python | 3.11.16 |
| torch | 2.12.0+cu126（GPU）— 基线为 2.12.0+cpu |
| ChromaDB | 1.5.9（嵌入式 `PersistentClient`，隔离目录） |
| FlagEmbedding | 1.4.2 — 基线为 1.4.0 |
| LangChain | 1.3.16 |
| SQLAlchemy | 2.0.35 |
| 数据库 | 隔离 MySQL 8.0.42 库 `localrag_p104_eval`，Alembic head=`20260802_0004` |
| 评测租户 | 保留的本地专用 tenant（`user_id=2147483647`，`kb_id=1`） |

两份评测输入（Golden Set 与语料）的 SHA-256 与基线报告**逐字符一致**，且运行前后均未修改。

### 2.1 执行时生效的检索参数

评测期间由 `temporary_eval_settings` 覆盖：`retrieval_top_k=20`、`rerank_top_k=20`、`query_rewrite_enabled=False`、`web_search_enabled=False`、`temperature=0`。其余为生产默认值，与本地基线环境逐项一致：

| 参数 | 值 | 参数 | 值 |
| --- | --- | --- | --- |
| chunk_size | 500 | rerank_enabled | True |
| chunk_overlap | 50 | rerank_threshold | 1.0 |
| hybrid_search | True | similarity_threshold | 0.7 |
| bm25_weight | 0.5 | post_fusion_similarity_filter_enabled | False |
| retrieval_top_k | 20 | unified_fusion_enabled（off 组） | False |
| rerank_top_k | 5 | unified_fusion_enabled（on 组） | True |

> **说明**：`run_evals.py` 的 manifest 只记录 `unified_fusion_enabled` / `post_fusion_similarity_filter_enabled` 等显式实验参数，**不记录** `rerank_enabled`、`rerank_threshold`、`similarity_threshold`、`bm25_weight`、`hybrid_search` 这些 ambient 参数（清单 §2 的 P2 待办）。上表由评测前在服务器上直接读取 `settings` 得出并留档于此，防止 on/off 对比静默偏斜。

## 3. 执行结果

四轮正式运行目录（`backend/evals/runs/`，不入库）：

| 轮次 | run 目录 | 耗时 |
| --- | --- | ---: |
| off-run1 | `20260923T192119.324483Z-p104-unified-fusion-off-run1` | 28 s |
| off-run2 | `20260923T192203.778237Z-p104-unified-fusion-off-run2` | 28 s |
| on-run1 | `20260923T192242.029474Z-p104-unified-fusion-on-run1` | 29 s |
| on-run2 | `20260923T192320.859776Z-p104-unified-fusion-on-run2` | 28 s |

命令：

```bash
# 环境变量：JWT_SECRET、DATABASE_URL（隔离库）、DATA_DIR（隔离目录）
python torch_first.py backend/scripts/run_evals.py \
  --golden backend/evals/golden_set/v1.jsonl \
  --label p104-unified-fusion-off-run1 --no-rewrite
# on 组追加 --enable-unified-fusion
```

- 语料索引为幂等复用（四轮均 `indexed=0, skipped=24`），四轮面对**完全相同**的 Chroma 集合与 BM25 索引。
- 耗时从基线的 2192 s 降到 28–29 s，原因是本次在 GPU 上执行 embedding 与 reranker（见 §6 的等价性讨论）。

### 3.1 确定性校验

对每轮 manifest 的逐题 payload（`question_id`/`hit_ranks`/五项指标）做全等比较：

- `off-run1` vs `off-run2`：**完全一致**
- `on-run1` vs `on-run2`：**完全一致**
- off 与 on 之间：不同（符合预期，两组参数不同）

## 4. 五指标与门槛判定

| 组别 | Recall@20 ≥0.90 | MRR@10 ≥0.70 | nDCG@10 ≥0.75 | rerank Recall@5 ≥0.85 | Unanswerable Recall ≥0.90 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 基线（2026-08-23 rewrite-off） | 0.820000（失败） | 0.803333（通过） | 0.810000（通过） | 0.820000（失败） | 1.000000（通过） |
| off-run1 | 0.820000（失败） | 0.803333（通过） | 0.810000（通过） | 0.820000（失败） | 1.000000（通过） |
| off-run2 | 0.820000（失败） | 0.803333（通过） | 0.810000（通过） | 0.820000（失败） | 1.000000（通过） |
| **on-run1** | 0.820000（失败） | **0.810000**（通过） | **0.815237**（通过） | 0.820000（失败） | 1.000000（通过） |
| **on-run2** | 0.820000（失败） | **0.810000**（通过） | **0.815237**（通过） | 0.820000（失败） | 1.000000（通过） |

### 4.1 P1-04 验收线判定

验收线（清单 §5）：**on 组任一指标不得低于 off 组对应值**。

| 指标 | off | on | 差值 | 判定 |
| --- | ---: | ---: | ---: | --- |
| Recall@20 | 0.820000 | 0.820000 | +0.000000 | 不回退 ✅ |
| MRR@10 | 0.803333 | 0.810000 | **+0.006667** | 不回退 ✅ |
| nDCG@10 | 0.810000 | 0.815237 | **+0.005237** | 不回退 ✅ |
| rerank Recall@5 | 0.820000 | 0.820000 | +0.000000 | 不回退 ✅ |
| Unanswerable Recall | 1.000000 | 1.000000 | +0.000000 | 不回退 ✅ |

**判定：通过。** 两轮结果一致。

## 5. 分题型结果

仅统计 100 条可回答题（`unanswerable` 20 条不参与前四项指标）。

| 题型 | 数量 | 组别 | Recall@20 | MRR@10 | nDCG@10 | rerank Recall@5 |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| factoid | 55 | off | 0.872727 | 0.848485 | 0.854545 | 0.872727 |
| factoid | 55 | **on** | 0.872727 | **0.854545** | **0.859307** | 0.872727 |
| exact_term | 15 | off | 0.800000 | 0.711111 | 0.733333 | 0.800000 |
| exact_term | 15 | **on** | 0.800000 | **0.733333** | **0.750791** | 0.800000 |
| multi_span | 15 | off | 0.733333 | 0.800000 | 0.800000 | 0.733333 |
| multi_span | 15 | **on** | 0.733333 | 0.800000 | 0.800000 | 0.733333 |
| ocr_table | 15 | off | 0.733333 | 0.733333 | 0.733333 | 0.733333 |
| ocr_table | 15 | **on** | 0.733333 | 0.733333 | 0.733333 | 0.733333 |

提升集中在 `exact_term`（MRR +0.022222、nDCG +0.017458）与 `factoid`（MRR +0.006060、nDCG +0.004762）；`multi_span` 与 `ocr_table` 持平。Recall@20 与 rerank Recall@5 各题型均持平——即**命中集合不变、命中名次前移**，与「取消向量相似度预过滤后更多相关块进入融合池，再由精排前移」的预期一致。

## 6. 方法学限制与说明

以下几点限定本报告结论的适用范围，不应被省略引用。

1. **on 组在 `--no-rewrite` 下只覆盖单查询融合路径。** 本次 on 组实际检验的三项行为是：①向量相似度阈值预过滤被移除（`vector_search(..., apply_similarity_threshold=False)`）；②BM25 空 / 向量空的提前返回分支不生效（BM25-only 命中得以保留）；③按稳定 `chunk_id` 去重。**跨查询统一候选池（多变体单池融合）只有 rewrite-on 才走得到**，本次未覆盖。这正是清单 §2 要求报告中声明的局限。

2. **GPU 与基线的 CPU 执行等价性，由结果而非假设保证。** 基线在 CPU（`torch 2.12.0+cpu`）上产生，本次在 GPU（`torch 2.12.0+cu126`，reranker 启用 fp16）上执行。off 组两轮**精确复现**基线五项指标，说明在本 Golden Set 上该设备/精度差异未改变任何名次；但这是经验结论，不构成「设备无关」的一般保证。torch 版本与基线一致（2.12.0），仅构建变体不同。

3. **`rerank_threshold = 1.0` 的既有影响沿袭 master 语义。** 生产默认阈值为 1.0，而 `FlagReranker.compute_score` 返回的是未过 sigmoid 的 logits，低分命中会被阈值直接过滤。该行为在基线与 on/off 两组中完全一致，**不是 P1-04 引入**；但它会掩盖「BM25-only 命中被保留」这部分改动的部分收益，评估后续 retrieval 改动时需一并考虑。

4. **FlagEmbedding 版本差异。** 服务器为 1.4.2，基线为 1.4.0。off 组精确复现表明该差异未影响结果。

5. **Rewrite-on 路径未评测。** 与基线报告一致，rewrite-on 受外部 LLM 可用性制约，本次仍未补齐；因此「多变体统一池」的收益尚无数值证据。

## 7. 执行环境问题记录（服务器侧）

本次在 AutoDL 容器（Ubuntu 20.04 / 驱动 535.104.05）执行，遇到并解决了两个环境问题，均**不涉及应用代码改动**，记录于此供后续复现参考。

### 7.1 torch 的 CUDA 版本必须匹配驱动

PyPI 上最新 `torch` 为 **CUDA 13.0** 构建（`nvidia-*-cu13`），而该机驱动仅支持 **CUDA 12.2**，`torch.cuda.is_available()` 为 `False`。改用 `torch 2.12.0+cu126`（`mirrors.aliyun.com/pytorch-wheels/cu126/`）后 GPU 可用，且版本号与本地基线一致。

### 7.2 原生库加载顺序导致的 segfault

直接运行 `run_evals.py` 会在 `default_dependencies()` 阶段收到 SIGSEGV（exit 139），`faulthandler` 无法给出 Python 栈（崩在原生初始化）。该环境中同时存在多个 OpenMP 运行时：`torch/lib/libgomp.so.1`、scikit-learn 自带的 `libgomp-e985bcbb.so`，以及 chromadb 的 Rust bindings。经对照实验：

| 方案 | 结果 |
| --- | --- |
| 原样 | ✗ SIGSEGV |
| `OMP_NUM_THREADS=1` | ✗ SIGSEGV |
| `KMP_DUPLICATE_LIB_OK=TRUE` | ✗ SIGSEGV |
| **先 `import torch` 再运行目标脚本** | **✓ 正常** |

因此评测通过一个薄包装 `torch_first.py`（仅 `import torch` 后用 `runpy` 执行目标脚本）启动。**该包装不修改任何被评测代码，也不改变检索逻辑**，只调整原生库初始化顺序。这是本机的环境缺陷，不属于项目缺陷，但若后续在其他 Linux 环境复现同类崩溃可参照此结论。

## 8. 待办

1. **合并/转正前提**：启用 `UNIFIED_FUSION_ENABLED` 的部署需**重索引旧库**——pre-P1-03 文档的 Chroma metadata 没有 `chunk_id`，融合去重会失效。需在 `.env.example` 注释或部署文档中声明。
2. **rewrite-on 路径补测**：外部 LLM 改写可用后，补跑 on/off 的 rewrite-on 两组，验证多变体统一池的收益。
3. **manifest 补记 ambient 参数**（清单 §2 的 P2 项）：让 `run_evals.py` 记录 `rerank_enabled`/`rerank_threshold`/`similarity_threshold`/`bm25_weight`/`hybrid_search`，避免后续对比再次依赖人工留档（本报告 §2.1 即为人工留档）。
4. **Phase 1 未达门槛项**：Recall@20 与 rerank Recall@5 仍未达门槛，属 P1-04 范围之外，按原计划另行处理。
5. run 产物保留在已忽略的 `backend/evals/runs/`，不提交仓库。
