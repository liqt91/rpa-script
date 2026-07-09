

registerHandler('scrollIntoView', async (args) => {
      args.extra = { ...(args.extra || {}), action: 'scrollIntoView' };
      return doScroll(args);
  });
