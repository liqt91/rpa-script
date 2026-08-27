// browser-dom 黄金样例（照抄改 cmd 名与逻辑）
// 放 extension/dom_handlers_new/myCmd.js，JSON 定义 handler.source 指向它。

registerHandler('myCmd', async ({ locator, selectorFamily, extra }) => {
  // 1) 有 element 参数时定位元素（无必填 element 参数时可全页面跑，locator 为空）
  const el = findTarget(locator, selectorFamily, extra);

  // 2) 读 JSON 定义的参数（extra 里就是参数名）
  const mode = getVisibilityMode(extra);
  const visible = checkVisibility(el, mode);

  // 3) 返回 dict；value/extracted 会被 runner 写回 resultVar
  return { value: visible ? '命中' : '未命中', visible };
});
