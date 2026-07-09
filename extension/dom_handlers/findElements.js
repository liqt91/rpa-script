

registerHandler('findElements', async function findElements({ locator, selectorFamily, extra }) {
      const timeoutMs = (extra?.timeout ?? 10) * 1000;
      const mode = getVisibilityMode(extra);
      const ctxLocator = extra?.contextLocator;
      const ctxLocatorType = extra?.contextLocatorType;
      const ctxIndex = extra?.contextIndex ?? 0;
      const srcLocator = extra?.sourceLocator;
      const srcLocatorType = extra?.sourceSelectorFamily;
      const srcIndex = extra?.sourceIndex ?? 0;
      const start = Date.now();
      let elements = [];
      while (Date.now() - start < timeoutMs) {
        let parent = null;
        if (ctxLocator) {
          const parents = resolveAllLocators(ctxLocator, ctxLocatorType);
          parent = parents[ctxIndex];
        }
        if (!parent && srcLocator) {
          const parents = resolveAllLocators(srcLocator, srcLocatorType);
          parent = parents[srcIndex];
        }
        if (extra?.useRelative && extra?.relativeLocator && parent) {
          elements = resolveAllRelativeInContext(extra.relativeLocator, extra.relativeSelectorFamily, parent);
        } else if (parent) {
          elements = resolveAllLocatorsInContext(locator, selectorFamily, parent);
        } else {
          elements = resolveAllLocators(locator, selectorFamily);
        }
        const rawCount = elements.length;
        if (mode !== 'any') {
          elements = elements.filter(el => checkVisibility(el, mode));
        }
        console.log(`[RPA findElements] raw=${rawCount} filtered=${elements.length} mode=${mode} locator=${JSON.stringify(locator)} ctx=${ctxLocator ? 'yes' : 'no'}`);
        if (elements.length > 0) break;
        await sleep(200);
      }
      const items = elements.map((el, idx) => ({
        text: el.textContent?.trim() ?? '',
        html: el.innerHTML?.slice(0, 500) ?? '',
        tagName: el.tagName,
        index: idx,
        contextLocator: getElementXPath(el),
        contextLocatorType: 'xpath',
      }));
      return { count: items.length, items };
    });
