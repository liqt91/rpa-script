/**
 * rpa-dsh-plugin — DSH web client 半身（bundle）。
 *
 * 在 dsh web 侧边栏底部注册 “RPA 控制台” 入口：点击展开右侧抽屉，
 * 内嵌现有 workflow-editor SPA（http://127.0.0.1:8000/workflow-editor/）。
 *
 * 本文件由浏览器直接执行（经 /plugins/rpa-dsh-plugin/client.js 提供），
 * 保持 ES5 + var 风格，不要引入需要转译的语法。
 * 可 require 的模块见前端 staticModules：react / react/jsx-runtime / react-dom /
 * @deepseek-ai/cordis / @deepseek-ai/dsh-client-ui-primitives 等。
 */
window.__ModuleLoader__.load({
  id: "rpa-dsh-plugin",
  factory: function (require) {
    var module = { exports: {} };
    var exports = module.exports;
    var React = require("react");
    var jsxRuntime = require("react/jsx-runtime");

    var NS = "rpa-console";
    // 后端端口已随机（8100-8199，写 data/backend.port）。浏览器端无法读文件，
    // 打开抽屉时探测 /health 发现实际端口（与扩展 discovery 同法）。
    var DISCOVER_LO = 8100;
    var DISCOVER_HI = 8199;

    function discoverBackendBase() {
      return new Promise(function (resolve) {
        var tries = [];
        for (var p = DISCOVER_LO; p <= DISCOVER_HI; p++) tries.push(p);
        var idx = 0;
        var CHUNK = 25;
        function nextChunk() {
          if (idx >= tries.length) return resolve("");
          var chunk = tries.slice(idx, idx + CHUNK);
          idx += CHUNK;
          Promise.all(chunk.map(function (port) {
            return fetch("http://127.0.0.1:" + port + "/health", { mode: "cors", signal: AbortSignal.timeout(800) })
              .then(function (r) { return r.ok ? port : 0; })
              .catch(function () { return 0; });
          })).then(function (results) {
            var found = results.find(function (v) { return v > 0; });
            if (found) return resolve("http://127.0.0.1:" + found);
            nextChunk();
          });
        }
        nextChunk();
      });
    }

    var zh = {
      "action.title": "RPA 控制台",
      "action.tooltip": "打开 RPA 工作流编辑器",
      "panel.hint": "内嵌 RPA 工作流编辑器；若加载失败请确认后端已启动，或点右上角新窗口打开。",
      "panel.openExternal": "新窗口打开",
      "panel.close": "关闭"
    };
    var en = {
      "action.title": "RPA Console",
      "action.tooltip": "Open RPA workflow editor",
      "panel.hint": "Embedded RPA workflow editor; if it fails to load, make sure the backend is running or open it in a new tab.",
      "panel.openExternal": "Open in new tab",
      "panel.close": "Close"
    };

    function RpaPanel(props) {
      var openState = React.useState(false);
      var open = openState[0];
      var setOpen = openState[1];
      var editorState = React.useState("");
      var editorBase = editorState[0];
      var setEditorBase = editorState[1];
      var t = props.t;

      // 打开抽屉时探测后端端口（自动适配随机端口）
      React.useEffect(function () {
        if (!open) return;
        var alive = true;
        if (!editorBase) {
          discoverBackendBase().then(function (base) { if (alive) setEditorBase(base); });
        }
        return function () { alive = false; };
      }, [open]);

      var editorUrl = editorBase ? editorBase + "/workflow-editor/" : "";

      var iconStyle = {
        width: 32,
        height: 32,
        borderRadius: 8,
        border: "none",
        background: "transparent",
        cursor: "pointer",
        fontSize: 17,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        color: "var(--dsw-alias-label-secondary, #6b7280)"
      };

      return jsxRuntime.jsxs(React.Fragment, {
        children: [
          jsxRuntime.jsx("button", {
            type: "button",
            title: t ? t("action.tooltip") : "打开 RPA 工作流编辑器",
            onClick: function () { setOpen(!open); },
            style: iconStyle,
            children: "\u2699"
          }),
          open && jsxRuntime.jsxs("div", {
            style: {
              position: "fixed",
              top: 0,
              right: 0,
              bottom: 0,
              width: "min(1180px, 86vw)",
              background: "var(--dsw-alias-bg-page, #ffffff)",
              zIndex: 2147483000,
              display: "flex",
              flexDirection: "column",
              boxShadow: "-10px 0 40px rgba(0, 0, 0, 0.2)",
              borderLeft: "1px solid var(--dsw-alias-border-subtle, #e5e7eb)"
            },
            children: [
              jsxRuntime.jsxs("div", {
                style: {
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "10px 14px",
                  borderBottom: "1px solid var(--dsw-alias-border-subtle, #eef0f2)",
                  background: "var(--dsw-alias-bg-module-platform, #fafafa)",
                  flex: "none"
                },
                children: [
                  jsxRuntime.jsx("span", { style: { fontWeight: 600, fontSize: 14 }, children: t ? t("action.title") : "RPA 控制台" }),
                  jsxRuntime.jsx("span", { style: { fontSize: 12, color: "var(--dsw-alias-label-tertiary, #9ca3af)" }, children: t ? t("panel.hint") : "内嵌 RPA 工作流编辑器；若加载失败请确认后端已启动，或点右上角新窗口打开。" }),
                  jsxRuntime.jsx("span", { style: { flex: 1 } }),
                  jsxRuntime.jsx("a", {
                    href: editorUrl || "http://127.0.0.1:8000/workflow-editor/",
                    target: "_blank",
                    rel: "noreferrer",
                    style: { fontSize: 12, color: "var(--dsw-alias-state-business-primary, #2563eb)", textDecoration: "none" },
                    children: (t ? t("panel.openExternal") : "新窗口打开") + " \u2197"
                  }),
                  jsxRuntime.jsx("button", {
                    type: "button",
                    onClick: function () { setOpen(false); },
                    style: { border: "none", background: "transparent", cursor: "pointer", fontSize: 16, color: "var(--dsw-alias-label-secondary, #6b7280)" },
                    children: "\u2715"
                  })
                ]
              }),
              jsxRuntime.jsx("iframe", {
                src: editorUrl,
                style: { flex: 1, width: "100%", border: "none" },
                title: "RPA workflow editor"
              })
            ]
          })
        ]
      });
    }

    function apply(ctx) {
      ctx.effect(function () {
        ctx.locale.register(NS, { zh: zh, en: en });
      }, "rpa-console: dictionaries");
      ctx.slots.inject("sidebar.footer.action", function () {
        return ctx.slots.register({
          name: "sidebar.footer.action",
          id: "rpa-console",
          locale: NS,
          inject: function () { return {}; }
        }, RpaPanel);
      });
    }

    exports.apply = apply;
    exports.inject = ["slots", "locale"];
    return module.exports;
  }
});
