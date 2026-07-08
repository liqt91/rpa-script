

registerHandler('getValue', async (args) => {
      args.extra = { ...(args.extra || {}), action: 'getValue' };
      return doExtract(args);
  });
