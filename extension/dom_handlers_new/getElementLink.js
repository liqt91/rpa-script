/**
 * getElementLink — DOM handler.
 *
 * Self-contained implementation: extracts the href attribute.
 */
registerHandler('getElementLink', async function getElementLink({ locator, selectorFamily, extra }) {
  const el = findTarget(locator, selectorFamily, extra);
  const value = (el && el.getAttribute) ? (el.getAttribute('href') || '') : '';
  return { value, text: value, extracted: value };
});
