# 本地开发 / 上手体验 — 已知问题与待办

> 状态：**待办清单，尚未修复**（`JWT_SECRET` 一项已出方案待决策）。
> 建立日期：2026-09-22。记录人为 Claude（基于一次真实排障会话）。
> 相关文档：[AGENTS.md](../../AGENTS.md)（JWT_SECRET 配置小节）、[README](../../README.md) 快速开始、[CONTRIBUTING](../../CONTRIBUTING.md) 环境准备。

## 为什么有这份文档

2026-09-22 一次「后端起不来 / 前端 502」的排障，暴露出一串本地开发与上手的结构性问题。它们不是偶发故障，而是**每个新用户/新部署都会踩**的固定坑，因此集中记录，避免只靠 AGENTS.md 的零散条目。

## 核心问题：`JWT_SECRET` 要求每个用户手写环境变量

### 现象

后端起不来，报：

```
RuntimeError: JWT_SECRET must contain at least 32 UTF-8 bytes
```

要点：`backend/app/auth.py:17` 在**模块导入期**就执行 `build_auth_config(EnvironmentSecretProvider())`，所以整个应用导入即失败——`uvicorn --reload` 的父进程不会退出也不会监听端口，表现为端口空着、前端 `ECONNREFUSED`/502。

### 三个互相冲突的事实

| # | 事实 | 位置 |
|---|------|------|
| 1 | `.env.example` 告诉用户把 `JWT_SECRET` 填进 `.env` | `.env.example:6-7` |
| 2 | `Settings` **没有** `jwt_secret` 字段，且 pydantic-settings 默认 `extra="forbid"` → 写进 `.env` 反而启动失败 | `backend/app/config.py:16-81`、`secrets.py:16-20` |
| 3 | 密钥只能来自**进程环境变量**，于是每个用户/每个终端都要手动 `export` | `backend/app/security/secrets.py:10-13` |

**已实测确认**（2026-09-22，用真实 `Settings` 类 + `.env.example` 内容作为 `env_file`）：

```
FAIL: ValidationError
1 validation error for Settings
jwt_secret
  Extra inputs are not permitted [type=extra_forbidden,
  input_value='your-jwt-secret-at-least-32-bytes-long']
```

也就是说：**照着 `.env.example` 做，一定起不来**。文档与代码在这一项上直接矛盾。

### 其他项目怎么做（调研结论）

| 项目 | 开发期怎么给密钥 | 生产期 | 可借鉴点 |
|------|------------------|--------|----------|
| **Django** | `django-admin startproject` 直接生成一个随机 `SECRET_KEY` 写进 `settings.py`（官方文档明确说是 "for convenience"）；未设置则拒绝启动 | 部署清单要求从环境变量**或文件**（文档示例 `/etc/secret_key.txt`）读取；`SECRET_KEY_FALLBACKS` 支持轮换 | **自动生成 + 持久化到文件**是主流做法；「从文件读」是被官方认可的形态 |
| **Rails** | test/development 下 `secret_key_base` 由**应用名派生**，无需手填 | 其他环境必须有随机密钥，存在 `credentials.yml.enc`；`master.key` 不入库；`bin/rails secret` 生成 | 开发/生产**分级策略**：开发图省事，生产强制 |
| **Laravel** | 安装流程执行 `php artisan key:generate`，把 `APP_KEY` **写进 `.env`** | 同机制 | 生成后**写入 env 文件**，用户零操作；说明「密钥进 .env」本身并非不可接受 |
| **Docker Compose** | — | `secrets:` 以**文件**形式挂载到 `/run/secrets/<name>`；普通 environment 变量对同宿主其他进程可见 | 容器部署应走 secrets 或 env 注入，不能假设宿主已 export |

**结论**：没有哪家要求每个用户手动 export。通行做法是「**开发期自动生成并持久化到不入库的文件，生产期用环境变量/secrets 覆盖**」。

### 候选方案

