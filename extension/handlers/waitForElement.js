// ─── waitForElement / waitForElementHide ─────────────────────────

registerHandler('waitForElement', async function waitForElementHandler({ locator, selectorFamily, extra }) {
    const mode = getVisibilityMode(extra);
    const timeoutMs = (extra?.timeout ?? 10) * 1000;
    await waitForElement(locator, selectorFamily, mode, timeoutMs);
    return { appeared: true };
  });
