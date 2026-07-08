

registerHandler('getAttribute', async (args) => {
      args.extra = { ...(args.extra || {}), action: 'getAttr' };
      return doExtract(args);
  });
