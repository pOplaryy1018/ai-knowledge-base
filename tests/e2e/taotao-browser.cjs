/* Deterministic browser contract for the persistent assistant in both apps. */
const { chromium } = require('playwright')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const output = process.env.TAOTAO_OUTPUT || path.resolve('docs/acceptance/taotao-browser')
const fixtureSources = [
  { id: 'source-a', name: '合成重试规范', kind: 'document', current_revision_id: 'revision-a', archived_at: null },
  { id: 'source-b', name: '合成产品记录', kind: 'document', current_revision_id: 'revision-b', archived_at: null },
  { id: 'source-draft', name: '未发布草稿', kind: 'document', current_revision_id: null, archived_at: null },
  { id: 'source-archived', name: '已归档资料', kind: 'document', current_revision_id: 'revision-old', archived_at: '2026-10-01T00:00:00Z' },
]
const citation = {
  index: 1, source_id: 'source-a', revision_id: 'revision-a', document_id: 'document-a',
  knowledge_title: '合成重试规范', content: '最多重试三次。', quote: '最多重试三次。',
  locator: { logical_path: 'policy.md', line_start: 3 }, unavailable: false,
}

function sseEvent(type, data) { return `event: ${type}\ndata: ${JSON.stringify(data)}\n\n` }

async function checkApp(browser, { base, routePath, role, name, navPath }) {
  const context = await browser.newContext({ viewport: { width: 1360, height: 900 }, acceptDownloads: true })
  await context.addInitScript(() => localStorage.setItem('akb_access_token', 'taotao-fixture-token'))
  const page = await context.newPage()
  const errors = [], calls = [], failures = []
  let originals = 0
  const sources = [...fixtureSources]
  page.on('pageerror', error => errors.push(error.message))
  page.on('console', message => { if (message.type() === 'error') failures.push(message.text()) })
  page.on('requestfailed', request => failures.push(`${request.url()}: ${request.failure()?.errorText}`))
  page.on('response', response => { if (response.status() >= 400) failures.push(`${response.status()} ${response.url()}`) })
  await page.route('**/api/**', route => {
    const request = route.request(), url = new URL(request.url())
    if (!url.pathname.startsWith('/api/')) return route.continue()
    const json = value => route.fulfill({ contentType: 'application/json', body: JSON.stringify(value) })
    if (url.pathname === '/api/auth/me') return json({ id: 'fixture-user', username: '合成用户', role })
    if (url.pathname === '/api/auth/users' || url.pathname === '/api/statistics/recent-activities') return json([])
    if (url.pathname === '/api/statistics/overview') return json({ total_items: 0, available_items: 0, total_agents: 0, today_chats: 0 })
    if (url.pathname === '/api/sources') return json({ items: sources })
    if (url.pathname === '/api/answers' || url.pathname === '/api/reviews') return json({ items: [] })
    if (url.pathname === '/api/chat/scoped') {
      assert.equal(request.headers().authorization, 'Bearer taotao-fixture-token')
      const body = request.postDataJSON()
      calls.push(body)
      return route.fulfill({ contentType: 'text/event-stream', body: [
        sseEvent('meta', { conversation_id: 'conversation-1' }),
        sseEvent('token', { content: '最多重试三次。' }),
        sseEvent('citations', [citation]),
        sseEvent('done', { conversation_id: 'conversation-1', message_id: 'message-1' }),
      ].join('') })
    }
    if (url.pathname.endsWith('/original')) {
      originals++
      return route.fulfill({ contentType: 'text/plain', body: citation.content })
    }
    return json({ items: [], total: 0 })
  })
  try {
    await page.goto(base + routePath)
    await page.waitForLoadState('networkidle')
    if (!(await page.locator('body').innerText())) throw new Error(`App rendered an empty page: ${[...errors, ...failures].join('; ')}`)
    await page.getByRole('button', { name: '打开韬韬知识助手' }).click()
    const assistant = page.getByRole('dialog', { name: '韬韬知识助手' })
    await assistant.getByText('全部可访问资料 · 2 份').waitFor()
    await assistant.getByRole('button', { name: /更改范围/ }).click()
    assert.equal(await assistant.getByRole('checkbox').count(), 2)
    assert.equal(await assistant.getByText('未发布草稿').count(), 0)
    await assistant.getByRole('button', { name: /更改范围/ }).click()
    await assistant.getByRole('textbox', { name: '向韬韬提问' }).fill('重试上限是多少？')
    await assistant.getByRole('button', { name: /发送/ }).click()
    await assistant.locator('.taotao-answer').getByText('最多重试三次。', { exact: true }).waitFor()
    assert.deepEqual(calls[0].source_ids, ['source-a', 'source-b'])
    const download = page.waitForEvent('download')
    await assistant.getByRole('button', { name: /合成重试规范.*版本/ }).click()
    await download
    assert.equal(originals, 1)
    await assistant.getByRole('button', { name: /更改范围/ }).click()
    await assistant.getByRole('checkbox', { name: '合成产品记录' }).uncheck()
    assert.equal(await assistant.getByText('重试上限是多少？').count(), 0)
    await assistant.getByRole('button', { name: /更改范围/ }).click()
    await assistant.getByRole('textbox', { name: '向韬韬提问' }).fill('再问一次')
    await assistant.getByRole('button', { name: /发送/ }).click()
    await assistant.locator('.taotao-answer').getByText('最多重试三次。', { exact: true }).waitFor()
    assert.deepEqual(calls[1].source_ids, ['source-a'])
    await page.keyboard.press('Escape')
    assert.equal(await assistant.count(), 0)
    sources.push({ id: 'source-new', name: '新发布的合成资料', kind: 'document', current_revision_id: 'revision-new', archived_at: null })
    await page.getByRole('button', { name: '打开韬韬知识助手' }).click()
    await assistant.getByText('再问一次').waitFor()
    await assistant.getByRole('button', { name: /更改范围/ }).click()
    await assistant.getByRole('checkbox', { name: '新发布的合成资料' }).waitFor()
    assert.equal(await assistant.getByRole('checkbox', { checked: true }).count(), 1)
    await assistant.getByRole('button', { name: /更改范围/ }).click()
    await page.locator(`nav a[href="${navPath}"]`).click()
    await assistant.getByText('再问一次').waitFor()
    await page.setViewportSize({ width: 390, height: 844 })
    await page.screenshot({ path: path.join(output, `${name}-mobile.png`), fullPage: true, animations: 'disabled' })
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'Mobile page must fit viewport')
    await page.setViewportSize({ width: 1360, height: 900 })
    await page.screenshot({ path: path.join(output, `${name}-desktop.png`), fullPage: true, animations: 'disabled' })
    if (name === 'consumer') await page.getByRole('button', { name: /退出登录/ }).click()
    else {
      await page.locator('.user-info').click()
      await page.getByText('退出登录', { exact: true }).click()
    }
    await page.waitForURL('**/login')
    assert.equal(await page.getByRole('dialog', { name: '韬韬知识助手' }).count(), 0)
    assert.deepEqual(errors, [])
    console.log(`${name}: assistant stream, citation, scope reset, navigation, Escape, mobile and logout passed`)
  } finally { await context.close() }
}

;(async () => {
  fs.mkdirSync(output, { recursive: true })
  const browser = await chromium.launch({ headless: true, channel: 'chrome' })
  try {
    await checkApp(browser, { base: process.env.CONSUMER_UI_URL || 'http://127.0.0.1:54174', routePath: '/workspace/answers', role: 'user', name: 'consumer', navPath: '/workspace/knowledge-bases' })
    await checkApp(browser, { base: process.env.ADMIN_UI_URL || 'http://127.0.0.1:54173', routePath: '/admin/dashboard', role: 'super_admin', name: 'admin', navPath: '/admin/users' })
  } finally { await browser.close() }
})().catch(error => { console.error(error); process.exitCode = 1 })