- **方案 A（推荐）：首次运行自动生成并持久化**
  启动时若 `JWT_SECRET` 环境变量缺失，则读 `data/.jwt_secret`；若该文件也不存在，生成 `secrets.token_hex(32)` 写入该文件（权限收紧、已 gitignore）并使用。**环境变量优先，文件仅作开发期兜底**；使用文件兜底时打一条 warning。
  - 优点：零操作；符合 Django/Laravel 先例；生产仍可用环境变量整体覆盖。
  - 代价：密钥落盘于数据目录，须确保 gitignore 与文件权限；多进程需读同一文件（文件方案天然满足）。
- **方案 B：保留环境变量，但把报错变成可执行的指引**
  在 `require_secret` 的报错里直接给出「要跑什么命令」。改动最小，但没解决"每个用户都要配"的核心痛点。
- **方案 C：给 `Settings` 声明 `jwt_secret` 字段，让 `.env` 写法如其文档所述生效**
  改 3 行即可让 `.env.example` 的写法成立。
  - 代价：与 Phase 0「密钥必须来自环境」的设计意图相悖，且把签名密钥放进容易被拷贝的 `.env`。
- **方案 D：维持现状 + 文档**（最低成本，痛点保留）

### 待办（JWT_SECRET）

- [ ] **决策方案 A/B/C/D** —— 倾向 A（环境变量优先 + 文件兜底）；若采纳，需同步修订 Phase 0 验收里"must come from environment"的表述
- [ ] 若采纳 A：实现 `data/.jwt_secret` 的读取/生成/落盘，确认 `.gitignore` 覆盖（`data/` 已整体忽略）
- [ ] 若采纳 A 或 C：修正 `.env.example` 与 `Settings` 的矛盾（当前第 6-7 行的 `JWT_SECRET` 行是**错误指引**，要么删、要么让代码支持）
- [ ] 补一条回归测试：断言「仅有 `.env` 无 `JWT_SECRET` 环境变量」时的行为符合方案预期（当前无任何测试覆盖该组合）

## 其他待办

### P1 · `docker compose up` 起不来（后端缺 `JWT_SECRET`）

`docker-compose.yml` 的 `backend` 服务 `environment:` 只有 `DATABASE_URL`、`DATA_DIR`，**没有 `JWT_SECRET`**；`backend/Dockerfile` 以 `./backend` 为构建上下文，仓库根的 `.env` 不会被打进镜像。因此 `docker compose up --build` 会因同一个 `RuntimeError` 失败。

- [ ] 给 `backend` 服务补密钥注入：优先 `secrets:`（挂到 `/run/secrets/`，需后端支持读文件），或 `environment: JWT_SECRET: ${JWT_SECRET:?}` 强制宿主提供
- [ ] 若选后者，在 `.env.example` 或 README 的 Docker 段落说明需要先在宿主设置该变量
- [ ] 未验证：本机无 Docker，未实跑；修复后需实际 `docker compose up --build` 确认

### P1 · 文档四处不一致，新用户必然踩坑

| 文档 | 当前说法 | 问题 |
|------|----------|------|
| `.env.example:6-7` | 把 `JWT_SECRET` 填进 `.env` | **与代码矛盾，会导致启动失败** |
| `README.md` 快速开始 §2 | 只说「编辑 .env，填入 LLM 配置和 MySQL」 | **完全没提 `JWT_SECRET`** —— 照做必失败 |
| `CONTRIBUTING.md` 环境准备 | 同样只提 LLM 与 MySQL | 同上 |
| `AGENTS.md` | 已补 `JWT_SECRET` 必填说明 + 配置小节 | 正确，但三份对外文档没跟上 |

- [ ] README 快速开始补 `JWT_SECRET` 步骤（对外文档优先级最高）
- [ ] CONTRIBUTING「环境准备」同步
- [ ] `.env.example` 修正（依赖上面 JWT_SECRET 的方案决策）
- [ ] 顺手核对：`.env.example` 的 `LLM_API_KEY` 等字段与 `Settings` 字段完备一致（本次已确认除 `jwt_secret` 外无其他 `extra_forbidden`）

### P2 · 后端启动 20+ 秒，前端 0.2 秒，首屏必然报错

