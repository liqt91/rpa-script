/**
 * pressKey — DOM handler.
 *
 * Sends a keyboard event to the page.
 * Supports modifiers (Ctrl, Alt, Shift, Meta) via extra.modifiers.
 */
registerHandler('pressKey', async function({ extra }) {
  const key = extra?.key || 'Enter';
  const humanLike = extra?.humanLike ?? true;
  const modifiers = extra?.modifiers || '';

  // Parse modifiers: comma-separated
  const modList = Array.isArray(modifiers) ? modifiers
    : modifiers.split(',').map(s => s.trim()).filter(Boolean);
  const ctrlKey = modList.includes('Ctrl');
  const altKey = modList.includes('Alt');
  const shiftKey = modList.includes('Shift');
  const metaKey = modList.includes('Meta');

  if (humanLike) {
    const isModifier = ['Control', 'Alt', 'Shift', 'Meta'].includes(key);
    if (isModifier || modList.length > 0) await sleep(randNormal(30, 10));
    if (key === 'Enter' || key === 'Tab') await sleep(randNormal(300, 100));
  }

  const init = { key, bubbles: true, ctrlKey, altKey, shiftKey, metaKey };
  document.dispatchEvent(new KeyboardEvent('keydown', init));
  if (humanLike && !['Control', 'Alt', 'Shift', 'Meta'].includes(key)) {
    await sleep(randNormal(80, 30));
  }
  document.dispatchEvent(new KeyboardEvent('keyup', init));

  return { pressed: key, modifiers: modList.length ? modList.join(',') : undefined };
});
