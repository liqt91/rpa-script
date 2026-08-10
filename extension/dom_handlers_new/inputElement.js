/**
 * inputElement — DOM handler.
 *
 * 模拟键盘输入（simulateKeyboard=true）: 使用操作系统真实键盘逐字输入
 * （runner 用 SendInput）。不移动鼠标/不点击 —— 获取焦点需在前面添加
 * 「点击元素」指令（见参数提示）。
 *
 * 模拟键盘输入=false: DOM 合成输入（el.value + input 事件，快速）。
 */
registerHandler('inputElement', async function inputElement({ locator, selectorFamily, extra }) {
  const el = findTarget(locator, selectorFamily, extra);
  const text = extra?.text ?? '';
  const keyboard = extra?.simulateKeyboard ?? true;

  if (!keyboard) {
    // DOM 合成输入
    el.focus();
    if (extra?.clearFirst !== false) el.value = '';
    el.value = text;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    if (extra?.pressEnter === true) {
      const keyInit = { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, cancelable: true };
      const notCancelled = el.dispatchEvent(new KeyboardEvent('keydown', keyInit));
      el.dispatchEvent(new KeyboardEvent('keypress', keyInit));
      el.dispatchEvent(new KeyboardEvent('keyup', keyInit));
      const form = el.form;
      if (notCancelled && form && typeof form.requestSubmit === 'function') {
        try { form.requestSubmit(); } catch (_) {}
      }
    }
    el.dispatchEvent(new Event('change', { bubbles: true }));
    return { input: text, length: text.length };
  }

  // 模拟键盘输入 → OS 级真实键入（SendInput）。先把目标浏览器窗口/标签页置前台，
  // 确保真实按键送达；焦点由前面的「点击元素」指令提供。
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  await sleep(randNormal(300, 100));
  el.focus();
  try {
    await chrome.runtime.sendMessage({ action: 'activateWindow' });
    await sleep(200);
  } catch (_) {}
  return {
    input: text,
    length: text.length,
    osType: text,
    osClear: extra?.clearFirst !== false,
    osEnter: extra?.pressEnter === true,
  };
});
