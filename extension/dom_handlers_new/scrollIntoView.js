/**
 * scrollIntoView — DOM handler.
 *
 * Self-contained scroll implementation. Future scroll commands
 * (scrollToBottom / scrollBy / ...) will each own their own handler.
 */
registerHandler('scrollIntoView', async function scrollIntoView({ locator, selectorFamily, extra }) {
  const el = findTarget(locator, selectorFamily, extra);
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  return { scrolled: true };
});
