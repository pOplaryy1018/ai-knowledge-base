# 🧠 AI 知识库管理平台

基于 RAG（检索增强生成）架构的智能知识库管理平台，支持多格式文档导入、向量化检索与 AI 对话。

## ✨ 功能特性

- 📄 **多格式文档导入**：支持 PDF、DOC/DOCX、Markdown、TXT、代码、JSON/YAML，持久化导入状态并支持失败重试
- 🖼️ **图片 OCR**：自动识别图片中的中文/英文文字内容
- 🔍 **向量化检索**：基于 sentence-transformers 的文本向量化 + pgvector 向量存储
- 🤖 **AI 智能对话**：结合知识库上下文的 RAG 问答，支持流式 SSE 推送
- 📊 **统计面板**：知识条目趋势、对话趋势、热门知识排行等数据可视化
- 👥 **用户管理**：JWT 认证、角色权限控制（超级管理员 / 普通用户）
- 🏗️ **Monorepo 架构**：pnpm workspace 管理前后端多个子包

## 🛠️ 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 前端框架 | Vue 3 + TypeScript | 组合式 API + `<script setup>` |
| UI 组件库 | Arco Design Vue | 字节跳动开源组件库 |
| 构建工具 | Vite 6 | 快速 HMR 开发体验 |
| 状态管理 | Pinia | Vue 3 官方推荐 |
| 数据请求 | @tanstack/vue-query | 服务端状态缓存 |
| 图表 | ECharts + vue-echarts | 统计面板可视化 |
| 后端框架 | FastAPI (Python 3.12) | 异步 Web 框架 |
| ORM | SQLAlchemy 2.0 (async) | 异步数据库操作 |
| 数据校验 | Pydantic V2 | 类型安全配置与校验 |
| 数据库 | PostgreSQL 16 + pgvector | 向量存储 |
| 缓存 / 队列 | Redis 7 + arq | 异步任务队列 |
| LLM | OpenAI 兼容接口 | 默认 DeepSeek，可替换 |
| OCR | Tesseract | 中英文图片文字识别 |
| 文档解析 | pdfplumber / python-docx / markdown | 多格式提取 |
| 包管理 | pnpm (前端) / pip (后端) | Monorepo 管理 |

## 📁 项目结构

```
ai-knowledge-base/
├── packages/
│   ├── admin/            # 管理后台 (super_admin 角色)
│   ├── consumer/         # 用户端 (知识库检索与对话)
│   ├── backend/          # FastAPI 后端
│   └── shared/           # 前后端共享类型与工具
├── docs/                 # 文档与设计规范
├── docker-compose.yml    # Docker 本地开发环境
└── pnpm-workspace.yaml   # pnpm 工作区配置
```

## 🚀 本地开发

### 环境要求

- **Node.js** >= 20
- **pnpm** >= 9
- **Python** 3.12（与后端依赖锁和容器一致）
- **PostgreSQL 16** + **pgvector** 扩展
- **Redis** 7
- **Tesseract OCR**（可选，用于图片识别）

### 快速启动（Docker Compose）

```bash
# 1. 克隆仓库
git clone https://github.com/pOplaryy1018/ai-knowledge-base.git
cd ai-knowledge-base

# 2. 配置环境变量
cp packages/backend/.env.example packages/backend/.env
cp .env.example .env
# 编辑 .env，填入 LLM API Key 等必要配置

# 3. 新环境启动；已有数据请先按下方备份与升级步骤处理
# Compose 等待依赖健康，执行 migrate，成功后启动后端与 Worker
docker compose up -d

# 4. 启动前端开发服务器
pnpm install
pnpm dev:admin     # 管理后台 → http://localhost:54173
pnpm dev:consumer  # 用户端   → http://localhost:54174
```

### 手动启动

```bash
# 1. 安装前端依赖
pnpm install

# 2. 启动 PostgreSQL + Redis（可使用 Docker）
docker compose up -d postgres redis

# 3. 配置并启动后端
cd packages/backend
cp .env.example .env   # 编辑 .env 填入配置
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements-dev.lock.txt
alembic upgrade head  # 已有数据先备份；详见下方说明
uvicorn app.main:app --reload
# 另一个终端，packages/backend 下启动文档任务处理
arq app.worker.WorkerSettings

# 4. 启动前端
pnpm dev:admin
pnpm dev:consumer
```

### 环境变量说明

参考 `packages/backend/.env.example`，关键变量：

| 变量 | 说明 | 示例 |
|------|------|------|
| `DATABASE_URL` | PostgreSQL 连接串 | `postgresql+asyncpg://admin:password@localhost:15432/ai_knowledge` |
| `REDIS_URL` | Redis 连接地址 | `redis://localhost:16379/0` |
| `JWT_SECRET_KEY` | JWT 签名密钥 | 随机长字符串 |
| `LLM_API_KEY` | LLM API 密钥 | `sk-xxx`（需自行申请） |
| `LLM_BASE_URL` | LLM API 地址 | `https://api.deepseek.com` |
| `LLM_MODEL` | 模型名称 | `deepseek-chat` |
| `ENVIRONMENT` | 本地进程环境 | `development` / `production` |
| `EMBEDDING_MODEL` | Embedding 模型 | `Qwen/Qwen3-Embedding-0.6B`（1024 维） |
| `EMBEDDING_CACHE_DIR` | 可写模型缓存目录 | `./models` |
| `MODEL_PRELOAD` | Worker 启动时是否加载模型 | 默认 `False`，首个任务按需加载 |

