/**
 * takeScreenshot — DOM handler.
 *
 * Captures a screenshot of the page or a specific element.
 * Uses chrome.runtime.sendMessage to request capture from the background.
 */
registerHandler('takeScreenshot', async function({ locator, selectorFamily, extra }) {
  const mode = getVisibilityMode(extra);
  if (locator) {
    // Screenshot of a specific element
    const timeoutMs = (extra?.timeout ?? 10) * 1000;
    const el = await waitForElement(locator, selectorFamily, mode, timeoutMs);
    el.scrollIntoView({ block: 'center', behavior: 'instant' });
    await sleep(200);
    const rect = el.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const resp = await chrome.runtime.sendMessage({
      action: 'captureElementScreenshot',
      rect: { left: rect.left, top: rect.top, width: rect.width, height: rect.height },
      dpr,
    });
    if (resp?.error) throw new Error(`截图失败: ${resp.error}`);
    return { dataUrl: resp.dataUrl, elementScreenshot: true };
  }
  // Full page screenshot
  const resp = await chrome.runtime.sendMessage({ action: 'captureScreenshot' });
  if (resp?.error) throw new Error(`截图失败: ${resp.error}`);
  return { dataUrl: resp.dataUrl, elementScreenshot: false };
});
