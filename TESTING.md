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

## 已知非阻塞项

前端 lint 有既有 28 个 warning，构建仍有大 chunk 提示；后端 jieba 有 pkg_resources 弃用 warning。来源任务失败提示目前为通用提示，原已发布版本保留。Docker 镜像下载经过本地代理可能间歇 EOF/reset。
