# LocalRAG 竞品差距与后续路线图

> 调研日期：2026-08-02  
> 范围：RAGFlow、Dify、AnythingLLM、Open WebUI、PrivateGPT、Kotaemon、Quivr；仅采用官方文档与官方仓库。  
> 说明：本报告取代 `plans/competitor-analysis-report.md` 中已经过时的缺失项判断。

## 1. 结论先行

LocalRAG 已经越过“基础 RAG Demo”阶段。当前代码具备多格式文档、ChromaDB、本地中文 Embedding、BM25 + 向量 RRF、Reranker、查询改写、多知识库、标签/全文搜索、URL/批量/整站导入、引用、图片理解、JWT、多用户和 Docker Compose。核心检索链路约处于成熟开源产品的 **70%–80% 基础能力段**。

真正的差距不是再堆一种检索算法，而是：

1. **安全隔离尚未闭环**：存在跨用户资源 ID 校验缺口、全局标签/设置、硬编码 JWT 密钥和 URL 抓取 SSRF 风险。
2. **无法证明质量变好**：没有 Golden Set、Recall@K/MRR/nDCG、faithfulness、citation precision 或 CI 回归门禁。
3. **复杂文档理解较弱**：仅递归字符分块，缺 OCR、版面/表格/图片结构恢复、父子分块和可视化 chunk 调试。
4. **摄取和运行不够可靠**：FastAPI `BackgroundTasks` 无持久队列、重试、取消和宕机恢复；BM25 为单进程内存索引。
5. **缺少产品平台层**：没有全链路 trace、反馈闭环、增量同步、项目化上下文、标准 API Key、MCP/工具与可控记忆。

战略建议：定位为“**轻量、中文优化、隐私优先、可验证质量的个人/小团队 RAG**”，不要正面复制 Dify 的通用低代码平台。RAGFlow 官方自托管最低要求为 4C/16GB/50GB，LocalRAG 的低复杂度本身是优势。

## 2. 代表项目对标

| 项目 | 强项 | LocalRAG 应借鉴 | 不建议照搬 |
|---|---|---|---|
| RAGFlow | DeepDoc/VLM/OCR、复杂版面、模板/父子分块、可视化 chunk、融合检索、Agent | 解析质量、chunk 干预、检索 trace | 重型 ES/MinIO/Redis 全家桶、过早 GraphRAG |
| Dify | 知识流水线、Workflow/Chatflow、插件、LLMOps、Workspace/RBAC | 可编排摄取、生产日志、权限模型 | 直接建设通用低代码平台 |
| AnythingLLM | 本地优先、Workspace、Agent/MCP、记忆、模型路由、定时任务 | 低摩擦桌面体验、工具权限、浏览器采集 | 功能全集式扩张 |
| Open WebUI | 8 类提取引擎、Focused/Full Context、agentic knowledge、RBAC/SSO、OTel | 多检索模式、精确 grep/行引用、可观测性 | 服务器任意 Python 插件信任模型 |
| PrivateGPT | API-first、Celery 异步摄取、任务状态、Phoenix/Opik trace | 稳定 API、可靠任务生命周期、请求调试 | 将 Workbench 当生产多用户 UI |
| Kotaemon | Docling/OCR/表格、PDF 页内高亮、低相关警告、可插拔 pipeline | 结构化解析、精确引用、置信度 UX | 早期引入多种 GraphRAG |
| Quivr Core | YAML 声明式 rewrite→retrieve→generate 工作流 | 可版本化 RAG 配置、插件接口 | 依赖旧版 Quivr 产品印象 |

## 3. 当前工程风险（P0）

以下不是竞品“锦上添花”，而是上线前门槛：

- `backend/app/auth.py:12` 硬编码 `SECRET_KEY`；应从环境或 secret store 注入，生产缺失时拒绝启动，并支持轮换。
- `POST /api/chat` 直接接受 `conversation_id`/`kb_id`，进入检索前未验证归属；上传和 URL 导入也未确认目标知识库属于当前用户。
- `backend/app/api/tags.py` 的标签和文档关联未按用户过滤；`/api/settings` 无认证且修改全局配置。
- `web_fetcher.py` 跟随重定向但未阻止 loopback、内网、link-local、云 metadata IP；需要每次 DNS/redirect 重新校验，并限制协议、响应类型和字节流。
- `main.py` 启动时执行手写 DDL；应改用 Alembic。文档任务需幂等，避免重处理产生重复向量。
- 当前约 80 个后端测试、0 个前端测试；认证边界、SSE、失败恢复和关键 UI 流程仍缺覆盖。

## 4. 推荐路线图

### Phase 0：安全与质量基线（0–2 周）

