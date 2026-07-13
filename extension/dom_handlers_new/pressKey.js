/**
 * pressKey — DOM handler.
 *
 * humanLike=true:  runner sends OS keybd_event directly (no mouse move).
 * humanLike=false: content script dispatches synthetic KeyboardEvent.
 */
registerHandler('pressKey', async function({ extra }) {
  const key = extra?.key || 'Enter';
  const humanLike = extra?.humanLike ?? true;
  const modifiers = extra?.modifiers || '';

  // When humanLike=true, runner sends OS key directly
  if (humanLike) {
    return { pressed: key };
  }

  // humanLike=false: synthetic event dispatch
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

  return { pressed: key };
});
