// ─── Condition check handlers ───────────────────────────────────

registerHandler('checkElementExists', async function checkElementExists({ locator, selectorFamily, extra }) {
      const mode = getVisibilityMode(extra);
      const timeoutMs = (extra?.timeout ?? 10) * 1000;
      try {
        await waitForElementWithContext(locator, selectorFamily, extra, mode, timeoutMs);
        return { exists: true };
      } catch (e) {
        return { exists: false };
      }
    });
