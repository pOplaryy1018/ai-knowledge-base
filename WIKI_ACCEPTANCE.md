# LLM Wiki 使用与验收

核验日期：2026-10-14。当前交付为项目内主题Wiki V1，沿用现有Vue/FastAPI与资料证据链。编写约定见 [WIKI_SCHEMA.md](WIKI_SCHEMA.md)，路线和开发周期见 [DEVELOPMENT.md](DEVELOPMENT.md)。

## 使用流程

1. 启动项目后在用户端导航进入“LLM Wiki”（`/workspace/wiki`）。在“资料来源”准备至少一份已发布、可访问且有文字证据的资料。
2. 输入明确主题并选择资料，生成草稿。模型按主题检索相关证据，无法保证覆盖资料全文；无可引用文字时明确失败。
3. 在详情页人工编辑Markdown，展开引用核对原文、位置和资料版本。人工编辑沿用现有引用，新增陈述不会自动获得依据。
4. 保存会创建新修订，再由用户明确发布。发布版本可认证导出为Markdown；未发布草稿不能导出。
5. 用 `[[slug]]` 链接自己的已有页面。正向链接优先取当前保存草稿，反向链接来自其他已发布页面。代码示例与转义语法不生成链接。
6. 来源更新或不可用时提示“待复核”。选择当前资料重新编译会创建新草稿，旧发布和全部历史保留；再次核对后发布。

## 版本、权限与失败行为

- 页面、搜索、修订、链接目录和导出均按用户隔离。其他用户不能通过已知UUID访问。
- 写操作携带 `expected_revision_id`。旧页面编辑、重编译或发布返回409，前端保留本地编辑并解释如何刷新或重编译。
- 生成后的持久化与发布前再次锁定并校验来源头版本，避免模型调用期间资料变化被过期发布。
- 缺LLM配置返回503；无证据返回422；供应商或引用校验失败返回502；90秒超时返回504。失败不会改写已有发布。
- 每次修订只保存引用指针、位置与quote hash，API按原资料授权回取原文。删除资料后旧修订的引用原文不可用；Wiki正文和修订历史仍是用户保存的派生知识。
- Markdown禁用原始HTML。后端引用校验与前端显示使用一致的HTML文本边界；有效引用不能证明相关陈述真的被支持。
- 生成使用现有兼容LLM配置，temperature为0.2，正文最多50000字符。已有主题目录最多50条，不编造可跳转的页面地址。

## 迁移与运行

新增 `20261014_wiki`，建立 `wiki_pages` 与 `wiki_revisions`。新环境执行主README的迁移步骤；已有数据必须先备份，在副本恢复并验证再升级。不要把测试库迁移当作业务库迁移已完成。

迁移回退在存在Wiki页面或修订时拒绝删表。数据恢复需使用备份，不以downgrade代替。

独立测试：根目录启动 `docker compose -f compose.test.yml up -d --wait`；按 [TESTING.md](TESTING.md) 设置测试数据库和Redis，在 `packages/backend` 运行迁移和pytest。

## 本轮验证证据

- 后端260项通过、2项因Windows符号链接权限跳过；完整Mypy覆盖85个文件，Ruff通过。数据库使用独立PostgreSQL/pgvector和Redis，不是SQLite替身。新迁移完成空库回退/再升级，带数据回退拒绝也有集成测试。
- 前端51项测试、双端typecheck及生产构建通过；ESLint无错误，保留既有warning与构建大chunk提示。
- `tests/e2e/wiki-browser.cjs` 已通过：创建、编辑、发布、原文/原件、认证导出、双链/反链、重编译保留历史、409冲突、来源变更、HTML转义、搜索及390px手机布局。
- 原有 `tests/e2e/comparison-browser.cjs` 的11类检查通过。浏览器使用合成HTTP替身，不能称真实后端/模型端到端测试。
- 显式执行 `tests/manual/live_wiki_smoke.py`，通过两次真实DeepSeek生成，以及带引用草稿、人工发布和重编译历史验证。检索query embedding明确使用1024维确定性替身，OCR未运行；不是通用效果基线。
- 独立复查发现并修复HTML块未知引用绕过，以及Windows路径行内代码后的双链遗漏，均先复现失败再修复。
- 评测观测必须绑定固定数据集hash，拒绝将旧结果归入新资料，不能通过修改题目让错误拒答变成正确拒答。

普通CI不调用付费LLM、不下载模型。真实模型烟测仅在明确配置并选择运行时执行：`python -m pytest tests/manual/live_wiki_smoke.py -q -s`，仅使用合成资料与受保护测试库。

浏览器测试先启动用户端开发服务（可用54184隔离端口），安装可用的Playwright与Chrome后运行 `node tests/e2e/wiki-browser.cjs`。默认访问 `http://127.0.0.1:54184`，可用 `WIKI_UI_URL` 覆盖；可用 `PLAYWRIGHT_MODULE` 指向已有Playwright模块，截图写到被忽略的内部 `docs/acceptance/wiki-browser/`。

## 仍未完成的独立范围

60例评测资料已固定，离线校验/已有结果汇总/环境预检可用。完整真实OCR/embedding/检索/生成运行器、真实效果基线和人工陈述支撑标注仍未完成，详见 [QUALITY_EVALUATION_PLAN.md](QUALITY_EVALUATION_PLAN.md)。生产部署、业务库升级、备份恢复与公开站点URL也需要独立验收。
