/**
 * clickElement — DOM handler.
 *
 * Self-contained click implementation. Uses shared infra from content_base.js
 * (findTarget / sleep / randNormal / _captureCalibrationOnce / coordsResult).
 *
 * clickMethod（与 JSON/Python 桩三件套对应）：
 *   - auto（默认）：真实 OS 点击（humanLike=true 时 runner 移动真实鼠标并点击）；
 *     humanLike=false 且未指定 clickMethod 时退化为 js 合成。
 *   - js：页面内合成完整鼠标事件序列（mouseover/mousemove/mousedown/mouseup/click），
 *     不移动系统鼠标、后台可用，适合被固定栏遮挡的元素或反爬页。
 *   - os：强制真实 OS 点击。
 */
registerHandler('clickElement', async function clickElement({ locator, selectorFamily, extra }) {
  const el = findTarget(locator, selectorFamily, extra);
  const humanLike = extra?.humanLike ?? true;
  const clickMethod = extra?.clickMethod || (humanLike ? 'auto' : 'js');

  // ── js：合成完整鼠标事件序列（不碰真实鼠标）──
  if (clickMethod === 'js') {
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    await sleep(randNormal(400, 150));
    const rect = el.getBoundingClientRect();
    const cx = Math.round(rect.left + rect.width / 2);
    const cy = Math.round(rect.top + rect.height / 2);
    const opts = {
      bubbles: true, cancelable: true, view: window,
      clientX: cx, clientY: cy, button: 0, buttons: 1,
    };
    el.dispatchEvent(new MouseEvent('mouseover', opts));
    el.dispatchEvent(new MouseEvent('mousemove', opts));
    el.dispatchEvent(new MouseEvent('mousedown', opts));
    el.dispatchEvent(new MouseEvent('mouseup', opts));
    el.dispatchEvent(new MouseEvent('click', opts));
    await sleep(randNormal(200, 80));
    // 不带 viewX/screenX：js 模式不涉及真实鼠标，避免 runner 误触发 OS 移动分支
    return { clicked: true, osClick: false, method: 'js' };
  }

  // ── auto / os：真实 OS 点击（humanLike 控制是否移动真实鼠标）──
  if (humanLike) {
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    await sleep(randNormal(400, 150));
  }
  const rect = el.getBoundingClientRect();
  const viewX = Math.round(rect.left + rect.width / 2);
  const viewY = Math.round(rect.top + rect.height / 2);
  _captureCalibrationOnce();
  if (!humanLike) {
    const clickType = extra?.clickType || 'left';
    if (clickType === 'right') {
      el.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true }));
    } else if (clickType === 'double') {
      el.dispatchEvent(new MouseEvent('dblclick', { bubbles: true, cancelable: true }));
    } else {
      el.click();
    }
  }
  if (humanLike) await sleep(randNormal(300, 100));
  return {
    clicked: true,
    osClick: humanLike,
    method: clickMethod,
    ...coordsResult(viewX, viewY),
  };
});
