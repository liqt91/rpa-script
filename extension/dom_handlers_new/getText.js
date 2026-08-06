/**
 * getText — DOM handler.
 *
 * Self-contained text extraction. Future extraction commands (getValue /
 * getAttribute / ...) will each own their own handler.
 */
registerHandler('getText', async function getText({ locator, selectorFamily }) {
  const el = findTarget(locator, selectorFamily);
  const value = (el.textContent || el.innerText || '').trim();
  return { value, text: value, extracted: value };
});
