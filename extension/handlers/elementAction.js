

registerHandler('elementAction', async function elementAction({ locator, selectorFamily, extra }) {
    const action = extra?.action;
    if (!action) throw new Error('elementAction: extra.action is required');
    switch (action) {
      case 'click':
      case 'doubleClick':
      case 'rightClick':
        return doClick({ locator, selectorFamily, extra });
      case 'clickCurrentLoopItem':
        return doClickCurrentLoopItem({ extra });
      case 'input':
      case 'inputAndPressEnter':
        return doInput({ locator, selectorFamily, extra });
      case 'extract':
      case 'getText':
      case 'getAttr':
      case 'getHtml':
      case 'getValue':
        return doExtract({ locator, selectorFamily, extra });
      case 'scroll':
      case 'scrollToBottom':
      case 'scrollToTop':
      case 'scrollOneScreen':
      case 'scrollIntoView':
      case 'scrollBy':
        return doScroll({ locator, selectorFamily, extra });
      case 'hover':
        return doHover({ locator, selectorFamily, extra });
      case 'unhover':
        return doUnhover({ locator, selectorFamily, extra });
      case 'clearInput':
        return doClearInput({ locator, selectorFamily, extra });
      case 'selectOption':
        return doSelectOption({ locator, selectorFamily, extra });
      default:
        throw new Error(`elementAction: unknown action "${action}"`);
    }
  });
