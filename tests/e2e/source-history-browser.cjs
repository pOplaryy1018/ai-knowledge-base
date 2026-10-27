/* Synthetic browser contract for publication history and explicit rollback. */
const { chromium } = require('playwright')
const assert = require('node:assert/strict')

;(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'chrome' })
  const page = await browser.newPage()
  await page.addInitScript(() => localStorage.setItem('akb_access_token', 'history-fixture-token'))
  const source = { id: 'source-a', name: '合成来源', kind: 'document', knowledge_base_id: 'kb-a',
    current_revision_id: 'revision-b', current_publication_id: 'publication-b', active_task_id: null, archived_at: null }
  const other = { id: 'source-b', name: '另一份来源', kind: 'document', knowledge_base_id: 'kb-a',
    current_revision_id: null, current_publication_id: null, active_task_id: null, archived_at: null }
  const revisions = [
    { id: 'revision-b', filename: 'b.txt', state: 'ready', created_at: '2026-10-26T00:00:00Z', published_at: '2026-10-26T00:00:00Z' },
    { id: 'revision-a', filename: 'a.txt', state: 'ready', created_at: '2026-10-25T00:00:00Z', published_at: '2026-10-25T00:00:00Z' },
  ]
  const publications = [
    { id: 'publication-b', revision_id: 'revision-b', sequence: 2, created_at: '2026-10-26T00:00:00Z' },
    { id: 'publication-a', revision_id: 'revision-a', sequence: 1, created_at: '2026-10-25T00:00:00Z' },
  ]
  const calls = [], errors = []
  let releasePending
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/api/**', route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname
    if (!path.startsWith('/api/')) return route.continue()
    const json = value => route.fulfill({ contentType: 'application/json', body: JSON.stringify(value) })
    if (path === '/api/auth/me') return json({ id: 'user-a', username: '合成用户', role: 'user' })
    if (path === '/api/sources') return json({ items: [source, other] })
    if (path === '/api/knowledge-bases') return json({ items: [], total: 0 })
    if (path === '/api/source-repo-roots') return json({ items: [] })
    if (path === '/api/sources/source-b/publications') return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: '历史服务暂不可用' }) })
    if (path === '/api/sources/source-b/revisions') return json({ items: [{ id: 'other-rev', filename: 'other.txt', state: 'ready', created_at: '2026-10-25T00:00:00Z', published_at: '2026-10-25T00:00:00Z' }] })
    if (path.endsWith('/revisions')) return json({ items: revisions })
    if (path.endsWith('/publications')) return json({ items: publications })
    if (path.endsWith('/graph')) return json({ source_id: source.id, revision_id: source.current_revision_id, status: 'not_indexed' })
    if (path.endsWith('/rollback')) {
      calls.push(request.postDataJSON())
      if (calls.length === 2) return route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: '当前发布记录已变化，请刷新后重试' }) })
      if (calls.length === 3) return new Promise(resolve => {
        releasePending = () => route.fulfill({ contentType: 'application/json', body: JSON.stringify(source) }).then(resolve, resolve)
      })
      source.current_revision_id = 'revision-a'
      source.current_publication_id = 'publication-c'
      publications.unshift({ id: 'publication-c', revision_id: 'revision-a', sequence: 3, created_at: '2026-10-27T00:00:00Z' })
      return json(source)
    }
    return json({ items: [] })
  })
  try {
    await page.goto('http://127.0.0.1:54174/workspace/sources')
    await page.getByRole('button', { name: '合成来源', exact: true }).click()
    const history = page.getByRole('region', { name: '发布历史' })
    await history.getByText('发布 #2').waitFor({ timeout: 3000 })
    assert.equal(await history.getByText('发布 #1').count(), 1)
    await history.getByRole('button', { name: '回滚到发布 #1' }).click()
    await page.getByRole('button', { name: '取消', exact: true }).last().click()
    assert.equal(calls.length, 0)
    await history.getByRole('button', { name: '回滚到发布 #1' }).click()
    await page.getByRole('button', { name: '确认回滚' }).click()
    await history.getByText('发布 #3').waitFor()
    assert.deepEqual(calls, [{ target_revision_id: 'revision-a', expected_publication_id: 'publication-b' }])
    await history.getByRole('button', { name: '回滚到发布 #2' }).click()
    await page.getByRole('button', { name: '确认回滚' }).click()
    await page.getByText('当前发布记录已变化，请刷新后重试').waitFor()
    assert.equal(await history.getByText('发布 #3').count(), 1)
    await history.getByRole('button', { name: '回滚到发布 #2' }).click()
    const pending = page.waitForRequest(request => request.url().endsWith('/rollback'))
    await page.getByRole('button', { name: '确认回滚' }).click()
    await pending
    await page.getByRole('button', { name: '另一份来源', exact: true }).click()
    await page.getByText(/other\.txt/).waitFor({ timeout: 3000 })
    await history.getByText('历史服务暂不可用').waitFor({ timeout: 3000 })
    releasePending()
    assert.equal(await history.getByText('发布 #3').count(), 0)
    assert.deepEqual(errors, [])
    console.log('source history: display, cancel, rollback payload and refreshed publication passed')
  } finally { await browser.close() }
})().catch(error => { console.error(error); process.exitCode = 1 })