实测（本机 2026-09-22）：后端从启动到端口 `LISTEN` 约 **23–26 秒**（`jieba` 词典 + `bge` 模型加载），Vite 仅 **0.2 秒**就绪。用户打开页面时后端仍在加载 → 前端立刻 `ECONNREFUSED`/502。**这不是故障，是固有的启动时序差**，但体验上像故障。

- [ ] 让 Vite 代理在 ECONNREFUSED 时静默重试/降级（配置 `proxy.configure` 或 `retry`），避免刷屏报错
- [ ] 或前端显示「后端启动中」的明确占位态，而不是代理报错
- [ ] 评估后端懒加载（模型按需初始化）是否可行——可把 20s 摊到首次请求，但会改变首问延迟
- [ ] 至少在 README/AGENTS 的启动步骤里注明「后端需等 20-30 秒」，避免误判为崩溃

### P2 · `uvicorn --reload` 强杀后残留孤儿 worker 占住端口

`--reload` 模式下父进程负责监听、`multiprocessing` worker 负责跑应用（实测命令行形如 `python -c "from multiprocessing.spawn import spawn_main; spawn_main(parent_pid=...)"`）。**强杀父进程不会连带清理 worker**，后者继续占着端口（表现为 `Errno 10048` / `WinError 10013`，且 `Ctrl+C` 已无效）。本次排障中连续踩到两次。

- [ ] 在 AGENTS.md/脚本里补一条「清干净」命令（本次已写入 AGENTS.md 排查条目）：
  `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*uvicorn*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }`
- [ ] 评估给 `start.bat` 加启动前端口检查 + 残留清理，避免用户手动处理

### P2 · `start.bat` 依赖发起终端的环境

`start.bat:26` 用 `conda run -n localrag --no-capture-output uvicorn ...` 启动后端——`conda run` **只继承发起终端的环境**（已实测确认变量能透传）。所以双击 `start.bat` 时，`JWT_SECRET` 必须在**该 cmd 会话可继承的环境里**（系统/用户级 + 重启 explorer，或 `conda env config vars set`），否则后端立刻崩。

- [ ] 推荐用 `conda env config vars set JWT_SECRET=<值> -n localrag` 钉进环境，之后 `conda activate` 自动注入 —— 这是绕开 Windows 环境变量广播问题的**最省事路径**，建议写进 README
- [ ] 或在 `start.bat` 里显式读取并校验 `JWT_SECRET`，缺失时给出明确提示而不是让后端静默崩溃

### P3 · 依赖漏洞与依赖 PR 积压

- [ ] GitHub 提示默认分支有 **10 个依赖漏洞**（1 critical / 3 high / 6 moderate）
- [ ] 4 个 dependabot PR（#16 pypdf、#17 browserslist、#18 vitest、#19 baseline-browser-mapping）自 2026-09-02/09-11 起未处理
- [ ] 注意：`npm audit` 在国内镜像下不可用，需加 `--registry=https://registry.npmjs.org`

### P3 · Windows 环境变量广播问题（已记录，供新用户检索）

用户级/系统级环境变量设置后**仅重开终端通常无效**——只写注册表，需广播 `WM_SETTINGCHANGE`，而已运行的 Explorer 环境块是旧的，其所有派生终端都继承旧块。彻底生效需重启 explorer 或注销重登。

- [x] 已写入 AGENTS.md 的「JWT_SECRET 配置」小节（含排查方法与会话内临时绕过写法）
- [ ] 若采纳 JWT_SECRET 方案 A，此坑对新用户自然消失（无需再配环境变量）

## 建议的修复顺序

1. **JWT_SECRET 方案决策**（阻塞其余多项：`.env.example`、docker、README 都依赖它）
2. README / CONTRIBUTING 补 `JWT_SECRET`（对外文档，新用户第一入口）
3. `docker-compose.yml` 补密钥注入
4. 前端代理重试 + 启动时延说明（体验层）
5. `start.bat` 端口清理 + 密钥校验（工具链）
6. 依赖漏洞与 dependabot PR（可与上述并行）
