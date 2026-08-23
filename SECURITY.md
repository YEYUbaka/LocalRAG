# 安全策略

简体中文 | [English](SECURITY.en.md)

## 支持的版本

| 分支 / 版本 | 支持状态 |
| ----------- | -------- |
| `master` 最新代码 | ✅ 接收安全修复 |
| 历史 commit / tag | ❌ 请升级到最新版本 |

## 如何报告漏洞

**请勿通过公开 Issue、PR 或 Discussions 报告安全问题。**

首选通道：GitHub 私密安全公告——仓库页 **Security → Advisories → New draft security advisory**，直达链接：<https://github.com/YEYUbaka/LocalRAG/security/advisories/new>

报告时请尽量包含：

- 漏洞类型与影响范围；
- 复现步骤或最小化 PoC；
- 触发前提（部署方式、相关配置）。

维护者会在 **48 小时内**确认收到，约 **7 天内**给出初步评估。确认后双方再协商披露时间线，原则上修复发布后才公开细节。

## 重点关注的范围

- **本地优先边界**：任何导致原始文档、向量索引、API Key 外泄到非预期第三方的路径；
- 认证与会话：JWT 签发/校验逻辑、默认账号口令、会话过期策略；
- 文档解析：恶意构造的 PDF / Office / HTML 文件引发的解析器漏洞；
- Web 安全：SQL 注入、路径穿越（上传/导出/预览接口）、XSS（预览渲染）、CORS 配置；
- 部署面：docker-compose 默认口令、nginx 反代配置、`.env` 示例中的弱默认值；
- 依赖链中的已知高危 CVE。

## 项目已有的安全设计

- 密钥仅存于本地 `.env`（不入库，CI 内置密钥扫描 job）；
- 原始文档与向量索引留在本地，云端 LLM 仅接收脱敏后的检索片段。

## 已知上游依赖漏洞（跟踪中）

- **GHSA-f4j7-r4q5-qw2c**（critical）：chromadb 鉴权前代码注入，影响 1.0.0 – 1.5.9，截至 2026-08-23 上游尚未发布修复版本。
  - **暴露面分析**：该漏洞位于 chromadb 的 HTTP 服务端请求处理路径。LocalRAG 仅以**嵌入式模式**使用 chromadb（`app/core/vectorstore.py` 中的 `PersistentClient`，进程内运行、无任何网络监听），源码部署与 docker-compose 均不启动 chroma server，因此默认配置下攻击面不存在。
  - **处置约定**：上游发布修复版后立即升级并解除本记录；在此之前，任何贡献者都**不得**引入以 server 模式运行 chromadb 或对外暴露其端口的改动。

感谢你负责任地披露，你的贡献会让所有 LocalRAG 用户更安全。
