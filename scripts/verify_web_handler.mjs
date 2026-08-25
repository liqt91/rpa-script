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
import { readFileSync } from 'node:fs';
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
// 可选注入示例 DOM（links=[{href,text}]）让 querySelectorAll 返回真实元素
const linksJson = arg('links');
let links = null;
if (linksJson) {
  links = JSON.parse(readFileSync(expandedPath(linksJson), 'utf8').replace(/^\uFEFF/, ''));
} else {
  links = [{ href: 'https://google.com', text: 'Google' }, { href: 'https://baidu.com', text: 'Baidu' }];
}

function expandedPath(p) {
  return p.startsWith('~') ? join(process.env.HOME || '', p.slice(1)) : p;
}

// ── 最小 DOM 桩 ──
class MockEl {
  constructor(href = '', text = '') {
    this._attr = { href };
    this.href = href.startsWith('http') ? href : new URL(href, url).href;
    this.innerText = text;
    this.textContent = text;
  }
  getAttribute(k) { return this._attr[k] ?? null; }
  closest() { return null; }
  classList = { contains: () => false };
}
const mockEls = links.map((l) => new MockEl(l.href, l.text));
const mockDocument = {
  querySelectorAll: () => mockEls,
};

// stub 全局（handler 里可能用 document/window/registerHandler）
// 注意：不能解构 registerHandler 到局部 const——它是自由变量，严格模式 eval 会解析到
// 模块作用域的局部绑定导致 undefined。用 globalThis.registerHandler 即可。
globalThis.document = mockDocument;
globalThis.window = { location: { href: url } };
// checkVisibility 等共享 helper 的最小实现（真实在 content_base.js 里）
globalThis.checkVisibility = (el) => true;

// 读 handler 文件，剥离 registerHandler('...', fn) 包装取出 fn
const jsPath = join(ROOT, 'extension', 'dom_handlers_new', `${cmd}.js`);
let src = readFileSync(jsPath, 'utf8');

// 收集器模式：stub registerHandler 收集 fn，eval 整个文件（handler 通常只在文件里
// 调一次 registerHandler('cmd', async fn)，无需正则拆取）。
const handlers = {};
globalThis.registerHandler = (c, f) => { handlers[c] = f; };
try { eval(src); } catch (e) { console.error('eval handler 失败:', e.message); process.exit(1); }

// 真实 document 根（默认空）可被调用方注入：通过 extra 里的 __links 注入示例
// 简单起见，默认用空 DOM，至少验证"无匹配返回空数组 + 不抛异常"。
const fn2 = handlers[cmd];
if (!fn2) { console.error(`未注册 handler: ${cmd}`); process.exit(1); }

(async () => {
  const result = await fn2({ locator: '', selectorFamily: 'css', extra });
  console.log('🔎 结果:');
  console.log(JSON.stringify(result, null, 2));
  // 基础断言：返回对象含 value/extracted/items 之一（写变量机制），或不抛异常
  const hasWriteable = result && typeof result === 'object' &&
    ('value' in result || 'extracted' in result || 'items' in result);
  console.log(hasWriteable ? '✅ 可写回变量(value/extracted/items)' : '⚠️ 无 value/extracted/items，检查返回结构');
  process.exit(0);
})();
