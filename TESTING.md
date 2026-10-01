# 第一阶段验收与独立测试环境

2026-10-01：文档来源、版本、限定来源问答、保存答案、直接引用变化复核、候选采纳和历史保留已完成工程验收。真实模型质量与现有业务数据迁移尚未验收。

## 测试数据库

根目录运行 `docker compose -f compose.test.yml up -d`。这是独立项目 akb-evidence-tests，PostgreSQL 使用 25432，Redis 使用 26379，不复用业务数据。数据库使用 tmpfs，停止容器后可能丢失，不能用作正式资料库。

在 packages/backend 的 PowerShell 中，仅为本次进程设置：

```powershell
$env:DATABASE_URL='postgresql+asyncpg://evidence_test:evidence_test_only@127.0.0.1:25432/akb_evidence_test'
$env:TEST_DATABASE_URL=$env:DATABASE_URL
$env:REDIS_URL='redis://127.0.0.1:26379/0'
python -m alembic upgrade head
python -m pytest -q
python -m ruff check app tests
python -m mypy app
```

集成测试没有 TEST_DATABASE_URL 时会跳过；跳过不算数据库验收。保护规则只允许 localhost/127.0.0.1 的 akb_evidence_test。

根目录运行 `pnpm test`、`pnpm typecheck`、`pnpm lint`、`pnpm build:admin`、`pnpm build:consumer`。开发端口为 54173 和 54174。

## 使用范围

新入口是“资料来源”“个人问答”“已保存答案”。使用新来源入口上传文档才能建立版本与证据链；旧知识库上传、旧 Agent 问答保持兼容，旧记录标为不可追踪，不推测历史版本。重新上传早先已发布版本暂不支持作为回滚。

浏览器验收使用真实 PostgreSQL、Redis、ARQ 和 HTTP/SSE，但模型与向量器为确定性测试替身。正式运行前还需在独立环境配置真实服务，验证一个正常引用问题、一个无证据问题、一次更新后的候选生成。测试替身服务不可用于正式演示。

迁移只在测试库演练过 upgrade、downgrade、再 upgrade 和备份恢复。现有业务库上线需先备份，在副本验证迁移与记录数，再安排正式迁移。

## 第二阶段：仓库接入

资料来源可选择本地仓库或公开 GitHub 仓库，手动同步固定 HEAD commit，仅采集已提交 UTF-8 文本。未提交内容不会入库；每次同步的 dirty 观察独立记录，即使 commit 未变也会提示。范围可以修改，修改后需手动同步；相同 commit 不同处理范围产生独立版本。

本地授权默认关闭。在后端 `.env` 中配置 JSON 数组（路径和 UUID 按实际部署填写）：

```dotenv
SOURCE_REPO_ROOTS=[{"id":"personal","label":"个人代码目录","path":"/repo-roots/personal","user_ids":["USER_UUID"]}]
SOURCE_GIT_EXECUTABLE=git
SOURCE_REPO_CACHE_DIR=./uploads/git-cache
```

Windows 原生部署将 path 换为实际绝对路径，如 `E:/code`。Docker 部署必须为 backend 和 worker 分别增加相同只读挂载，例如 `E:/code:/repo-roots/personal:ro`，并共享相同用户授权配置；不要把盘符路径直接传入容器。前端只显示 label 和根目录内相对路径，不显示服务端根路径。Git 已加入 Dockerfile，但更新镜像需要重新构建。

本地路径、`.git` symlink/junction、对象 alternates、配置 include、linked worktree 和配置了 filters 的仓库会被拒绝；不执行项目代码或安装依赖。公開来源限 HTTPS GitHub 公共仓库，禁用凭据继承、hooks、filter、重定向和子模块。

候选文件默认5000、单文件1MiB、总文本50MiB、超时180秒。公开 fetch 另监测100MiB临时存储预算；50ms检查间隔可能短时超出预算，超限不会发布。超限可调整范围后重试。ZIP 下载只包含实际采集文件，不是完整 Git 仓库备份，commit/范围/跳过清单在版本信息中查看。

来源内容版本与发布记录分离，A→B→A保留三次发布及独立复核事件。存在重复发布后，降级到第一阶段的迁移会明确拒绝，避免丢失发布历史；应恢复备份或制定专门迁移方案。

第二阶段验证包含真实 GitHub 首次采集、本地真实仓库更新/回退/删除、真实 HTTP 凭据隔离、SHA-1/SHA-256、数据库与浏览器。公共来源更新采用受控连接器快照测试，不修改第三方仓库。真实 LLM 两个小样例通过，embedding 仍用替身验证编排，不代表真实检索质量验收。

## 已知非阻塞项

前端 lint 有既有 28 个 warning，构建仍有大 chunk 提示；后端 jieba 有 pkg_resources 弃用 warning。来源任务失败提示目前为通用提示，原已发布版本保留。Docker 镜像下载经过本地代理可能间歇 EOF/reset。
