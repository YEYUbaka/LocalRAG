<!-- 标题建议使用 Conventional Commit 风格，例如 feat: 支持表格感知分块 -->

## 背景 / 问题

<!-- 说明这个 PR 解决什么问题，关联 Issue 用 Closes/Fixes #编号 -->

## 变更内容

-

## 变更类型

- [ ] feat（新功能）
- [ ] fix（缺陷修复）
- [ ] docs（文档）
- [ ] refactor（重构，不改行为）
- [ ] test（测试）
- [ ] chore（构建/工具链）

## 验证方式

已运行并通过：

- [ ] `conda run -n localrag python -m pytest backend/tests -v`
- [ ] `cd frontend && npm run lint && npm test && npm run build`
- [ ] `docker compose up --build`（涉及部署/依赖变更时）

其他验证命令、截图（UI 变更必附）：

## 兼容性影响（没有就保持全不勾）

- [ ] 涉及数据库 schema 变更（需附 Alembic 迁移脚本）
- [ ] 新增/修改环境变量（需同步 `.env.example`）
- [ ] 修改检索参数默认值或 SSE/API 契约（需更新契约快照）

说明：

## 本地优先红线自查

- [ ] 未引入将原始文档/向量索引发送到第三方服务的逻辑
- [ ] 未提交 `.env`、密钥、模型文件、上传文档或生成产物

## Checklist

- [ ] 提交信息遵循 Conventional Commits
- [ ] 附带回归测试，或说明为何不需要
- [ ] 相关文档（README / docs / plans）已同步更新
