const { chromium } = require('playwright')
const assert = require('node:assert/strict')

;(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'chrome' })
  const page = await browser.newPage()
  page.on('pageerror', error => console.error('page error:', error.message))
  await page.addInitScript(() => localStorage.setItem('akb_access_token', 'fixture-token'))
  await page.route('**/api/**', route => {
    const url = new URL(route.request().url())
    if (!url.pathname.startsWith('/api/')) return route.continue()
    const json = data => route.fulfill({ contentType: 'application/json', body: JSON.stringify(data) })
    if (url.pathname === '/api/auth/me') return json({ id: 'user', username: '合成用户', role: 'user' })
    if (url.pathname === '/api/sources') return json({ items: [{ id: 'source', name: '合成来源', kind: 'document', current_revision_id: 'v1', archived_at: null }] })
    if (url.pathname === '/api/chat/scoped') {
      const events = [['meta', { conversation_id: 'c' }], ['token', { content: '回答[99]' }], ['citations', []], ['warning', { message: '回答中可能有未匹配原文的引用标记，请核对。' }], ['done', { message_id: 'm', conversation_id: 'c' }]]
      return route.fulfill({ contentType: 'text/event-stream', body: events.map(([type, data]) => `event: ${type}\ndata: ${JSON.stringify(data)}\n\n`).join('') })
    }
    if (url.pathname === '/api/reviews/review-1') return json({ id: 'review-1', decision: 'pending', historical_evidence_results: [], answer: { id: 'answer-1', question: '合成问题', content: '原答案', evidence: [] } })
    if (url.pathname === '/api/answers/answer-1/candidates') return json({ id: 'candidate', content: '候选[99]', citations: [], source_versions: {}, warning: '回答中可能有未匹配原文的引用标记，请核对。' })
    return json({ items: [] })
  })
  try {
    await page.goto('http://127.0.0.1:54174/workspace/reviews/review-1')
    await page.getByRole('button', { name: '生成候选答案' }).click({ timeout: 5000 }).catch(async error => { console.error(page.url(), await page.locator('body').innerText()); throw error })
    await page.getByText('回答中可能有未匹配原文的引用标记，请核对。').waitFor({ timeout: 3000 })
    assert.equal(await page.getByText('候选[99]').count(), 1)
    await page.goto('http://127.0.0.1:54174/workspace/personal-chat')
    await page.locator('.arco-select-view').click()
    await page.locator('.arco-select-option').filter({ hasText: '合成来源' }).click()
    await page.locator('h2').click()
    await page.locator('textarea').fill('合成问题')
    await page.getByRole('button', { name: '提问', exact: true }).click()
    await page.getByText('回答中可能有未匹配原文的引用标记，请核对。').waitFor({ timeout: 3000 })
    console.log('review candidate and personal chat warnings are visible')
  } finally { await browser.close() }
})().catch(error => { console.error(error); process.exitCode = 1 })
