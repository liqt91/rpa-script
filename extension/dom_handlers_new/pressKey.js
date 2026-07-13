/**
 * pressKey — DOM handler.
 *
 * humanLike=true:  runner handles OS key press; content script just returns viewport coords.
 * humanLike=false: content script dispatches synthetic KeyboardEvent.
 */
registerHandler('pressKey', async function({ extra }) {
  const key = extra?.key || 'Enter';
  const humanLike = extra?.humanLike ?? true;
  const modifiers = extra?.modifiers || '';

  // Get active element viewport coords for OS mouse movement
  const el = document.activeElement || document.body;
  const rect = el.getBoundingClientRect();
  const viewX = Math.round(rect.left + rect.width / 2);
  const viewY = Math.round(rect.top + rect.height / 2);
  _ensureCalibrationCapture();

  // When humanLike=true, runner handles OS key — skip synthetic
  if (!humanLike) {
    const modList = Array.isArray(modifiers) ? modifiers
      : modifiers.split(',').map(s => s.trim()).filter(Boolean);
    const ctrlKey = modList.includes('Ctrl');
    const altKey = modList.includes('Alt');
    const shiftKey = modList.includes('Shift');
    const metaKey = modList.includes('Meta');

    console.warn('[RPA pressKey] key=' + key + ' modifiers=' + (modList.join(',') || 'none'));

    const init = { key, bubbles: true, ctrlKey, altKey, shiftKey, metaKey };
    const target = document.activeElement || document.body;
    target.dispatchEvent(new KeyboardEvent('keydown', init));
    if (!['Control', 'Alt', 'Shift', 'Meta'].includes(key)) {
      await sleep(randNormal(80, 30));
    }
    target.dispatchEvent(new KeyboardEvent('keyup', init));
  }

  let cal = null;
  try { const raw = sessionStorage.getItem('_rpaHoverCal'); if (raw) cal = JSON.parse(raw); } catch (_) {}
  if (cal) {
    const dpr = window.devicePixelRatio || 1;
    return { pressed: key, viewX, viewY,
      screenX: Math.round((cal.offX + viewX) * dpr),
      screenY: Math.round((cal.offY + viewY) * dpr) };
  }
  return { pressed: key, viewX, viewY, dpr: window.devicePixelRatio || 1, _needsCalib: true };
});
