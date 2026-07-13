/**
 * getElementLink — DOM handler.
 * Extracts the href attribute from an element.
 */
registerHandler('getElementLink', async (args) => {
  args.extra = { ...(args.extra || {}), action: 'getAttr', attribute: 'href' };
  return doExtract(args);
});
