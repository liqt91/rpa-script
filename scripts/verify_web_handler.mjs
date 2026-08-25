#!/usr/bin/env node
/** 网页指令(extension) JS handler 验证桩 — 不依赖浏览器扩展，绕开"重载扩展"问题。
 *
 * 用法: node scripts/verify_web_handler.mjs <cmd> [--extra '<json>'] [--url '<page>']
 *   - 读取 extension/dom_handlers_new/<cmd>.js，stub registerHandler/document，
 *     在 Node 里执行 handler 逻辑，注入 mock DOM + extra 参数，跑一遍断言结果。
 *   - 用于：生成 extension 指令后无需重载浏览器扩展即可验证 JS 逻辑。
 *
 * 说明：
 *   - 只 stub 最常用的 DOM API（querySelectorAll/getAttribute/href/innerText/textContent
 *     /closest/classList 等）。若 handler 用到更冷门的 DOM API，需要在这个桩里补。
 *   - 不加载 content_base.js 的共享 helper（checkVisibility 等），桩里提供最小实现。
 */
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const ROOT = join(import.meta.dirname, '..');
const cmd = process.argv[2];
if (!cmd) { console.error('用法: node scripts/verify_web_handler.mjs <cmd> [--extra <json>] [--extra-file <path>] [--url <page>]'); process.exit(1); }

