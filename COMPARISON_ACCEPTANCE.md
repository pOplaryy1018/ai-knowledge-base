# 资料对比卡片开发与验收
日期：2026-10-13。项目：E:/zijie/ai-knowledge-base。
## 使用
进入“个人资料问答”，选择2至4份已发布资料，切换“资料对比”，输入比较问题并点击“生成对比”。
卡片按比较维度排列资料；可筛选维度，点击引用编号查看原文、位置与版本并下载原件。
回答完成后可保存，在“已保存答案与复核”重新打开、生成候选、采纳，并查看历史版本及其原文引用。
手机布局改为顶部可横向滚动的导航；卡片表格可横向滚动查看其他资料。
## 实现与边界
保留Vue/Arco/FastAPI及现有来源版本和权限体系。没有新增React、CopilotKit、TypeSafe或运行生成代码的依赖。
对每份资料独立检索最多3段证据，合并统一编号；模型仅输出数据JSON，严格限制维度、来源、文本长度及引用。
未知/跨来源引用、重复来源/维度、额外字段拒绝；无引用或缺失单元格显示“未找到依据”。
JSON格式无效时降级为普通引用问答并提示；供应商中断不发done，不产生可保存的完整卡片。
messages与answer_revisions新增可空comparison JSONB，保留兼容正文；原文仅取自可鉴权的引用证据，不复制进展示结构。
服务校验结构和引用归属，不能机械证明每个模型结论都被原文支持。真实embedding召回质量及复杂资料的对比质量仍需专门评测。
对比模式每轮独立处理，请完整描述比较主题；“只比较刚才第二项”等多轮指代未接入。
## 实际验证
- Docker引擎29.4.3响应正常；独立akb-evidence-tests PostgreSQL/pgvector（25432）与Redis（26379）健康。
- 独立测试库Alembic升级到20261012_comparison；无卡片数据时降级/升级往返通过；有卡片历史时拒绝降级的集成测试通过。
- 全套后端：202 passed，1 skipped（Windows符号链接权限），无失败。
- 前端：40 tests passed；双端vue-tsc通过。
- 无头Chrome：11类验证，覆盖来源数量、SSE、维度筛选、原文/版本/定位、原件下载、保存、读回、候选采纳、历史引用、HTML转义、手机内容宽度。HTTP使用确定性替身。
- 真实模型：独立PG中的两份合成资料生成两个维度、两个有效引用。检索向量使用确定性替身；不是全量检索质量验收。
- Ruff app/tests通过；修改范围Mypy（排除既有statistics.py）检查77个文件通过。完整Mypy仍有statistics.py的12个既有Select类型错误，该文件未修改。
- 双端生产构建通过；全项目ESLint无error、27个既有warning；本次四个Vue文件无warning。构建保留既有大chunk提示、jieba弃用warning。
## 重跑
在仓库根目录运行：
```powershell
docker compose -f compose.test.yml up -d --wait
pnpm test
pnpm typecheck
pnpm lint
pnpm build:consumer
pnpm build:admin
```
在packages/backend运行：
```powershell
$env:ENVIRONMENT='test'
$env:DATABASE_URL='postgresql+asyncpg://evidence_test:evidence_test_only@127.0.0.1:25432/akb_evidence_test'
$env:TEST_DATABASE_URL=$env:DATABASE_URL
$env:REDIS_URL='redis://127.0.0.1:26379/0'
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check app tests
```
真实模型小样例需已有模型配置，显式运行 `.venv/Scripts/python.exe -m pytest tests/manual/live_comparison_smoke.py -q -s`，会产生少量模型调用费用。默认全套测试不会调用它。
浏览器：先启动 `pnpm --filter @akb/consumer dev --host 127.0.0.1 --port 54184`，配置PLAYWRIGHT_MODULE为安装的playwright模块路径；执行 `node tests/e2e/comparison-browser.cjs`。COMPARISON_OUTPUT可指定截图输出目录。
## 部署
本次未修改业务数据库或部署；代码按用户要求提交并推送GitHub开发分支。正式库使用新代码前需备份并在副本确认迁移，再执行alembic upgrade head并重启后端。
降级保护会拒绝直接删除已有卡片字段；不要通过清空卡片绕过保护，应保留/导出历史并制定恢复方案。
测试环境已补装锁文件中既有的pytesseract==0.3.13；没有安装Tesseract或更改OCR业务配置。

独立只读代码审查未发现可确认的重要阻塞问题；审查没有代替测试执行。
