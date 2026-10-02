# 图片证据来源 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 实现已批准 IMAGE_SOURCES_DESIGN.md 的原图、OCR、人工描述和混合来源证据复核。

**Architecture:** 保留 Source/Revision/Publication 不可变版本链，图片连接器输出独立文本渠道和结构化 manifest。所有新图与文字编辑进入已有持久任务，发布前检查当前版本；复核先比较图片指纹再比较渠道。

**Tech Stack:** FastAPI、SQLAlchemy/PostgreSQL、ARQ、Pillow/Tesseract、Vue/TypeScript、pytest/Vitest/Playwright。

## Task 1: 图片连接器
Files: packages/backend/app/services/connectors/image.py; packages/backend/tests/test_image_source.py.
- [x] 写测试：真实 PNG/JPEG/WebP；伪造扩展名、多帧、10MiB、2000万像素拒绝；空 OCR、不可用 OCR 保留合法图片；指纹和三种渠道独立。
- [x] 运行 `python -m pytest tests/test_image_source.py -q`，确认新接口缺失造成失败。
- [x] 实现 `collect_image(path, *, manual_description='', ocr_correction='', ocr_runner=None)` 和可复用 `validate_image(path)`。输出带 image_hash、ocr_text、ocr_status、description/correction、raw_hash、documents、manifest 的不可变 ImageSnapshot。默认 OCR 有超时并正确关闭解码资源；人工校正替代 OCR 检索但机器原文留 manifest。
- [x] 针对测试通过，Ruff/Mypy 检查，再本地提交。

任务1验收：17项测试通过；设计和质量独立复查通过。本地提交3aebaf9、c0af359。任务2与任务3因持久输入和后台发布紧密耦合，由同一实施单元完成，统一复查。

## Task 2: 持久版本与 API
Files: packages/backend/app/api/image_source_api.py; app/schemas/source.py; app/models/source.py; app/main.py; migrations/versions; tests/integration/test_image_sources.py (all relative to packages/backend).
- [x] 写真实 PG 测试：创建/更新图片、授权原件、文本编辑清空、过期 expected_revision_id 和活动任务 409。
- [x] 用 TEST_DATABASE_URL 独立 akb_evidence_test 运行目标测试，确认端点缺失失败。
- [x] 创建图片上传、文本编辑、重提取端点；严格校验当前 head，保存持久任务输入，不自动复制新图旧描述；复用 source_api 的鉴权、锁顺序、原件下载和清理协议。版本处理输入必须能在 Redis 任务重试后恢复；需要时新增最小 JSONB 字段迁移。
- [x] PG 目标测试通过，静态检查，提交。

## Task 3: 工作任务与发布
Files: packages/backend/app/services/source_jobs.py; source_publication.py; source_cleanup.py; tests/integration/test_image_sources.py.
- [x] 增加空 OCR/不可用 OCR 发布空文字版本、embedding 失败保留旧 head、删除取消不发布、重试幂等测试。
- [x] 先运行目标 pytest 观察行为失败。
- [x] image 分支调用连接器，编辑复用已保存 OCR 不重提取；仅 image 允许空 chunks，记录 needs_description。失败不发布；发布前复查来源访问与 expected head。共享图片原件删除路径去重。
- [x] 测试通过、静态检查和提交。

## Task 4: 图片证据复核
Files: packages/backend/app/services/impact_service.py; scoped_chat_service.py; tests/integration/test_image_sources.py.
- [ ] 增加不同图相同 OCR 必 changed/image_changed、同图描述修改只影响 manual_description、渠道删除 missing、未知指纹不可追踪、混合引用测试。
- [ ] 运行 pytest 确认旧比较逻辑失败。
- [ ] 图指纹变化优先；同图仅匹配对应 origin/logical_path；引用元数据明确 OCR/人工描述/人工校正，保留原来的精确引文校验。
- [ ] 目标及文档/Git 回归通过，提交。

## Task 5: 图片界面
Files: packages/shared/src (source types/API); packages/consumer/src/views/sources/SourceWorkspace.vue; saved answer/review components and locator formatter; frontend tests.
- [ ] 增加认证 Blob 加载释放、版本切换丢弃过期响应、渠道标签、编辑冲突的测试，执行 `pnpm test` 确认失败。
- [ ] 实现图片创建与更新、原图历史预览、OCR只读、校正和描述编辑、手动重提取；复核显示旧新原图与变化原因，支持现有候选采纳。
- [ ] Vitest、typecheck、build、lint 通过并提交。

## Task 6: 集成验收
- [ ] 全量真实 PG pytest；Ruff、Mypy；全量 pnpm test/typecheck/build/lint。
- [ ] 隔离数据库迁移升级降级升级、备份恢复，禁止操作业务库。
- [ ] 浏览器上传空 OCR 图→补充描述→与代码联合问答→保存答案→换图→复核→采纳候选，检查权限、历史和控制台错误。
- [ ] 可用时真实 OCR 测试；替身流程与 OCR/真实 embedding 质量分别报告。
- [ ] 分别完成设计符合度与代码质量检查，修复发现的问题；验收报告存 outputs，本地提交，不推送。

## 验证环境
Python: F:/codex/2026-10-01/wo/work/backend-verification-312/Scripts/python.exe。
TEST_DATABASE_URL: postgresql+asyncpg://evidence_test:evidence_test_only@127.0.0.1:25432/akb_evidence_test。
Redis: redis://127.0.0.1:26379/0。每条命令在 packages/backend 执行；不打印 .env 或 Settings。


