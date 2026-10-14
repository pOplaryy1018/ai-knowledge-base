/* Synthetic HTTP contracts for the existing consumer screens; no live account or model. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const assert = require('node:assert/strict')
const base = process.env.CONSUMER_UI_URL || 'http://127.0.0.1:54184'
const files = ['a', 'b', 'image'].map(id => ({ id, knowledge_base_id: 'kb', original_filename: `${id}.${id === 'image' ? 'png' : 'txt'}`,
  file_type: id === 'image' ? 'png' : 'txt', file_size: 20, chunks_count: 1, status: 'completed', created_at: '2026-10-14T00:00:00Z' }))
const content = id => ({ file_id: id, content_type: id === 'image' ? 'image' : 'text', content: id === 'image' ? '' : `Content ${id}`,
  total_chars: 9, preview_chars: 9 })
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a5XcAAAAASUVORK5CYII=', 'base64')

;(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'chrome' })
  let failures = 0
  async function run(name, test, authenticated = true) {
    const context = await browser.newContext()
    if (authenticated) await context.addInitScript(() => {
      localStorage.setItem('akb_access_token', 'fixture-access')
      localStorage.setItem('akb_refresh_token', 'fixture-refresh')
    })
    await context.addInitScript(() => {
      window.objectUrls = []; window.revokedUrls = []
      const create = URL.createObjectURL.bind(URL), revoke = URL.revokeObjectURL.bind(URL)
      URL.createObjectURL = blob => { const url = create(blob); window.objectUrls.push(url); return url }
      URL.revokeObjectURL = url => { window.revokedUrls.push(url); revoke(url) }
    })
    const page = await context.newPage()
    page.setDefaultTimeout(8000)
    const state = { requests: [], releaseA: null, delayA: false, expireRaw: false, refreshes: 0, releaseAgent: null, releaseStream: null }
    await context.route('**/api/**', async route => {
      const req = route.request(), url = new URL(req.url())
      if (!url.pathname.startsWith('/api/')) return route.continue()
      state.requests.push({ url, method: req.method(), authorization: req.headers().authorization })
      const json = (value, status = 200) => route.fulfill({ contentType: 'application/json', status, body: JSON.stringify(value) })
      if (url.pathname === '/api/auth/me') return json({ id: 'owner', username: 'fixture', role: 'user' })
      if (url.pathname === '/api/auth/refresh') { state.refreshes++; return json({ access_token: 'fixture-refreshed' }) }
      if (url.pathname === '/api/auth/login' || url.pathname === '/api/auth/register') return json({ detail: 'Should not submit invalid input' }, 400)
      if (url.pathname === '/api/knowledge-bases') return json(req.method() === 'GET' ? { items: [], total: 0, page: 1, size: 20 } : { detail: 'Invalid' }, req.method() === 'GET' ? 200 : 400)
      if (url.pathname === '/api/knowledge-bases/kb/files') return json({ items: files, total: 3, page: 1, size: 20 })
      if (url.pathname === '/api/agents') return json({ items: [{ id: 'default', name: 'Default assistant' }] })
      if (url.pathname.startsWith('/api/agents/')) {
        const id = url.pathname.split('/').pop()
        if (id === 'private') return json({ detail: 'Forbidden' }, 403)
        if (id === 'slow') await new Promise(resolve => { state.releaseAgent = resolve })
        return json({ id, name: `Assistant ${id}` }).catch(() => {})
      }
      if (url.pathname.startsWith('/api/chat/agents/')) {
        await new Promise(resolve => { state.releaseStream = resolve })
        return route.fulfill({ contentType: 'text/event-stream', body: 'event: token\ndata: {"content":"OLD PRIVATE STREAM"}\n\nevent: done\ndata: {"conversation_id":"old-conversation"}\n\n' }).catch(() => {})
      }
      const match = url.pathname.match(/\/files\/(a|b|image)\/(preview|raw)$/)
      if (match?.[2] === 'preview') {
        if (state.delayA && match[1] === 'a') await new Promise(resolve => { state.releaseA = resolve })
        return json(content(match[1])).catch(() => {}) // canceled requests may already be gone
      }
      if (match?.[2] === 'raw') {
        if (state.expireRaw && req.headers().authorization !== 'Bearer fixture-refreshed') return json({ detail: 'Expired' }, 401)
        return route.fulfill({ contentType: 'image/png', body: png })
      }
      return json({ detail: 'Unknown fixture endpoint' }, 404)
    })
    try { await test(page, state); console.log(`PASS ${name}`) }
    catch (error) { failures++; console.error(`FAIL ${name}: ${error.message}`); console.error(state.requests.map(r => r.url.pathname).join(', ')) }
    finally { state.releaseA?.(); state.releaseAgent?.(); state.releaseStream?.(); await context.close() }
  }
  const open = async page => {
    await page.goto(base + '/workspace/knowledge-bases/kb')
    await page.locator('.filename-link').first().waitFor()
  }
  const select = (page, id) => page.locator('.filename-link').filter({ hasText: files.find(f => f.id === id).original_filename }).evaluate(el => el.click())
  const settle = page => page.waitForLoadState('networkidle')

  await run('A late response cannot replace selected B', async (page, state) => {
    state.delayA = true
    await open(page); await select(page, 'a')
    await page.waitForFunction(() => !!document.querySelector('.preview-overlay'))
    await select(page, 'b') // same visible component, different selected file
    await page.waitForTimeout(100)
    state.releaseA?.(); await settle(page)
    assert.equal(await page.locator('.preview-text-content').textContent(), 'Content b')
  })
  await run('closing A then opening B rejects A completion', async (page, state) => {
    state.delayA = true
    await open(page); await select(page, 'a')
    await page.locator('.toolbar-btn-close').click()
    await select(page, 'b')
    await page.locator('.preview-text-content').waitFor()
    state.releaseA?.(); await settle(page)
    assert.equal(await page.locator('.preview-text-content').textContent(), 'Content b')
  })
  await run('image uses Bearer Blob and releases object URL on close', async (page, state) => {
    await open(page); await select(page, 'image'); await page.locator('.preview-image').waitFor(); await settle(page)
    assert.match(await page.locator('.preview-image').getAttribute('src'), /^blob:/)
    const raw = state.requests.find(r => r.url.pathname.endsWith('/raw'))
    assert.equal(raw.authorization, 'Bearer fixture-access'); assert.equal(raw.url.search, '')
    await page.locator('.toolbar-btn-close').click()
    assert.deepEqual(await page.evaluate(() => window.revokedUrls), await page.evaluate(() => window.objectUrls))
  })
  await run('expired image and download share authenticated refresh path', async (page, state) => {
    state.expireRaw = true
    await open(page); await select(page, 'image'); await settle(page)
    assert.match(await page.locator('.preview-image').getAttribute('src'), /^blob:/)
    const downloaded = page.waitForEvent('download')
    await page.locator('.toolbar-actions').getByRole('button', { name: '下载', exact: true }).click()
    assert.equal((await downloaded).suggestedFilename(), 'image.png')
    assert.equal(state.refreshes, 1)
    assert(state.requests.filter(r => r.url.pathname.endsWith('/raw')).every(r => !r.url.searchParams.has('token')))
  })
  await run('account change clears existing private preview', async page => {
    await open(page); await select(page, 'image'); await settle(page)
    await page.evaluate(async () => { const { useUserStore } = await import('/src/stores/user.ts'); useUserStore().clearAuth() })
    await settle(page)
    assert.equal(await page.locator('.preview-overlay').count(), 0)
    assert.deepEqual(await page.evaluate(() => window.revokedUrls), await page.evaluate(() => window.objectUrls))
  })
  await run('late preview cannot restore content after account change', async (page, state) => {
    state.delayA = true
    await open(page)
    const requested = page.waitForRequest(req => new URL(req.url()).pathname.endsWith('/a/preview'))
    await select(page, 'a'); await requested
    await page.evaluate(async () => { const { useUserStore } = await import('/src/stores/user.ts'); useUserStore().clearAuth() })
    state.releaseA?.(); await settle(page)
    assert.equal(await page.locator('.preview-overlay').count(), 0)
    assert.equal(await page.getByText('Content a', { exact: true }).count(), 0)
  })
  await run('image selection replacement releases previous object URL', async page => {
    await open(page); await select(page, 'image'); await settle(page)
    await select(page, 'b'); await page.locator('.preview-text-content').waitFor()
    assert.deepEqual(await page.evaluate(() => window.revokedUrls), await page.evaluate(() => window.objectUrls))
  })
  for (const [route, button] of [['login', '登 录'], ['register', '注 册']]) {
    await run(`invalid ${route} never submits HTTP`, async (page, state) => {
      await page.goto(base + '/' + route)
      await page.getByRole('button', { name: button, exact: true }).click()
      await settle(page)
      assert.equal(state.requests.filter(r => r.url.pathname === '/api/auth/' + route).length, 0)
      assert(await page.getByText('请输入用户名', { exact: true }).isVisible())
    }, false)
  }
  await run('invalid knowledge base never submits HTTP', async (page, state) => {
    await page.goto(base + '/workspace/knowledge-bases')
    await page.getByRole('button', { name: '新建知识库', exact: true }).click()
    await page.getByRole('button', { name: '创建', exact: true }).click()
    await settle(page)
    assert.equal(state.requests.filter(r => r.url.pathname === '/api/knowledge-bases' && r.method === 'POST').length, 0)
  })
  const navigate = (page, id) => page.evaluate(async agentId => {
    const router = document.querySelector('#app').__vue_app__.config.globalProperties.$router
    await router.push({ path: '/workspace/chat', query: agentId ? { agent_id: agentId } : {} })
  }, id)
  await run('shared Agent query selects exact detail and no-query keeps default', async (page, state) => {
    await page.goto(base + '/workspace/chat?agent_id=shared')
    await page.getByRole('heading', { name: 'Assistant shared', exact: true }).waitFor()
    assert.equal(state.requests.filter(r => r.url.pathname === '/api/agents').length, 0)
    await navigate(page)
    await page.getByRole('heading', { name: 'Default assistant', exact: true }).waitFor()
    await navigate(page, 'private'); await settle(page)
    assert.equal(await page.getByRole('heading', { name: 'Default assistant', exact: true }).count(), 0)
    assert.equal(state.requests.filter(r => r.url.pathname === '/api/agents').length, 1)
  })
  await run('Agent query switch discards late detail and old stream', async (page, state) => {
    const slow = page.waitForRequest(req => new URL(req.url()).pathname === '/api/agents/slow')
    await page.goto(base + '/workspace/chat?agent_id=slow')
    await slow
    await navigate(page, 'next')
    await page.getByRole('heading', { name: 'Assistant next', exact: true }).waitFor()
    state.releaseAgent?.(); await settle(page)
    assert.equal(await page.getByRole('heading', { name: 'Assistant next', exact: true }).count(), 1)
    await page.locator('textarea').fill('synthetic question')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await page.getByRole('button', { name: '停止', exact: true }).waitFor()
    await navigate(page, 'last')
    await page.getByRole('heading', { name: 'Assistant last', exact: true }).waitFor()
    state.releaseStream?.(); await settle(page)
    assert.equal(await page.locator('.message-wrapper').count(), 0)
    assert.equal(await page.getByText('OLD PRIVATE STREAM').count(), 0)
  })
  await browser.close()
  if (failures) process.exitCode = 1
})().catch(error => { console.error(error); process.exitCode = 1 })
