# 🧠 AI 知识库管理平台

基于 RAG（检索增强生成）架构的智能知识库管理平台，支持多格式文档导入、向量化检索与 AI 对话。

## ✨ 功能特性

- 📄 **多格式文档导入**：支持 PDF、DOCX、Markdown、TXT 文件上传与自动解析
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
| 后端框架 | FastAPI (Python 3.11+) | 异步 Web 框架 |
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
- **Python** >= 3.11
- **PostgreSQL 16** + **pgvector** 扩展
- **Redis** 7
- **Tesseract OCR**（可选，用于图片识别）

### 快速启动（Docker Compose）

```bash
# 1. 克隆仓库
git clone https://github.com/your-org/ai-knowledge-base.git
cd ai-knowledge-base

# 2. 配置环境变量
cp packages/backend/.env.example packages/backend/.env
# 编辑 .env，填入 LLM API Key 等必要配置

# 3. 启动所有依赖服务 (PostgreSQL + Redis + 后端 + Worker)
docker compose up -d

# 4. 启动前端开发服务器
pnpm install
pnpm dev:admin     # 管理后台 → http://localhost:5173
pnpm dev:consumer  # 用户端   → http://localhost:5174
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
pip install -r requirements.txt
uvicorn app.main:app --reload

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

## 📄 许可证

本项目基于 [MIT License](LICENSE) 开源。

## ⚠️ 注意事项

- 本项目依赖第三方 LLM 服务（如 DeepSeek、OpenAI），用户需自行申请 API Key
- 生产环境部署时请务必更换所有默认密码和密钥
- OCR 功能需要安装 Tesseract 及对应语言包
