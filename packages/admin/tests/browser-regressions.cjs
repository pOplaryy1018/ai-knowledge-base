/* Deterministic HTTP fixtures only: no business data or real model calls. */
/* eslint-disable @typescript-eslint/no-require-imports */
/* global require, process, console, localStorage, window, navigator, URL */
const assert = require('node:assert/strict')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const adminUrl = process.env.ADMIN_UI_URL || 'http://127.0.0.1:54183'
const consumerUrl = process.env.ADMIN_CONSUMER_UI_URL
const agent = { id: 'agent-two', name: 'Selected synthetic agent', knowledge_ids: ['item-1'], description: null, prompt_template: null, created_at: '2026-10-14T00:00:00Z' }
const requests = []
const failures = []
let browser

async function withPage(authenticated, run) {
  const context = await browser.newContext({ reducedMotion: 'reduce' })
  await context.addInitScript((authenticated) => {
    if (authenticated) localStorage.setItem('akb_access_token', 'synthetic-admin-token')
    window.testOpenedUrl = null
    window.testCopiedUrl = null
    window.open = url => { window.testOpenedUrl = url; return null }
    Object.defineProperty(navigator, 'clipboard', { value: { writeText: async url => { window.testCopiedUrl = url } } })
  }, authenticated)
  const page = await context.newPage()
  page.setDefaultTimeout(5000)
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/api/**', async route => {
    const request = route.request(), url = new URL(request.url())
    if (!url.pathname.startsWith('/api/')) return route.continue()
    requests.push({ path: url.pathname, method: request.method(), query: Object.fromEntries(url.searchParams) })
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
    if (url.pathname === '/api/auth/me') return json({ id: 'owner', username: 'synthetic', role: 'super_admin' })
    if (url.pathname === '/api/auth/login') return json({ detail: 'Invalid synthetic login' }, 400)
    if (url.pathname === '/api/knowledge-bases') {
      if (request.method() === 'POST') return json({ id: 'created', name: 'Synthetic' }, 201)
      return json({ items: [{ id: 'kb-two', name: 'Synthetic KB', description: null }], total: 1 })
    }
    if (url.pathname === '/api/agents') return json({ items: [{ ...agent, id: 'agent-one', name: 'First synthetic agent' }, agent], total: 2 })
    if (url.pathname === '/api/agents/' + agent.id) return json(agent)
    if (url.pathname === '/api/statistics/top-items') return json([{ id: 'item-1', title: 'Synthetic top knowledge', count: 3 }])
    if (url.pathname.startsWith('/api/statistics/')) return json([])
    return json({ detail: 'Unexpected synthetic endpoint' }, 404)
  })
  try { await run(page); assert.deepEqual(errors, [], 'unexpected browser exceptions') } finally { await context.close() }
}

async function check(name, run) {
  if (process.env.ADMIN_CASE && !name.includes(process.env.ADMIN_CASE)) return
  try { await run(); console.log('PASS ' + name) }
  catch (error) { failures.push(name + ': ' + error.message); console.error('FAIL ' + name + ': ' + error.message) }
}

;(async () => {
  browser = await chromium.launch({ headless: true, channel: 'chrome' })
  await check('invalid login submits zero HTTP requests', () => withPage(false, async page => {
    await page.goto(adminUrl + '/login'); await page.waitForLoadState('networkidle')
    const before = requests.length
    await page.getByRole('button', { name: /登\s*录/ }).click()
    await page.getByText('请输入用户名', { exact: true }).waitFor()
    await page.waitForTimeout(150)
    assert.equal(requests.slice(before).filter(r => r.path === '/api/auth/login').length, 0)
  }))
  await check('invalid knowledge form submits zero HTTP requests', () => withPage(true, async page => {
    await page.goto(adminUrl + '/admin/knowledge-bases'); await page.waitForLoadState('networkidle')
    await page.getByRole('button', { name: '新建知识库', exact: true }).click()
    const before = requests.length
    await page.locator('.arco-modal-footer').getByRole('button', { name: /创\s*建/ }).click()
    await page.waitForTimeout(150)
    assert.equal(requests.slice(before).filter(r => r.method === 'POST').length, 0)
    assert.equal(await page.locator('.arco-modal').isVisible(), true)
  }))
  await check('valid login still submits one HTTP request', () => withPage(false, async page => {
    await page.goto(adminUrl + '/login'); await page.waitForLoadState('networkidle')
    await page.getByPlaceholder('请输入用户名', { exact: true }).fill('synthetic')
    await page.getByPlaceholder('请输入密码', { exact: true }).fill('synthetic-password')
    const before = requests.length
    await page.getByRole('button', { name: /登\s*录/ }).click()
    await page.getByText('Invalid synthetic login', { exact: true }).waitFor()
    assert.equal(requests.slice(before).filter(r => r.path === '/api/auth/login').length, 1)
  }))
  await check('valid knowledge form still submits and closes', () => withPage(true, async page => {
    await page.goto(adminUrl + '/admin/knowledge-bases'); await page.waitForLoadState('networkidle')
    await page.getByRole('button', { name: '新建知识库', exact: true }).click()
    await page.getByPlaceholder('请输入知识库名称', { exact: true }).fill('Synthetic created KB')
    const before = requests.length
    await page.locator('.arco-modal-footer').getByRole('button', { name: /创\s*建/ }).click()
    await page.locator('.arco-modal').waitFor({ state: 'hidden' })
    assert.equal(requests.slice(before).filter(r => r.method === 'POST' && r.path === '/api/knowledge-bases').length, 1)
  }))
  for (const action of ['cancel', 'close']) await check('knowledge dialog ' + action + ' closes', () => withPage(true, async page => {
    await page.goto(adminUrl + '/admin/knowledge-bases'); await page.waitForLoadState('networkidle')
    await page.getByRole('button', { name: '新建知识库', exact: true }).click()
    if (action === 'cancel') await page.locator('.arco-modal-footer').getByRole('button', { name: /取\s*消/ }).click()
    else await page.locator('.arco-modal-close-btn').click()
    await page.locator('.arco-modal').waitFor({ state: 'hidden' })
    await page.getByRole('button', { name: '新建知识库', exact: true }).click()
    await page.locator('.arco-modal').waitFor({ state: 'visible' })
  }))
  await check('statistics filters issue requests with current days and KB', () => withPage(true, async page => {
    await page.goto(adminUrl + '/admin/statistics'); await page.waitForLoadState('networkidle')
    const before = requests.length
    await page.getByText('近7天', { exact: true }).click()
    await page.waitForTimeout(200)
    const recent = requests.slice(before)
    assert(recent.some(r => r.path === '/api/statistics/items-trend' && r.query.days === '7'), 'missing 7-day item request')
    assert(recent.some(r => r.path === '/api/statistics/chat-trend' && r.query.days === '7'), 'missing 7-day chat request')
    const kbStart = requests.length
    await page.locator('.arco-select-view').click()
    await page.getByText('Synthetic KB', { exact: true }).click()
    await page.waitForTimeout(200)
    for (const endpoint of ['items-trend', 'items-by-type', 'top-items', 'tags-wordcloud']) {
      assert(requests.slice(kbStart).some(r => r.path === '/api/statistics/' + endpoint && r.query.kb_id === 'kb-two'), 'missing filtered ' + endpoint)
    }
    assert(requests.slice(kbStart).some(r => r.path === '/api/statistics/items-trend' && r.query.days === '7'))
  }))
  await check('statistics Top table renders synthetic knowledge row', () => withPage(true, async page => {
    await page.goto(adminUrl + '/admin/statistics'); await page.waitForLoadState('networkidle')
    await page.getByRole('row').filter({ hasText: 'Synthetic top knowledge' }).waitFor()
    assert.equal(await page.locator('.statistics-page canvas').count(), 3)
  }))
  await check('knowledge table renders synthetic knowledge row', () => withPage(true, async page => {
    await page.goto(adminUrl + '/admin/knowledge-bases'); await page.waitForLoadState('networkidle')
    await page.getByRole('row').filter({ hasText: 'Synthetic KB' }).waitFor()
  }))
  await check('agent share and test use consumer route and agent_id', () => withPage(true, async page => {
    await page.goto(adminUrl + '/admin/agents'); await page.waitForLoadState('networkidle')
    const row = page.getByRole('row').filter({ hasText: agent.name })
    const expected = new URL(adminUrl); expected.port = '54174'; expected.pathname = '/workspace/chat'; expected.searchParams.set('agent_id', agent.id)
    await row.getByRole('button', { name: '复制链接', exact: true }).click()
    assert.equal(await page.evaluate(() => window.testCopiedUrl), expected.toString())
    await row.getByRole('button', { name: '对话测试', exact: true }).click()
    assert.equal(await page.evaluate(() => window.testOpenedUrl), expected.toString())
  }))
  if (consumerUrl) await check('consumer route selects requested agent instead of first agent', () => withPage(true, async page => {
    await page.goto(consumerUrl + '/workspace/chat?agent_id=' + agent.id)
    await page.waitForLoadState('networkidle')
    assert.equal(await page.locator('.chat-topbar h3').textContent(), agent.name)
  }))
  await browser.close()
  if (failures.length) { console.error(failures.join('\n')); process.exitCode = 1 }
})().catch(async error => { console.error(error); await browser?.close(); process.exitCode = 1 })
