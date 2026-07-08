

registerHandler('scrollToBottom', async (args) => {
      args.extra = { ...(args.extra || {}), action: 'scrollToBottom' };
      return doScroll(args);
  });
