/* Synthetic route and visual-state smoke check for both frontends. */
const { chromium } = require('playwright')
const assert = require('node:assert/strict')

const apps = [
  { name: 'consumer', port: 54174, role: 'user', paths: [
    '/workspace/knowledge-bases', '/workspace/sources', '/workspace/personal-chat',
    '/workspace/chat', '/workspace/answers', '/workspace/wiki',
    '/workspace/knowledge-bases/fixture-kb', '/workspace/answers/fixture-answer',
    '/workspace/reviews/fixture-review', '/workspace/wiki/fixture-wiki',
  ] },
  { name: 'admin', port: 54173, role: 'super_admin', paths: [
    '/admin/dashboard', '/admin/statistics', '/admin/knowledge-bases',
    '/admin/files', '/admin/agents', '/admin/users',
  ] },
]

function mockApi(route, role) {
  const url = new URL(route.request().url())
  const path = url.pathname
  if (!path.startsWith('/api/')) return route.continue()
  const json = data => route.fulfill({ contentType: 'application/json', body: JSON.stringify(data) })
  if (path === '/api/auth/me') return json({ id: 'fixture-user', username: '合成用户', role })
  if (path === '/api/statistics/overview') return json({ total_items: 0, available_items: 0, total_agents: 0, today_chats: 0 })
  if (path.startsWith('/api/statistics/') || path === '/api/auth/users' || path === '/api/auth/roles') return json([])
  if (path === '/api/knowledge-bases' || path === '/api/agents') return json({ items: [], total: 0, page: 1, size: 20 })
  if (path.endsWith('/files')) return json({ items: [], total: 0 })
  if (path === '/api/sources' || path === '/api/source-repo-roots' || path === '/api/wiki/pages' || path === '/api/answers' || path === '/api/reviews') return json({ items: [] })
  if (path === '/api/chat/conversations') return json({ items: [] })
  if (path.includes('/conversations/') && path.endsWith('/messages')) return json([])
  if (path.endsWith('/graph')) return json({ status: 'pending', retryable: false })
  if (path.includes('/revisions') || path.includes('/documents')) return json({ items: [] })
  return json({ id: 'fixture', name: '合成资料', title: '合成内容', items: [], citations: [], review: null, current_revision_id: null })
}

;(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'chrome' })
  try {
    for (const app of apps) {
      const context = await browser.newContext({ viewport: { width: 1360, height: 900 } })
      await context.addInitScript(() => localStorage.setItem('akb_access_token', 'route-fixture-token'))
      await context.route('**/api/**', route => mockApi(route, app.role))
      for (const path of app.paths) {
        const started = Date.now()
        const page = await context.newPage()
        const errors = []
        page.on('pageerror', error => errors.push(error.message))
        await page.goto(`http://127.0.0.1:${app.port}${path}`, { waitUntil: 'domcontentloaded' })
        await page.waitForFunction(() => document.querySelector('#app')?.textContent?.trim().length > 0, null, { timeout: 10000 }).catch(() => {})
        const heading = page.locator('h1, h2').first()
        const title = await heading.count() ? await heading.textContent() : ''
        const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth)
        assert(scrollWidth <= 1361, `${app.name} ${path}: horizontal overflow ${scrollWidth}`)
        assert.deepEqual(errors, [], `${app.name} ${path}: browser errors`)
        const modalTrigger = ({
          '/workspace/knowledge-bases': '新建知识库',
          '/admin/knowledge-bases': '新建知识库',
          '/admin/agents': '创建 Agent',
          '/admin/users': '新建用户',
        })[path]
        if (modalTrigger) {
          await page.getByRole('button', { name: modalTrigger }).first().click()
          const modal = page.locator('.arco-modal:visible').last()
          await modal.waitFor()
          const background = await modal.evaluate(element => getComputedStyle(element).backgroundColor)
          assert(!background.includes('255, 255, 255'), `${path}: modal leaked a light background`)
          const field = modal.locator('input').first()
          if (await field.count()) {
            await field.focus()
            const fieldBackground = await field.evaluate(element => getComputedStyle(element.closest('.arco-input-wrapper')).backgroundColor)
            assert(!fieldBackground.includes('255, 255, 255'), `${path}: focused dialog field leaked a light background`)
          }
          await page.keyboard.press('Escape')
          await modal.waitFor({ state: 'hidden' })
        }
        if (path === '/admin/dashboard') {
          await page.getByRole('button', { name: '文件管理' }).click({ timeout: 2000 })
          await page.waitForURL('**/admin/files')
          assert.equal(new URL(page.url()).pathname, '/admin/files')
        }
        await page.setViewportSize({ width: 390, height: 844 })
        const mobileWidth = await page.evaluate(() => document.documentElement.scrollWidth)
        assert(mobileWidth <= 391, `${app.name} ${path}: mobile horizontal overflow ${mobileWidth}`)
        assert.deepEqual(errors, [], `${app.name} ${path}: mobile browser errors`)
        console.log(`${app.name} ${path}: ${title?.trim() || await page.locator('body').innerText().then(value => value.slice(0, 30))} (${Date.now() - started}ms)`)
        await page.close()
      }
      await context.close()
    }
  } finally { await browser.close() }
})().catch(error => { console.error(error); process.exitCode = 1 })
