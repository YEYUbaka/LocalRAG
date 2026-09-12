# 前端设计方向稿

三个可交互的静态 HTML 方案，用于确定 LocalRAG 前端的视觉方向。**不是最终代码**，选定后才落地为 React + Ant Design。

## 打开方式

直接双击 `index.html`（对比入口），或单独打开任意方案。无外部依赖、无网络请求、无需构建。

| 文件 | 方案 | 核心赌注 |
|------|------|----------|
| `index.html` | 对比入口 | 三方案并排缩略图 + 取舍分析 |
| `a-dossier.html` | A · 案卷 | 证据卡的**相关度排序条**（条长 = 真实重排分归一化） |
| `b-pipeline.html` | B · 流程 | 顶部**可视化检索流水线**，阶段可展开看排名变化 |
| `c-collation.html` | C · 校勘 | 放弃聊天气泡；**段落批注联动** + 滚动跟随 |

## 设计约束（三案共有）

- 浅色底，脱离 Ant Design 默认蓝 `#1677ff`
- 全部样式走 CSS 自定义属性，无内联 `style={{}}`
- 键盘焦点可见、响应式到移动端、尊重 `prefers-reduced-motion`

## 数据来源

稿内所有内容取自本仓库真实资产，便于判断手感：

- 语料：`test_docs/interview-ai-engineer.md`、`test_docs/RAG技术入门.md`、`test_docs/interview-project-star.md`、`test_docs/interview-project-qa.md`
- 检索参数：`top_k=5`、`retrieval_top_k=20`、`rerank_threshold=1.0`、`query_rewrite_enabled=true`（见 `AGENTS.md`）

## preview/

Playwright 渲染的截图，用作方案留档与 PR 附件：

- `<方案>-1440.png` — 桌面视图
- `<方案>-820.png` — 窄屏视图（验证无横向溢出）
- `<方案>-active.png` — 签名交互的激活态

## 当前状态

**未选定方向。** 三个签名互不排斥，可合成一版（A 的三栏 + B 的流水线状态条 + C 的段落批注联动）。
