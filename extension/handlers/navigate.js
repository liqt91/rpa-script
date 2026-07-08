

registerHandler('navigate', function navigate({ extra }) {
      const url = extra?.url;
      if (!url) throw new Error('navigate: url required');
      window.location.href = url;
      return { navigatedTo: url };
    });