1. 建立统一资源授权层：用户必须拥有 conversation、KB、document、tag；设置改为用户级或管理员级。
2. 修复 JWT secret、SSRF、注册策略、速率限制、上传内容校验；新增安全回归测试。
3. 引入 Alembic；补备份/恢复脚本和恢复演练文档。
4. 从 `test_docs/` 建立 50–100 条 Golden Set，记录 Recall@5、MRR/nDCG、context precision/recall、faithfulness、citation precision、P95 延迟。
5. 将 RAG 配置、Prompt、Embedding/Reranker 版本写入每次评测结果，CI 对关键指标设非退化门禁。

**退出标准**：跨用户 ID 测试全部拒绝；SSRF 用例通过；同一数据集可一键复现实验并比较两版配置。

### Phase 1：复杂文档与可靠摄取（3–6 周）

1. 先接 Docling，按需增加 PaddleOCR/Marker；保留页码、标题层级、表格、图片说明和坐标。
2. 支持按 KB 配置并版本化 chunk 策略：父子分块、标题感知、表格不拆分；提供 chunk 预览、编辑和重建。
3. 引用升级为页码 + span/bbox，高亮原文；显示相关度和“证据不足”提示。
4. 用 Celery/RQ/Arq + Redis 替代进程内后台任务，支持进度、重试、取消、死信和重启恢复；BM25 改为可持久、可多 worker 一致的实现。
5. 增加 request_id 和结构化日志，对 rewrite、vector、BM25、rerank、LLM 分阶段 trace；记录 token、成本、耗时、命中和用户反馈。

**退出标准**：扫描 PDF、复杂表格、普通文档形成固定测试集；任务在服务重启后可恢复；引用可定位到原页原段。

### Phase 2：知识工作区与持续同步（7–10 周）

1. 增加 Project：绑定一个或多个 KB、Prompt、模型和检索配置；支持对话搜索、分支、固定和分享。
2. 增加 Full Context、Focused RAG、exact grep 三种模式；支持 metadata filter 和多 KB 检索。
3. 建立增量同步框架：本地文件夹优先，再扩展 Git、S3/网盘；用内容哈希处理新增、更新、删除和版本记录。
4. 提供版本化 REST API、个人 API Key、OpenAPI 文档和知识库导入/导出；补前端 Vitest/Playwright 冒烟测试。

### Phase 3：受控智能化（10 周后）

1. 先做带 JSON Schema、allowlist、超时、审计和用户确认的 tool registry，再接 MCP Streamable HTTP。
2. 记忆必须默认关闭、可查看/编辑/删除，并区分用户/项目范围；敏感信息不得自动长期保存。
3. 再考虑模型路由、定时摘要、工作流和团队 RBAC；SSO、Kubernetes、GraphRAG、语音和图片生成只在真实需求出现后投入。

## 5. 规划原则与指标

- **评测先于算法**：没有基线，不调整 chunk、阈值或模型默认值。
- **安全先于 Agent**：工具执行必须有最小权限、确认、沙箱和审计。
- **按失败类型迭代**：区分解析失败、召回失败、排序失败、生成幻觉和引用错误。
- **保持轻量**：默认单机可运行；Redis、外部向量库和 OCR 作为 profile/可选组件。
- **北极星指标**：Golden Set 通过率、citation precision、P95 首 token/总延迟、摄取成功率、人工“有帮助”率，以及单查询资源/费用。

## 6. 官方来源

- [RAGFlow 官方仓库](https://github.com/infiniflow/ragflow)；[Tracing](https://github.com/infiniflow/ragflow/blob/main/docs/administrator/tracing.mdx)
- [Dify 官方仓库](https://github.com/langgenius/dify)；[Knowledge Pipeline 发布说明](https://github.com/langgenius/dify/discussions/26138)
- [AnythingLLM 官方文档](https://docs.anythingllm.com/)；[MCP](https://docs.anythingllm.com/mcp-compatibility/overview)
- [Open WebUI Features](https://docs.openwebui.com/features/)；[Knowledge](https://docs.openwebui.com/features/workspace/knowledge/)；[RBAC](https://docs.openwebui.com/features/authentication-access/rbac/permissions/)
- [PrivateGPT Ingestion](https://docs.privategpt.dev/api-guide/ingestion)；[Async Ingestion](https://docs.privategpt.dev/api-guide/ingestion-async)；[Observability](https://docs.privategpt.dev/observability/observability)
- [Kotaemon 官方文档](https://cinnamon.github.io/kotaemon/development/)；[Quivr Core](https://github.com/QuivrHQ/quivr#configuration)
- [Ragas Core Concepts](https://docs.ragas.io/en/stable/concepts/)；[Ragas + Langfuse](https://langfuse.com/integrations/frameworks/ragas)

## 7. 局限

本报告比较的是公开社区版能力，不含无法验证的企业付费功能；项目功能变化很快，应在每个 Phase 开始前复核官方 release notes。工期按单人全职、复用现有架构估算；OCR 模型、硬件和文档类型会显著影响实际投入。

本次资料检索、代码对照与报告整理使用了 AI 辅助研究；关键竞品结论均回链至官方文档或官方仓库，规划优先级属于基于当前代码状态的工程判断。
