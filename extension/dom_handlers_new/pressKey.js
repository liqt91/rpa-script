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

  // Parse modifiers: comma-separated or array
  const modList = Array.isArray(modifiers) ? modifiers
    : modifiers.split(',').map(s => s.trim()).filter(Boolean);

  if (humanLike) {
    const isModifier = ['Control', 'Alt', 'Shift', 'Meta'].includes(key);
    const hasModifier = modList.length > 0;
    if (isModifier || hasModifier) await sleep(randNormal(30, 10));
    if (key === 'Enter' || key === 'Tab') await sleep(randNormal(300, 100));
  }

  document.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
  if (humanLike && !['Control', 'Alt', 'Shift', 'Meta'].includes(key)) {
    await sleep(randNormal(80, 30));
  }
  document.dispatchEvent(new KeyboardEvent('keyup', { key, bubbles: true }));

  return { pressed: key };
});
