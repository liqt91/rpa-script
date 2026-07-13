/**
 * scrollIntoView — DOM handler.
 *
 * Scrolls the page so the target element is visible.
 * Delegates to doScroll in content_base.js.
 */
registerHandler('scrollIntoView', async function(step) {
  const { locator, selectorFamily, extra } = step;
  return await doScroll({ locator, selectorFamily, extra: { ...extra, action: 'scrollIntoView' } });
});
