# 贡献指南

感谢关注 LocalRAG！无论是提 Issue、修 Bug、写文档还是做新功能，都欢迎。花两分钟读完这份指南，能让你的贡献更快被合并。

## 行为准则

参与本项目即表示你同意遵守[行为准则](CODE_OF_CONDUCT.md)。遇到不当行为请通过 GitHub 私信联系维护者。

## 开始之前：本地优先红线

这是本项目最重要的设计约束，任何改动都不得破坏：

- **原始文档、向量索引、Embedding/Reranker 模型全部留在本地**；
- 只有**脱敏后的检索片段**会被发送到用户自行配置的云端 LLM；
- 不要硬编码任何 API Key、密码或真实用户数据；不要提交 `.env`、模型文件、上传文档和构建产物（CI 有密钥扫描）。

如果某个功能必须把原始文档发往第三方才能实现，请先开 Issue 讨论。

## 环境准备

详细步骤见 [README 快速开始](README.md)，速览：

| 依赖 | 版本 |
| ---- | ---- |
| Python（推荐 conda 环境 `localrag`） | 3.11+ |
| Node.js（CI 使用） | 18+ / 20 |
| MySQL | 8.0（也可直接用 docker compose） |

```bash
# 后端
conda create -n localrag python=3.11
conda activate localrag
pip install -r backend/requirements.txt

# 前端
cd frontend && npm install

# 配置
cp .env.example .env   # 填入 LLM API 与 MySQL 配置
```

## 常用命令

```bash
# 后端开发服务器（backend/ 目录下）
uvicorn app.main:app --reload --port 8000

# 前端开发服务器（frontend/ 目录下）
npm run dev

# 后端测试
conda run -n localrag python -m pytest backend/tests -v

# 前端检查
cd frontend && npm run lint && npm test && npm run build

# 数据库迁移（修改 models.py 后）
cd backend && alembic revision --autogenerate -m "..." && alembic upgrade head

# 全栈联调
docker compose up --build
```

## 分支与提交规范

- 从最新 `master` 切出分支，命名建议：`feat/<主题>`、`fix/<主题>`、`docs/<主题>`；
- 提交信息遵循 **Conventional Commits**：`feat:` `fix:` `docs:` `refactor:` `test:` `chore:` + 简短的祈使句摘要；
- 一个分支只做一件事，保持 PR 小而聚焦；不要把格式化、重构和功能改动混在一个 PR 里。

## 测试要求

- 后端使用 pytest，文件命名 `test_<feature>.py`，用例命名 `test_<behavior>`；
- 复用 `backend/tests/conftest.py` 的 fixture；mock 掉数据库之外的 LLM、Embedding、联网调用，保证测试确定性；
- 新功能和 Bug 修复都要附带回归测试，重点覆盖：API 状态码、检索排序、SSE 事件顺序、文档解析；
- 未设覆盖率门槛，但「改了什么就要测什么」。

## CI 质量门（PR 必须全绿）

`.github/workflows/quality-gates.yml` 包含五个 job：

| Job | 内容 | 什么时候会挂 |
| --- | ---- | ------------ |
| backend | pytest 全量后端测试 | 测试失败、依赖冲突 |
| frontend | npm test + lint + build | 类型错误、ESLint 违规 |
| contracts | API 契约快照比对 | 改了接口但没更新快照：在 `backend/` 下执行 `python scripts/export_contracts.py --output contracts` 后一并提交 |
| migrations | Alembic 在干净 MySQL 上升级 | 改了模型但没写迁移脚本 |
| security | 密钥扫描 + 依赖审计 | 代码里混入疑似密钥 |

## 提交 PR

1. 大改动（新检索阶段、新存储后端、架构调整）请**先开 Issue** 对齐方向，避免白做；
2. 使用 [.github/PULL_REQUEST_TEMPLATE.md](.github/PULL_REQUEST_TEMPLATE.md) 填写：问题背景、变更点、验证命令、关联 Issue；
3. UI 改动附截图（改前/改后更佳）；
4. **显式标注** schema、环境变量、检索参数默认值的变化——这些会影响所有部署方；
5. 等待 CI 全绿 + 至少一位维护者 review 后合并。

外部贡献者请走标准 fork 工作流：Fork → 切分支 → 提交 → 向 `master` 发起 PR。拥有写权限的协作者直接建分支即可。

## 报告 Issue

- Bug 请用 [Bug 模板](.github/ISSUE_TEMPLATE/bug_report.yml)：复现步骤、期望/实际行为、环境信息、脱敏日志；
- 功能建议请用[功能模板](.github/ISSUE_TEMPLATE/feature_request.yml)，讲清楚使用场景；
- 使用疑问和想法交流请到 [Discussions](https://github.com/YEYUbaka/LocalRAG/discussions)。

## 安全问题

**切勿公开提交**，参见 [SECURITY.md](SECURITY.md)。

## 许可证

提交即表示你同意贡献内容以 [MIT](LICENSE) 协议授权。