Compose 从 `packages/backend/.env` 注入 LLM、JWT、管理员密码等配置；数据库和 Redis 地址自动替换为容器地址。仓库根目录 `.env` 用于 Compose 的 `APP_ENVIRONMENT` 和 PostgreSQL 账户配置。依赖端口只绑定本机，后端地址为 `http://localhost:8000`。容器共享 `uploads` 和 `models` 卷，`.env` 不进入镜像。

生产环境在根目录 `.env` 设置 `APP_ENVIRONMENT=production`，更换至少 12 字符的非默认 PostgreSQL 密码；在后端 `.env` 配置至少 32 字符的随机 JWT 密钥和至少 12 字符的非默认管理员密码。配置不合格时进程拒绝启动。初始密码仅用于新建管理员，不会重置已存在的管理员账户。前端对外访问需配置 `ALLOWED_ORIGINS`，通过反向代理提供 HTTPS。

首次使用 Embedding 会下载模型，需要网络、可写缓存目录及足够内存；修改模型必须保持 1024 维，模型或维度迁移需要单独设计与重建索引。后端与 Worker 分属不同进程，各自的编码并发上限为 1。

### 已有数据的备份与升级

1. 停止后端和 Worker 写入，保留 PostgreSQL、上传文件卷和模型缓存。
2. 使用 `pg_dump` 备份数据库，同时备份上传文件卷；在隔离数据库恢复并验证备份可用。
3. 执行 `alembic current` 与 `alembic upgrade head --sql` 检查迁移；确认后运行 `alembic upgrade head`，再恢复服务。Compose 的 `migrate` 也会自动执行这一步，因此旧环境首次更新前必须完成备份。
4. 新迁移建立导入任务表；没有可恢复任务记录的旧 `pending/processing` 文件会标记为失败供用户重试。知识条目与源文件不会因此删除。历史 `manual` 条目保留。已被旧迁移删除的数据需要从历史备份恢复。
5. 验证管理员登录、文件导入与重试、进度重连、跨用户权限、问答及文件删除。遇到问题先停止写入；结构 downgrade 不等于数据恢复，必要时从备份恢复。

上传与重试返回任务 ID；`GET /api/import/{task_id}/status` 与 `/progress` 均要求 Bearer 认证，仅任务所有者或超级管理员可读。进度可重连并重放终态。处理中的任务超时会变为失败供显式重试；排队任务不会因等待时间长而误失败。删除文件后旧任务不能再次写入知识片段。

### 质量验证

```bash
# 仓库根目录
pnpm test
pnpm lint
pnpm typecheck
pnpm build:admin
pnpm build:consumer
docker compose config --quiet

# packages/backend
python -m pytest -q
python -m ruff check app tests
python -m mypy app
python -m alembic upgrade head --sql
```

后端运行依赖固定在 `requirements.lock.txt`，开发工具在 `requirements-dev.txt`。更改依赖后使用 `uv pip compile requirements.txt --python-version 3.12 --universal --output-file requirements.lock.txt` 更新跨平台锁文件。CI 运行上述质量门禁；回归测试使用本地样例及替身，不调用付费 LLM 或下载模型。Docker、真实 PostgreSQL/Redis、模型和 LLM 的端到端验证需要运行环境单独验收。

`/api/live` 检查进程存活；`/api/ready` 在数据库或 Redis 不可用时返回 503。文件删除在数据库事务提交后清理源文件；磁盘权限等清理失败会记录日志，需要运维处理。

## 📝 默认账户

首次启动后自动创建超级管理员：

- 用户名：`admin`
- 密码：通过环境变量 `SEED_ADMIN_PASSWORD` 设置（默认 `devpassword`）

> ⚠️ 生产环境务必修改默认密码！

## 🧪 技术架构

```mermaid
graph LR
    A[Admin 管理后台] --> E[FastAPI 后端]
    B[Consumer 用户端] --> E
    E --> C[(PostgreSQL + pgvector)]
    E --> D[(Redis)]
    E --> F[LLM API]
    E --> G[OCR Tesseract]
    E --> H[arq Worker]
    H --> C
    H --> D
```

## 多来源个人知识库

用户端“资料来源”支持文档、本地授权仓库和公开 GitHub 仓库。仓库手动同步固定 commit，提供文件/行号引用、采集范围与跳过统计、原文浏览和采集快照下载；资料更新后可复核已保存答案，人工采纳候选并保留历史。

本地目录需管理员按用户 UUID 授权，并为 API/worker 配置相同只读挂载。部署与独立数据库验证方法见 [TESTING.md](TESTING.md)。证据未变化不证明答案正确；代码间接依赖与图片接入尚未实现。

## 📄 许可证

本项目基于 [MIT License](LICENSE) 开源。

## ⚠️ 注意事项

- 本项目依赖第三方 LLM 服务（如 DeepSeek、OpenAI），用户需自行申请 API Key
- 生产环境部署时请务必更换所有默认密码和密钥
- OCR 功能需要安装 Tesseract 及对应语言包
