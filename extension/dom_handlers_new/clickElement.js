/**
 * clickElement — DOM handler.
 *
 * Self-contained click implementation. Uses shared infra from content_base.js
 * (findTarget / sleep / randNormal / _ensureCalibrationCapture / coordsResult).
 * humanLike=true: runner performs the real OS click at the returned coords.
 * humanLike=false: dispatch synthetic click (left/right/double via clickType).
 */
registerHandler('clickElement', async function clickElement({ locator, selectorFamily, extra }) {
  const el = findTarget(locator, selectorFamily);
  const humanLike = extra?.humanLike ?? true;
  if (humanLike) {
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    await sleep(randNormal(400, 150));
  }
  const rect = el.getBoundingClientRect();
  const viewX = Math.round(rect.left + rect.width / 2);
  const viewY = Math.round(rect.top + rect.height / 2);
  _ensureCalibrationCapture();
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
  return { clicked: true, osClick: true, ...coordsResult(viewX, viewY) };
});
