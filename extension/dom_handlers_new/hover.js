/**
 * hover — DOM handler.
 *
 * Hovers the mouse over the target element.
 * Delegates to doHover in content_base.js.
 */
registerHandler('hover', async function(step) {
  const { locator, selectorFamily, extra } = step;
  return await doHover({ locator, selectorFamily, extra });
});
