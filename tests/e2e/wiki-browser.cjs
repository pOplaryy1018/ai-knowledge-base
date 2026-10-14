/* UI contracts with deterministic HTTP fixtures; this does not measure live model quality. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const base = process.env.WIKI_UI_URL || 'http://127.0.0.1:54184'
const output = process.env.WIKI_OUTPUT || path.resolve('docs/acceptance/wiki-browser')
const source = { id: 'source-a', name: '合成重试规范', kind: 'document', current_revision_id: 'source-v1', archived_at: null }
const citation = { index: 1, source_id: source.id, revision_id: source.current_revision_id,
  document_id: 'doc-a', knowledge_title: source.name, content: '重试次数上限为3次。', quote: '重试次数上限为3次。',
  locator: { logical_path: 'policy.md', line_start: 1, line_end: 1 }, unavailable: false }
const timestamp = '2026-10-14T03:00:00Z'
const revision = (id, content, kind = 'generated') => ({ id, title: '重试策略', content,
  kind, citations: [citation], source_versions: { 'source-a': 'source-v1' }, created_at: timestamp })
const targetRev = revision('target-v1', '背景知识 [1]')
const target = { id: 'wiki-target', slug: 'background', title: '背景知识', status: 'published',
  published_revision_id: targetRev.id, draft_revision_id: null, source_changed: false,
  published_revision: targetRev, draft_revision: null, history: [targetRev], links: [], backlinks: [], created_at: timestamp, updated_at: timestamp }
let current, counter = 0, changed = false, failPublish = false
let createCount = 0, exportCount = 0, originalCount = 0
const body = '最多重试3次。 [1]\n\n关联 [[background]]。\n\n<img src=x onerror="window.injected=true">'
const summary = p => ({ ...p, history: undefined, published_revision: undefined, draft_revision: undefined, links: undefined, backlinks: undefined })
function append(title, content, kind) {
  const rev = { ...revision(`revision-${++counter}`, content, kind), title }
  current.title = title; current.draft_revision = rev; current.draft_revision_id = rev.id
  current.history.push(rev)
}

;(async () => {
  fs.mkdirSync(output, { recursive: true })
  const browser = await chromium.launch({ headless: true, channel: 'chrome' })
  const context = await browser.newContext({ viewport: { width: 1360, height: 1000 } })
  await context.addInitScript(() => localStorage.setItem('akb_access_token', 'wiki-ui-fixture-token'))
  const page = await context.newPage(), errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/api/**', async route => {
    const request = route.request(), url = new URL(request.url()), method = request.method()
    if (!url.pathname.startsWith('/api/')) return route.continue()
    const json = (value, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(value) })
    assert(!url.searchParams.has('token'), 'Credentials must not appear in URL')
    if (url.pathname === '/api/auth/me') return json({ id: 'owner', username: 'wiki-fixture', role: 'user' })
    if (url.pathname === '/api/sources') return json({ items: [source] })
    if (url.pathname.endsWith('/original')) {
      assert.equal(request.headers().authorization, 'Bearer wiki-ui-fixture-token')
      originalCount++
      return route.fulfill({ body: citation.content, contentType: 'text/plain', headers: { 'content-disposition': 'attachment; filename="policy.md"' } })
    }
    if (url.pathname === '/api/wiki/pages') {
      if (method === 'POST') {
        createCount++
        assert.deepEqual(request.postDataJSON(), { title: '重试策略', source_ids: [source.id] })
        current = { id: 'wiki-primary', slug: 'retry-policy', title: '重试策略', status: 'draft',
          published_revision_id: null, draft_revision_id: null, published_revision: null,
          history: [], links: [{ id: target.id, slug: target.slug, title: target.title }], backlinks: [],
          source_changed: false, created_at: timestamp, updated_at: timestamp }
        append('重试策略', body, 'generated')
        return json(current, 201)
      }
      const query = url.searchParams.get('q') || ''
      return json({ items: [target, ...(current ? [current] : [])].filter(p => p.title.includes(query)).map(summary) })
    }
    if (url.pathname === '/api/wiki/pages/wiki-target') {
      return json({ ...target, backlinks: current?.published_revision ? [{ id: current.id, slug: current.slug, title: current.title }] : [] })
    }
    if (url.pathname.startsWith('/api/wiki/pages/wiki-primary')) {
      const suffix = url.pathname.slice('/api/wiki/pages/wiki-primary'.length)
      if (!suffix) return json({ ...current, source_changed: changed })
      const data = suffix === '/export' ? {} : request.postDataJSON()
      if (suffix === '/draft') {
        assert.equal(data.expected_revision_id, current.draft_revision_id || current.published_revision_id)
        append(data.title, data.content, 'edited')
        return json(current)
      }
      if (suffix === '/publish') {
        if (failPublish) return json({ detail: '资料版本已变化，请重新编译并复核草稿' }, 409)
        assert.equal(data.expected_revision_id, current.draft_revision_id)
        current.published_revision = current.draft_revision; current.published_revision_id = current.draft_revision_id
        current.draft_revision = null; current.draft_revision_id = null; current.status = 'published'
        return json(current)
      }
      if (suffix === '/compile') {
        assert.equal(data.expected_revision_id, current.draft_revision_id || current.published_revision_id)
        assert.deepEqual(data.source_ids, [source.id])
        append(current.title, '重新编译：最多重试3次。[1] [[background]]', 'generated')
        changed = false
        return json(current)
      }
      if (suffix === '/export') {
        assert.equal(request.headers().authorization, 'Bearer wiki-ui-fixture-token')
        exportCount++
        return route.fulfill({ body: '# Wiki export\n' + current.published_revision.content, contentType: 'text/markdown',
          headers: { 'content-disposition': "attachment; filename*=UTF-8''retry-policy.md" } })
      }
    }
    return json({ detail: `Unexpected fixture endpoint: ${method} ${url.pathname}` }, 404)
  })
  try {
    await page.goto(base + '/workspace/wiki')
    await page.waitForLoadState('networkidle')
    assert(await page.getByRole('button', { name: '生成 Wiki 草稿', exact: true }).isDisabled())
    await page.getByPlaceholder('例如：项目中的事务与并发控制').fill('重试策略')
    await page.getByPlaceholder('选择资料来源（最多100份）').click()
    await page.locator('.arco-select-option').filter({ hasText: source.name }).click()
    await page.getByRole('heading', { name: 'LLM Wiki', exact: true }).click()
    await page.getByRole('button', { name: '生成 Wiki 草稿', exact: true }).click()
    await page.waitForURL('**/workspace/wiki/wiki-primary')
    await page.getByLabel('Wiki Markdown正文', { exact: true }).waitFor()
    assert.equal(createCount, 1)
    assert.equal(await page.locator('.markdown-body img').count(), 0)
    assert.equal(await page.evaluate(() => window.injected), undefined)
    assert.equal(await page.locator('.arco-tabs-content-item-active .markdown-body a[href="/workspace/wiki/wiki-target"]').count(), 1)

    await page.getByText('引用 [1] · 合成重试规范', { exact: false }).first().click()
    await page.getByText(citation.quote, { exact: true }).first().waitFor()
    const original = page.waitForEvent('download')
    await page.getByRole('button', { name: '下载引用版本原件', exact: true }).click()
    assert.equal((await original).suggestedFilename(), 'policy.md')
    assert.equal(originalCount, 1)

    await page.getByLabel('Wiki Markdown正文', { exact: true }).fill('人工核对：最多重试3次。[1] [[background]]')
    assert(await page.getByRole('button', { name: '发布草稿', exact: true }).isDisabled())
    await page.getByRole('button', { name: '保存新草稿修订', exact: true }).click()
    await page.getByText('已保存为新的草稿修订', { exact: false }).waitFor()
    assert.equal(current.history.length, 2)
    await page.getByRole('button', { name: '发布草稿', exact: true }).click()
    await page.getByRole('button', { name: '确定', exact: true }).click()
    await page.getByText('草稿已发布。', { exact: false }).waitFor()
    assert.equal(current.published_revision.kind, 'edited')
    const download = page.waitForEvent('download')
    await page.getByRole('button', { name: '导出已发布 Markdown', exact: true }).click()
    assert.equal((await download).suggestedFilename(), 'retry-policy.md')
    assert.equal(exportCount, 1)
    await page.screenshot({ path: path.join(output, 'wiki-desktop.png'), fullPage: true, animations: 'disabled' })

    await page.locator('.arco-tabs-content-item-active .markdown-body a[href="/workspace/wiki/wiki-target"]').click()
    await page.waitForURL('**/workspace/wiki/wiki-target')
    await page.getByRole('heading', { name: '背景知识', exact: true }).waitFor()
    await page.locator('.wiki-side').getByRole('link', { name: '重试策略', exact: true }).click()
    await page.waitForURL('**/workspace/wiki/wiki-primary')
    await page.getByRole('button', { name: '按当前资料重新编译', exact: true }).click()
    await page.getByText('已根据当前资料生成新草稿', { exact: false }).waitFor()
    assert.equal(current.history.length, 3)
    assert.equal(current.published_revision.kind, 'edited')
    failPublish = true
    await page.getByRole('button', { name: '发布草稿', exact: true }).click()
    await page.getByRole('button', { name: '确定', exact: true }).click()
    await page.getByText('资料版本已变化，请重新编译并复核草稿。', { exact: false }).waitFor()
    assert.equal(current.history.length, 3)
    changed = true
    await page.getByRole('button', { name: '刷新页面', exact: true }).click()
    await page.locator('.wiki-review-warning').waitFor()
    await page.locator('.arco-tabs-tab-title').filter({ hasText: '修订历史' }).click()
    await page.locator('.wiki-history-select').waitFor()
    await page.setViewportSize({ width: 390, height: 844 })
    await page.screenshot({ path: path.join(output, 'wiki-mobile.png'), fullPage: true, animations: 'disabled' })
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'Page must fit mobile width')
    await page.goto(base + '/workspace/wiki')
    await page.waitForLoadState('networkidle')
    await page.getByPlaceholder('搜索 Wiki 标题或正文').fill('不存在的页面')
    await page.getByText('没有匹配的 Wiki 页面', { exact: true }).waitFor()
    assert.deepEqual(errors, [])
    console.log('PASS: Wiki creation, edit, publish, citation/original, export, links/backlinks, recompile/history, conflict, source change, escaping, search and mobile UI (HTTP fixtures).')
  } catch (error) {
    await page.screenshot({ path: path.join(output, 'wiki-failure.png'), fullPage: true })
    console.error('Wiki UI failure context:', page.url(), (await page.locator('body').innerText()).slice(0, 5000), errors)
    throw error
  } finally {
    await browser.close()
  }
})().catch(error => { console.error(error); process.exitCode = 1 })
