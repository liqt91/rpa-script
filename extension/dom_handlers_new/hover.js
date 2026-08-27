/**
 * hover — DOM handler.
 *
 * Self-contained hover implementation. Moves the real OS cursor to the element
 * (runner) via returned coords; no click is performed.
 */
registerHandler('hover', async function hover({ locator, selectorFamily, extra }) {
  const el = findTarget(locator, selectorFamily, extra);
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  await sleep(extra?.hoverDelayMs ?? 400);
  const rect = el.getBoundingClientRect();
  const viewX = Math.round(rect.left + rect.width / 2);
  const viewY = Math.round(rect.top + rect.height / 2);
  _captureCalibrationOnce();
  return { hovered: true, ...coordsResult(viewX, viewY) };
});
