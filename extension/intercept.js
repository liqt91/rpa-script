/**
 * intercept.js — Injected into page's MAIN world via <script> tag.
 * Intercepts fetch() and XMLHttpRequest, filters by URL pattern,
 * and posts results back to content.js via window.postMessage.
 */
(function () {
  'use strict';

  if (window.__rpaInterceptActive) return;
  window.__rpaInterceptActive = true;

  // Read initial config from the <script> data-config attribute
  let _config = { mode: 'trace', urlPattern: '*', method: 'ALL', captureResponse: false };
  try {
    const el = document.getElementById('__rpa_intercept_script');
    if (el && el.dataset.config) {
      _config = JSON.parse(el.dataset.config);
    }
  } catch (_e) {}

  // Listen for runtime config updates from content.js
  window.addEventListener('message', (e) => {
    if (e.data && e.data.source === 'rpa-intercept-config') {
      _config = { ..._config, ...e.data.config };
    }
  });

  function matchPattern(url, pattern) {
    if (!pattern || pattern === '*') return true;
    const parts = pattern.split('*');
    let idx = 0;
    for (const part of parts) {
      const i = url.indexOf(part, idx);
      if (i === -1) return false;
      idx = i + part.length;
    }
    return true;
  }

  function matchMethod(method, filter) {
    if (!filter || filter === 'ALL') return true;
    return method.toUpperCase() === filter.toUpperCase();
  }

  function postTrace(url, method) {
    window.postMessage({ source: 'rpa-intercept', type: 'trace', url, method, time: Date.now() }, '*');
  }

  function postIntercept(url, method, status, body) {
    window.postMessage({ source: 'rpa-intercept', type: 'intercept', url, method, status, body, time: Date.now() }, '*');
  }

  // ── Intercept fetch ──────────────────────────────────────────────

  const _origFetch = window.fetch;
  window.fetch = function (...args) {
    const url = String(args[0] || '');
    const method = (args[1] && args[1].method) || 'GET';

    const urlMatched = matchPattern(url, _config.urlPattern);
    const methodMatched = matchMethod(method, _config.method);

    if (_config.mode === 'trace' && urlMatched) {
      postTrace(url, method);
    }

    const promise = _origFetch.apply(this, args);

    if (_config.mode === 'intercept' && urlMatched && methodMatched) {
      promise.then(async (response) => {
        try {
          const clone = response.clone();
          const text = await clone.text();
          postIntercept(url, method, response.status, text);
        } catch (_e) {}
      });
    }

    return promise;
  };

  // ── Intercept XMLHttpRequest ─────────────────────────────────────

  const _XHR = XMLHttpRequest.prototype;
  const _origOpen = _XHR.open;
  const _origSend = _XHR.send;

  _XHR.open = function (method, url) {
    this._rpaUrl = url;
    this._rpaMethod = method;
    return _origOpen.apply(this, arguments);
  };

  _XHR.send = function (body) {
    const url = this._rpaUrl || '';
    const method = this._rpaMethod || 'GET';
    const urlMatched = matchPattern(url, _config.urlPattern);
    const methodMatched = matchMethod(method, _config.method);

    if (_config.mode === 'trace' && urlMatched) {
      postTrace(url, method);
    }

    if (_config.mode === 'intercept' && urlMatched && methodMatched) {
      this.addEventListener('load', function () {
        try {
          postIntercept(url, method, this.status, this.responseText);
        } catch (_e) {}
      });
    }

    return _origSend.apply(this, arguments);
  };

  console.log('[RPA Intercept] injected, mode=' + _config.mode + ', pattern=' + _config.urlPattern);
})();
