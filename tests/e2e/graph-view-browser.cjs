/* Synthetic graph UI contract: lazy loading, evidence, failure and source switch. */
const { chromium } = require('playwright')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

;(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'chrome' })
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } })
  page.setDefaultTimeout(3000)
  await page.addInitScript(() => localStorage.setItem('akb_access_token', 'graph-fixture-token'))
  const sources = [
    { id: 'source-a', name: '关系资料', kind: 'document', knowledge_base_id: 'kb', current_revision_id: 'revision-a', current_publication_id: 'publication-a', active_task_id: null, archived_at: null },
    { id: 'source-b', name: '空白资料', kind: 'document', knowledge_base_id: 'kb', current_revision_id: 'revision-b', current_publication_id: 'publication-b', active_task_id: null, archived_at: null },
  ]
  let graphCalls = 0
  let originals = 0
  let releasePending
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname
    if (!path.startsWith('/api/')) return route.continue()
    const json = value => route.fulfill({ contentType: 'application/json', body: JSON.stringify(value) })
    if (path === '/api/auth/me') return json({ id: 'user', username: '合成用户', role: 'user' })
    if (path === '/api/sources') return json({ items: sources })
    if (path === '/api/knowledge-bases') return json({ items: [], total: 0 })
    if (path.endsWith('/revisions') || path.endsWith('/publications') || path === '/api/source-repo-roots') return json({ items: [] })
    if (path.endsWith('/graph')) return json({ source_id: path.split('/')[3], revision_id: 'revision-a', status: 'completed', relation_count: 1 })
    if (path.endsWith('/graph/relations')) {
      graphCalls++
      if (graphCalls === 2) return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: '关系图谱暂时不可用，请重试' }) })
      if (graphCalls === 3) return new Promise(resolve => {
        releasePending = () => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ revision_id: 'revision-a', truncated: false, items: [{ id: 'late', subject: '甲公司', subject_type: '组织', predicate: '收购', object: '乙公司', object_type: '组织', quote: '甲公司收购乙公司。', document_id: 'document-a', revision_id: 'revision-a', locator: { logical_path: 'policy.txt' } }] }) }).then(resolve, resolve)
      })
      return json({ revision_id: 'revision-a', truncated: false, items: [{ id: 'relation-1', subject: '甲公司', subject_type: '组织', predicate: '收购', object: '乙公司', object_type: '组织', quote: '甲公司收购乙公司。', document_id: 'document-a', revision_id: 'revision-a', locator: { logical_path: 'policy.txt', line_start: 1 } }] })
    }
    if (path === '/api/sources/source-a/revisions/revision-a/original') {
      originals++
      return route.fulfill({ contentType: 'text/plain', body: '甲公司收购乙公司。' })
    }
    return json({ items: [] })
  })
  try {
    await page.goto('http://127.0.0.1:54174/workspace/sources')
    await page.getByRole('button', { name: '关系资料', exact: true }).click()
    const graph = page.getByRole('region', { name: '知识图谱' })
    assert.equal(graphCalls, 0)
    await graph.getByRole('button', { name: '查看知识图谱' }).click()
    await graph.getByRole('button', { name: /甲公司.*收购.*乙公司/ }).click()
    await graph.getByText('甲公司收购乙公司。').waitFor()
    const download = page.waitForEvent('download')
    await graph.getByRole('button', { name: '下载原件' }).click()
    await download
    assert.equal(originals, 1)
    fs.mkdirSync('docs/acceptance/graph-visualization', { recursive: true })
    await graph.screenshot({ path: path.resolve('docs/acceptance/graph-visualization/graph.png'), animations: 'disabled' })
    assert.equal(graphCalls, 1)
    await graph.getByRole('button', { name: '收起知识图谱' }).click()
    await graph.getByRole('button', { name: '查看知识图谱' }).click()
    await graph.getByText('关系图谱暂时不可用，请重试').waitFor()
    const pending = page.waitForRequest(request => request.url().endsWith('/graph/relations'))
    await graph.getByRole('button', { name: '重试' }).click()
    await pending
    await page.getByRole('button', { name: '空白资料', exact: true }).click()
    releasePending()
    assert.equal(await graph.getByText('甲公司收购乙公司。').count(), 0)
    await page.setViewportSize({ width: 390, height: 844 })
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1))
    assert.deepEqual(errors, [])
    console.log('graph UI: lazy fetch, relation evidence, failure and source switch passed')
  } finally { await browser.close() }
})().catch(error => { console.error(error); process.exitCode = 1 })
