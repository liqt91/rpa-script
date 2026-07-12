/**
 * getText — DOM handler.
 *
 * Reads textContent (or specified attribute) from a matched element.
 */
registerHandler('getText', async function(args) {
  const elementName = args.extra?.elementName;
  if (!elementName) return { ok: false, error: '缺少目标元素参数' };

  const elDef = args.elements?.[elementName];
  if (!elDef) return { ok: false, error: `未找到元素定义: ${elementName}` };

  const el = findElement(elDef, 'local', 'visible');
  if (!el) return { ok: false, error: `未找到元素: ${elementName}` };

  const text = (el.textContent || '').trim();
  const resultVar = args.extra?.resultVar || 'text1';

  return { ok: true, result: text, vars: { [resultVar]: text } };
});
