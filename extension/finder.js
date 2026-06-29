/**
 * finder.js — Configurable CSS selector generator with multi-criteria optimization.
 *
 * Optimizes for (in order):
 *   1. Fewest attributes used (core goal: "最少属性")
 *   2. Highest stability score (Sidereal-inspired attribute ranking)
 *   3. Lowest token-type penalty (id > class > tag > nth)
 *   4. Shallowest depth
 *
 * CONFIG is exposed as window.__rpaFinderConfig so content_capture.js
 * can share the same blacklist / scoring rules.
 */
(function (global) {
  'use strict';

  // ─── Configurable rules ──────────────────────────────────────────

  const CONFIG = {
    // Blacklist patterns: any id/class/attr matching these is ignored
    blacklist: {
      id: [
        /^:[Rr][a-z0-9]*:$/,           // React root
        /^css-[a-z0-9]{4,}$/i,          // CSS-in-JS (styled-components)
        /^[a-f0-9]{10,}$/i,             // hash-only
        /^[a-f0-9]{8}$/i,               // 8-char hash
      ],
      class: [
        /^css-[a-z0-9]{4,}$/i,          // CSS-in-JS
        /^_[a-f0-9]{6,}$/i,             // Emotion / CSS Modules hash
        /_{2,}[a-z0-9]{4,}/i,           // Scoped CSS
        /^orch-/i,                      // Orchestration markers
        /^mui-/, /^chakra-/, /^ant-/,   // Component lib prefixes
        /^v-[a-f0-9]{6,}$/i,            // Vue scoped
        /^[a-z]{1,2}_[a-zA-Z0-9]{5,}$/, // Short prefix + hash (e.g. t_VddJAQ)
        /^sc-[a-zA-Z]{4,}$/,            // styled-components generated
      ],
      attr: [
        /^data-v-[a-f0-9]+$/i,          // Vue scoped style marker
        /^data-react/,                  // React internals
        /^v-/i, /^_ng/i,                // Vue / Angular
      ],
    },

    // Stability score (0–10). Higher = more stable across page changes.
    // Sidereal-inspired: data-testid > aria-label > class > tag > nth
    stability: {
      id: 10,
      'data-testid': 9.5,
      'data-test': 9,
      'data-cy': 9,
      'data-qa': 9,
      'data-e2e': 9,
      'data-id': 8,
      'data-key': 7,
      'data-name': 7,
      'aria-label': 8,
      name: 7,
      role: 5,
      placeholder: 5,
      title: 4,
      class: 3,
      tag: 1,
      'nth-of-type': 0.5,
    },

    // Weights for the multi-criteria sort key.
    // The composite key is:
    //   [ attrCount * w.attrCount,
    //    -stability * w.stability,
    //     penalty * w.penalty,
    //     depth   * w.depth ]
    weights: {
      attrCount: 100,
      stability: 10,
      penalty: 1,
      depth: 5,
    },
  };

  // ─── Helpers ─────────────────────────────────────────────────────

  function isBlacklisted(value, patterns) {
    if (!value) return true;
    return patterns.some((p) => p.test(value));
  }

  function isStableId(id) {
    if (!id || id.length > 50) return false;
    if (isBlacklisted(id, CONFIG.blacklist.id)) return false;
    const hashSegs = (id.match(/_[a-f0-9]{6,}/g) || []).length;
    if (hashSegs >= 2) return false;
    return /^[a-zA-Z][a-zA-Z0-9_\-:]*$/.test(id);
  }

  function wordLike(name) {
    if (!name || name.length < 3 || name.length > 50) return false;
    if (/^[a-f0-9]{8,}$/i.test(name)) return false;
    const words = name.split(/[-_]/);
    for (const word of words) {
      if (word.length <= 2) return false;
      const lettersOnly = word.replace(/[0-9]/g, '');
      if (lettersOnly.length >= 4 && /[^aeiouAEIOU]{4,}/.test(lettersOnly)) return false;
      // 高数字比例通常是 hash（如 189h5o3）
      const digits = (word.match(/[0-9]/g) || []).length;
      if (digits > 0 && digits / word.length > 0.5) return false;
    }
    return true;
  }

  function isStableClass(cls) {
    if (!cls || cls.length < 2) return false;
    if (isBlacklisted(cls, CONFIG.blacklist.class)) return false;
    return wordLike(cls);
  }

  // ─── Token generation ────────────────────────────────────────────

  function getTokens(node) {
    const results = [];
    const tag = node.tagName.toLowerCase();

    // id → 1 attr, penalty 0, stability 10
    if (node.id && isStableId(node.id)) {
      results.push({
        name: '#' + CSS.escape(node.id),
        penalty: 0,
        attrCount: 1,
        stabilityScore: CONFIG.stability.id,
        type: 'id',
      });
    }

    // stable classes → 1 attr each, penalty 1, stability 3
    if (node.classList) {
      for (const cls of node.classList) {
        if (isStableClass(cls)) {
          results.push({
            name: '.' + CSS.escape(cls),
            penalty: 1,
            attrCount: 1,
            stabilityScore: CONFIG.stability.class,
            type: 'class',
          });
        }
      }
    }

    // tag → 0 attr, penalty 2, stability 1
    results.push({
      name: tag,
      penalty: 2,
      attrCount: 0,
      stabilityScore: CONFIG.stability.tag,
      type: 'tag',
    });

    // nth-of-type → 0 attr, penalty 3, stability 0.5
    const parent = node.parentElement;
    if (parent) {
      const siblings = Array.from(parent.children).filter((c) => c.tagName === node.tagName);
      const idx = siblings.indexOf(node) + 1;
      results.push({
        name: siblings.length === 1 ? tag : `${tag}:nth-of-type(${idx})`,
        penalty: 3,
        attrCount: 0,
        stabilityScore: CONFIG.stability['nth-of-type'],
        type: 'nth-of-type',
      });
    }

    return results;
  }

  // ─── Composite sort key ──────────────────────────────────────────

  function computeSortKey(item) {
    const w = CONFIG.weights;
    let attrs = 0;
    let stability = 0;
    let penalty = 0;
    for (const t of item.path) {
      attrs += t.attrCount || 0;
      stability += t.stabilityScore || 0;
      penalty += t.penalty || 0;
    }
    // Return an array for lexicographic compare.
    // Lower is better, except stability where higher is better (negated).
    return [
      attrs * w.attrCount,
      -stability * w.stability,
      penalty * w.penalty,
      item.path.length * w.depth,
    ];
  }

  function compareSortKey(a, b) {
    const ak = computeSortKey(a);
    const bk = computeSortKey(b);
    for (let i = 0; i < ak.length; i++) {
      if (ak[i] !== bk[i]) return ak[i] - bk[i];
    }
    return 0;
  }

  // ─── Core finder ─────────────────────────────────────────────────

  function finder(element, options) {
    if (!element || element.nodeType !== Node.ELEMENT_NODE) return null;
    if (element === document.body) return 'body';

    const opts = Object.assign(
      {
        seedMinLength: 1,
        optimizedMinLength: 2,
        maxNumberOfTries: 10000,
      },
      options
    );

    let tries = 0;
    const queue = [];

    function enqueue(path, node) {
      queue.push({ path, node });
      // Keep queue sorted by composite key (best first)
      queue.sort(compareSortKey);
    }

    // Seed queue with first-level tokens
    for (const token of getTokens(element)) {
      enqueue([token], element.parentElement);
    }

    while (queue.length > 0 && tries < opts.maxNumberOfTries) {
      const current = queue.shift();
      tries++;

      const selector = current.path.map((t) => t.name).join(' > ');

      // Test uniqueness once path is long enough
      if (current.path.length >= opts.seedMinLength) {
        let count = 0;
        try {
          count = document.querySelectorAll(selector).length;
        } catch (_e) {
          count = 0;
        }

        if (count === 1) {
          // Try to shorten from the root side
          if (opts.optimizedMinLength && current.path.length > opts.optimizedMinLength) {
            for (let i = opts.optimizedMinLength; i < current.path.length; i++) {
              const short = current.path.slice(0, i).map((t) => t.name).join(' > ');
              try {
                if (document.querySelectorAll(short).length === 1) {
                  return short;
                }
              } catch (_e) {}
            }
          }
          return selector;
        }
      }

      // Stop at body or max depth
      if (!current.node || current.node === document.body || current.path.length >= 8) {
        continue;
      }

      // Expand to next ancestor
      for (const token of getTokens(current.node)) {
        enqueue([...current.path, token], current.node.parentElement);
      }
    }

    return null;
  }

  // ─── Expose ──────────────────────────────────────────────────────

  global.__rpaFinder = finder;
  global.__rpaFinderConfig = CONFIG;
})(typeof self !== 'undefined' ? self : this);
