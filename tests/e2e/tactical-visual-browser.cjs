/* Browser checks for the dark tactical form states shared by both apps. */
const { chromium } = require('playwright')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

function rgb(value) {
  return [...value.matchAll(/[\d.]+/g)].slice(0, 3).map(match => Number(match[0]))
}
function luminance([red, green, blue]) {
  const channel = value => {
    const srgb = value / 255
    return srgb <= .04045 ? srgb / 12.92 : ((srgb + .055) / 1.055) ** 2.4
  }
  return .2126 * channel(red) + .7152 * channel(green) + .0722 * channel(blue)
}
function contrast(a, b) {
  const l1 = luminance(rgb(a)), l2 = luminance(rgb(b))
  return (Math.max(l1, l2) + .05) / (Math.min(l1, l2) + .05)
}

;(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'chrome' })
  try {
    for (const [name, url] of [
      ['user login', 'http://127.0.0.1:54174/login'],
      ['user register', 'http://127.0.0.1:54174/register'],
      ['admin login', 'http://127.0.0.1:54173/login'],
    ]) {
      const page = await browser.newPage({ viewport: { width: 1280, height: 800 } })
      await page.goto(url)
      for (const [index, input] of (await page.locator('.arco-input-wrapper input').all()).entries()) {
        await input.focus()
        const state = await input.evaluate(element => {
          const wrapper = element.closest('.arco-input-wrapper')
          const style = getComputedStyle(wrapper)
          return {
            background: style.backgroundColor,
            border: style.borderColor,
            text: getComputedStyle(element).color,
            shadow: style.boxShadow,
          }
        })
        assert(contrast(state.text, state.background) >= 4.5, `${name}: input text contrast is too low`)
        assert(luminance(rgb(state.background)) < .08, `${name}: focused input must stay dark; got ${state.background}`)
        assert(!state.border.includes('22, 93, 255'), `${name}: default blue focus border leaked`)
        assert(!state.shadow.includes('190, 218, 255'), `${name}: default blue focus glow leaked`)
        if (name === 'user login' && index === 0) {
          const output = path.resolve('docs/acceptance/frontend-final/login-focused.png')
          fs.mkdirSync(path.dirname(output), { recursive: true })
          await page.screenshot({ path: output, animations: 'disabled' })
        }
      }
      await page.close()
      console.log(`${name}: focused inputs retain dark background and readable contrast`)
    }
  } finally { await browser.close() }
})().catch(error => { console.error(error); process.exitCode = 1 })