function arg(name) {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 ? process.argv[i + 1] : null;
}
const extraFile = arg('extra-file');
const extraRaw = arg('extra') || '{}';
const url = arg('url') || 'https://example.com';
// 优先读文件(规避命令行 JSON 引号被 shell 吞掉，尤其 PowerShell 下)；否则解析 --extra
const extra = extraFile
  ? JSON.parse(readFileSync(expandedPath(extraFile), 'utf8').replace(/^\uFEFF/, ''))
  : JSON.parse(extraRaw.replace(/"/g, '"'));  // 若 shell 吞了双引号则尽力恢复
// 可选注入示例 DOM：links=[{href,text}] 供链接类指令(getLinksByRegex 等)；
// images=[{src,currentSrc,alt,attrs:{src,data-src,srcset,...}}] 供图片类指令(getAllImages 等)。
// 均未注入时提供一套默认元素，保证指令能回到非空结果、真正跑到分支逻辑。
const linksJson = arg('links');
let links = null;
if (linksJson) {
  links = JSON.parse(readFileSync(expandedPath(linksJson), 'utf8').replace(/^\uFEFF/, ''));
} else {
  links = [
    { href: 'https://google.com', text: 'Google' },
    { href: 'https://baidu.com', text: 'Baidu' },
    { href: 'mailto:sales@example.com', text: 'Email us' },
  ];
}
const imagesJson = arg('images');
let images = null;
if (imagesJson) {
  images = JSON.parse(readFileSync(expandedPath(imagesJson), 'utf8').replace(/^\uFEFF/, ''));
} else {
  images = [
    { src: '/img/hero.png', currentSrc: '', alt: 'Hero', naturalWidth: 1200, naturalHeight: 800,
      attrs: { src: '/img/hero.png', 'data-src': '/img/hero-lazy.png',
        srcset: '/img/hero-480.png 480w, /img/hero-960.png 960w' } },
    { src: 'data:image/png;base64,AAAA', currentSrc: '', alt: 'DataURI',
      attrs: { src: 'data:image/png;base64,AAAA' } },
  ];
}

function expandedPath(p) {
  return p.startsWith('~') ? join(process.env.HOME || '', p.slice(1)) : p;
}

// ── 最小 DOM 桩 ──
// 通用元素（表单/标签/meta 等）：tagName/type/value/attrs/innerText/parentElement。
class MockTag {
  constructor({ tag = 'div', type = '', value = '', attrs = {}, text = '' } = {}) {
    this.tagName = tag.toUpperCase();
    this.type = type;
    this.value = value;
    this._attr = { ...attrs };
    this.innerText = text;
    this.textContent = text;
    this.parentElement = null;
    this.classList = { contains: () => false };
  }
  getAttribute(k) { return this._attr[k] ?? null; }
  closest() { return null; }
}

class MockEl {
  constructor(href = '', text = '') {
    this._attr = { href };
    this.href = href.startsWith('http') ? href : new URL(href, url).href;
    this.innerText = text;
    this.textContent = text;
    this.tagName = 'A';
    this.parentElement = null;
  }
  getAttribute(k) { return this._attr[k] ?? null; }
  closest() { return null; }
  classList = { contains: () => false };
}
const mockEls = links.map((l) => new MockEl(l.href, l.text));

// <img> 桩：.src/.currentSrc 解析为绝对地址（对相对路径），getAttribute 读原始属性，含尺寸/alt。
class MockImg {
  constructor(o = {}) {
    this._base = url;
    this._src = o.src || '';
    this._currentSrc = o.currentSrc || '';
    this._attr = { ...(o.attrs || {}) };
    this.alt = o.alt ?? '';
    this.naturalWidth = o.naturalWidth ?? 0;
    this.naturalHeight = o.naturalHeight ?? 0;
    this.width = o.width ?? 0;
    this.height = o.height ?? 0;
    this.tagName = 'IMG';
    this.parentElement = null;
    this.complete = o.complete ?? true;
  }
  get src() { return this._resolve(this._src); }
  get currentSrc() { return this._resolve(this._currentSrc); }
  _resolve(v) {
    if (!v) return '';
    try { return new URL(v, this._base).href; } catch { return v; }
  }
  getAttribute(k) { return this._attr[k] ?? null; }
  closest() { return null; }
  classList = { contains: () => false };
}
const mockImgs = images.map((o) => new MockImg(o));

// 表单控件默认集（供 getAllFormFields 等）
const mockForms = [
  new MockTag({ tag: 'input', type: 'text', value: '', attrs: { name: 'email', type: 'text', placeholder: 'name@example.com' } }),
  new MockTag({ tag: 'input', type: 'hidden', value: '123', attrs: { name: 'tid', type: 'hidden' } }),
  new MockTag({ tag: 'textarea', type: 'textarea', value: '', attrs: { name: 'msg' } }),
  new MockTag({ tag: 'select', type: 'select', value: 'free', attrs: { name: 'plan' } }),
];
// meta 默认集（供 getPageInfo 等）
const mockMetas = [
  new MockTag({ tag: 'meta', attrs: { name: 'description', content: 'Example page' } }),
  new MockTag({ tag: 'meta', attrs: { name: 'keywords', content: 'rpa, automation' } }),
  new MockTag({ tag: 'meta', attrs: { property: 'og:title', content: 'Example Title' } }),
];
const mockLabels = [];

// 按选择器类型分流返回对应 mock 元素，让指令真正跑到分支逻辑。
// 逐个逗号片段解析首字母 tag（'a[href]'→a、'input'→input），避免子串误判（如 textarea 含 'a'）。
function queryAll(selector) {
  const s = (selector || '').trim();
  if (s === '*') return [...mockEls, ...mockImgs, ...mockForms, ...mockMetas];
  const kind = {
    img: mockImgs, a: mockEls, input: mockForms, textarea: mockForms,
    select: mockForms, meta: mockMetas, label: mockLabels,
  };
  const seen = new Set();
  const out = [];
  const push = (arr) => { for (const e of arr) { if (!seen.has(e)) { seen.add(e); out.push(e); } } };
  for (const part of s.split(',')) {
    const p = part.trim();
    const m = p.match(/^([a-zA-Z][a-zA-Z0-9]*)/);
    if (m) {
      const tag = m[1].toLowerCase();
      if (kind[tag]) push(kind[tag]);
    } else if (p.includes('href')) {
      // 无 tag 但带 href（如 '[href]'）→ 链接
      push(mockEls);
    }
  }
  return out;
}
const mockDocument = {
  baseURI: url,
  title: 'Example Page',
  URL: url,
  documentElement: { lang: 'en' },
  body: { innerText: 'Contact us at sales@example.com for more info.' },
  querySelectorAll: queryAll,
};

// stub 全局（handler 里可能用 document/window/registerHandler）
// 注意：不能解构 registerHandler 到局部 const——它是自由变量，严格模式 eval 会解析到
// 模块作用域的局部绑定导致 undefined。用 globalThis.registerHandler 即可。
globalThis.document = mockDocument;
globalThis.window = { location: { href: url } };
// checkVisibility 等共享 helper 的最小实现（真实在 content_base.js 里）
globalThis.checkVisibility = (el) => true;

// 读 handler 文件：background_handlers 优先（存在且 dom 不存在 → 后台 handler），否则 dom_handlers_new。
const bgJs = join(ROOT, 'extension', 'background_handlers', `${cmd}.js`);
const domJs = join(ROOT, 'extension', 'dom_handlers_new', `${cmd}.js`);
let srcPath;
let isBackground = false;
if (existsSync(bgJs) && !existsSync(domJs)) {
  srcPath = bgJs;
  isBackground = true;
} else {
  srcPath = domJs;
}
let src;
try { src = readFileSync(srcPath, 'utf8'); }
catch (e) { console.error(`找不到 handler 文件: ${srcPath}`); process.exit(1); }

// 收集器模式：stub registerHandler / registerBackgroundHandler 收集 fn，eval 整个文件。
const handlers = {};
globalThis.registerHandler = (c, f) => { handlers[c] = f; };
globalThis.registerBackgroundHandler = (c, f) => { handlers[c] = f; };
try { eval(src); } catch (e) { console.error('eval handler 失败:', e.message); process.exit(1); }

const fn2 = handlers[cmd];
if (!fn2) { console.error(`未注册 handler: ${cmd}`); process.exit(1); }

// chrome.\* 桩（后台 handler 用）：tabs.query 按 windowId 过滤、返回默认 Tab 集。
const defaultTabs = [
  { index: 0, id: 1, windowId: 1, title: 'Google', url: 'https://google.com', active: true, pinned: false, discarded: false },
  { index: 1, id: 2, windowId: 1, title: 'Baidu', url: 'https://baidu.com', active: false, pinned: true, discarded: false },
  { index: 2, id: 3, windowId: 1, title: 'New Tab', url: 'chrome://newtab/', active: false, pinned: false, discarded: false },
];
globalThis.chrome = {
  tabs: {
    query: async (q = {}) => (q.windowId == null) ? defaultTabs : defaultTabs.filter((t) => t.windowId === q.windowId),
    update: async (id, props) => ({ id, ...props }),
    get: async (id) => defaultTabs.find((t) => t.id === id) || { id, windowId: 1, url: 'https://example.com', status: 'complete', active: true },
  },
  windows: { update: async (id, props) => ({ id, ...props }) },
};

(async () => {
  let result;
  if (isBackground) {
    // 后台 handler 签名：registerBackgroundHandler(cmd, async (step, agent) => {...})
    const agent = { workWindowId: 1, _persistWorkState: async () => {}, _injectContentScript: async () => {} };
    result = await fn2({ stepId: 'verify', type: cmd, extra }, agent);
  } else {
    // DOM handler 签名：registerHandler(cmd, async (args) => {...})
    result = await fn2({ locator: '', selectorFamily: 'css', extra });
  }
  console.log('🔎 结果:');
  console.log(JSON.stringify(result, null, 2));
  // 基础断言：返回对象含 value/extracted/items 之一（写变量机制），或不抛异常
  const hasWriteable = result && typeof result === 'object' &&
    ('value' in result || 'extracted' in result || 'items' in result);
  console.log(hasWriteable ? '✅ 可写回变量(value/extracted/items)' : '⚠️ 无 value/extracted/items，检查返回结构');
  process.exit(0);
})();
