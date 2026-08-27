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
    // 内建回读校验：写入后读回 value 比对，不一致即失败（页面脚本可能改写/拦截输入）
    const actual = el.value ?? '';
    if (actual !== text) {
      throw new Error(`输入回读校验失败：期望「${text}」，实际「${actual}」`);
    }
    return { input: text, length: text.length, inputVerified: true };
  }

  // 模拟键盘输入 → OS 级真实键入（SendInput）。先把目标浏览器窗口/标签页置前台，
  // 确保真实按键送达；焦点由前面的「点击元素」指令提供。
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  await sleep(randNormal(extra?.inputDelayMs ?? 300, (extra?.inputDelayMs ?? 300) * 0.375));
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
    // 声明式效果验证：OS 键入（SendInput）只保证按键事件被系统接受，无法保证
    // 落到目标输入框（焦点被抢时静默丢失）。runner 在键入后、回车前按此声明回读
    // 目标元素 value 比对，不一致即判定步骤失败。机制通用：任何 handler 返回
    // verifyEffect 都会获得 runner 侧回读验证，非本指令特例。
    verifyEffect: { kind: 'readbackValue', expect: text },
  };
});
