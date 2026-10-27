# 后端接口与数据结构审查

审查日期：2026-10-27。范围：个人资料问答、图谱检索、答案复核、Wiki、管理统计的接口组合和 PostgreSQL 表关系。使用独立的 `akb_evidence_test` 与测试 Neo4j；未连接业务库。

## 已验证的设计

- `/api/chat/scoped` 统一准备会话和已发布来源范围；个人问答、资料对比、Wiki 编译复用 `prepare_evidence`。向量/关键词与图谱并行召回，图谱候选回到 PostgreSQL 核验用户、来源、版本、片段和可用状态后才进入提示词。图谱故障时保留来源检索，双路故障返回服务错误。这一聚合边界符合 `CONTEXT.md` 和 `NEO4J_DESIGN.md`。
- 来源、不可变版本、发布记录、文档、答案修订、引用证据、复核、Wiki 修订分表保存。`graph_build_tasks` 以 `(revision_id, extractor_version)` 唯一，状态与租约可恢复；`graph_cleanup` 不依赖已删除来源的外键，适合异步清理。测试库迁移到 head 成功。
- 管理统计按概览、动态与图表数据分接口，允许图表独立筛选和缓存。前端已移除未展示词云时的额外请求。暂不需要为这些读请求增加统一大接口；应先测量页面请求耗时和失败率。

## 后续改进项

1. **父子指针的数据库约束不足（中）**：测试库实际外键仅校验 `sources.current_revision_id`、`sources.current_publication_id`、`saved_answers.accepted_revision_id`、`wiki_pages.{draft,published}_revision_id` 指向存在的行，未约束该行属于同一个来源、答案或页面。正常服务路径有所有权和版本检查，但手工修复脚本或未来代码缺陷仍可能写入跨父对象指针。先在业务库副本审计现有记录，再为修订表增加可引用的 `(parent_id, id)` 唯一键与复合外键，或采用同等强度的数据库约束；单独制定迁移及回滚方案。
2. **证据链接口的响应契约较松（中）**：`source_api`、`answer_api`、`wiki_api`、`graph_api` 多数返回 `dict[str, Any]`，共享包由前端手工维护类型。字段增删或分页形状变化时，类型检查无法发现前后端漂移。按现有响应定义 Pydantic 模型，并用 OpenAPI/客户端契约测试覆盖资料、图谱状态、答案及 Wiki；保持现有 URL 和业务语义。
3. **列表分页反馈不一致（低）**：知识库列表有 `total`，`/answers` 和 `/reviews` 只有 `items/page/size`。用户端以“本页是否满 20 条”推测下一页，恰好满页时会出现可点击但为空的下一页。可为两个接口补 `total` 或 `has_more`，并让前端分页按钮据此判断。

这些是结构性改进建议，尚未对业务库执行迁移，也没有把工程测试结果解释为真实模型问答质量。

## 验证记录

- 独立 PostgreSQL/Redis/Neo4j 容器启动；`alembic upgrade head` 成功，离线迁移 SQL 生成 710 行。
- 后端 `pytest -q`：278 通过、2 跳过（Windows 符号链接权限相关）；Ruff 通过；Mypy 93 个源文件通过；`docker compose -f compose.test.yml config --quiet` 通过。
- 本机测试服务的真实 HTTP 浏览器链路完成合成用户注册 → 登录 → 新建知识库 → 进入资料来源；API `/api/ready` 返回数据库与 Redis 已连接。该流程未调用真实模型。
- 以上是工程与隔离集成验证；真实 LLM、embedding、OCR 的效果及业务库迁移不在这次审查结果内。
