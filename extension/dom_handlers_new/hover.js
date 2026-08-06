/**
 * hover — DOM handler.
 *
 * Self-contained hover implementation. Moves the real OS cursor to the element
 * (runner) via returned coords; no click is performed.
 */
registerHandler('hover', async function hover({ locator, selectorFamily }) {
  const el = findTarget(locator, selectorFamily);
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  await sleep(400);
  const rect = el.getBoundingClientRect();
  const viewX = Math.round(rect.left + rect.width / 2);
  const viewY = Math.round(rect.top + rect.height / 2);
  _ensureCalibrationCapture();
  return { hovered: true, ...coordsResult(viewX, viewY) };
});
