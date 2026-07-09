

registerHandler('getText', async (args) => {
      args.extra = { ...(args.extra || {}), action: 'getText' };
      return doExtract(args);
  });
