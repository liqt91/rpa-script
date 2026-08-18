/**
 * rpa-dsh-plugin — DSH web client 半身（bundle）。
 *
 * 在 dsh web 侧边栏底部注册 "RPA 控制台" 入口：点击展开右侧抽屉，
 * 内嵌现有 workflow-editor SPA（随机端口自动发现，主题与 dsh web 联动）。
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

    /** 读 dsh web 当前主题（dark/light）：body 上的 data-ds-dark-theme 属性。 */
    function readDshTheme() {
      try {
        if (document.body && document.body.hasAttribute("data-ds-dark-theme")) return "dark";
      } catch (e) {}
      return "light";
    }

    var zh = {
      "action.title": "RPA 控制台",
      "action.tooltip": "打开 RPA 工作流编辑器",
      "panel.hint": "内嵌 RPA 工作流编辑器；若加载失败请确认后端已启动，或点右上角新窗口打开。",
      "panel.openExternal": "新窗口打开",
      "panel.close": "关闭",
      "flowTab.label": "流程",
      "flowTab.notRpa": "当前目录不是 RPA 流程工作区（缺少 rpa.json）。在对话中用 rpa_project_create 初始化后，此页会自动出现。"
    };
    var en = {
      "action.title": "RPA Console",
      "action.tooltip": "Open RPA workflow editor",
      "panel.hint": "Embedded RPA workflow editor; if it fails to load, make sure the backend is running or open it in a new tab.",
      "panel.openExternal": "Open in new tab",
      "panel.close": "Close",
      "flowTab.label": "Workflow",
      "flowTab.notRpa": "This directory is not an RPA workflow workspace (rpa.json missing). Initialize it with rpa_project_create in the conversation and this tab will appear."
    };

    function RpaPanel(props) {
      var openState = React.useState(false);
      var open = openState[0];
      var setOpen = openState[1];
      var editorState = React.useState("");
      var editorBase = editorState[0];
      var setEditorBase = editorState[1];
      var themeState = React.useState(readDshTheme());
      var theme = themeState[0];
      var setTheme = themeState[1];
      var healthState = React.useState(null); // null=未知 true=在线 false=离线
      var online = healthState[0];
      var setOnline = healthState[1];
      var busyState = React.useState(false);
      var busy = busyState[0];
      var setBusy = busyState[1];
      var tipState = React.useState("");
      var tip = tipState[0];
      var setTip = tipState[1];
      var t = props.t;

      // 打开抽屉时探测后端端口 + 读当前主题
      React.useEffect(function () {
        if (!open) return;
        var alive = true;
        setTheme(readDshTheme());
        if (!editorBase) {
          discoverBackendBase().then(function (base) { if (alive) setEditorBase(base); });
        }
        return function () { alive = false; };
      }, [open]);

      // 主题联动：dsh 切换浅/深色时实时同步（MutationObserver on body）
      React.useEffect(function () {
        if (!open || typeof MutationObserver === "undefined") return;
        var mo = new MutationObserver(function () { setTheme(readDshTheme()); });
        if (document.body) mo.observe(document.body, { attributes: true, attributeFilter: ["data-ds-dark-theme"] });
        return function () { mo.disconnect(); };
      }, [open]);

      // 健康轮询：入口状态点（30s）
      React.useEffect(function () {
        if (!editorBase) return;
        var alive = true;
        var timer = null;
        var check = function () {
          fetch(editorBase + "/health", { mode: "cors", signal: AbortSignal.timeout(4000) })
            .then(function (r) { if (alive) setOnline(r.ok); })
            .catch(function () { if (alive) setOnline(false); });
        };
        check();
        timer = setInterval(check, 30000);
        return function () { alive = false; if (timer) clearInterval(timer); };
      }, [editorBase]);

      var editorUrl = editorBase
        ? editorBase + "/workflow-editor/?theme=" + theme
        : "";

      // 启动/重启后端：经 dsh web 同源 HTTP 触发插件 node 侧 spawn
      var onStartBackend = function (action) {
        if (busy) return;
        setBusy(true);
        setTip("");
        fetch("/rpa-bridge/start-backend", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: action || "start" })
        })
          .then(function (r) { return r.json().catch(function () { return {}; }); })
          .then(function (d) {
            if (d && d.ok) {
              setTip(d.already ? "后端已在运行" : "后端已启动" + (d.port ? "（端口 " + d.port + "）" : ""));
              if (!d.already) {
                // 端口可能变化 → 重新发现并刷新 iframe
                discoverBackendBase().then(function (base) { if (base) setEditorBase(base); });
              }
              setOnline(true);
            } else {
              setTip("失败: " + ((d && d.error) || "未知错误"));
            }
          })
          .catch(function (e) { setTip("请求失败: " + e.message); })
          .then(function () { setBusy(false); });
      };

      var hoverState = React.useState(false);
      var hovered = hoverState[0];
      var setHovered = hoverState[1];

      var iconStyle = {
        height: 28,
        borderRadius: 6,
        border: "none",
        background: hovered ? "var(--dsw-alias-interactive-bg-hover, rgba(0,0,0,0.06))" : "transparent",
        cursor: "pointer",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        position: "relative",
        gap: 6,
        padding: "0 10px",
        color: "var(--dsw-alias-label-secondary, #6b7280)",
        transition: "background 0.15s"
      };
      var dotStyle = {
        position: "absolute",
        right: 7,
        bottom: 3,
        width: 7,
        height: 7,
        borderRadius: "50%",
        background: online === false
          ? "var(--dsw-alias-state-danger, #e5484d)"
          : "var(--dsw-alias-state-success, #30a46c)",
        boxShadow: "0 0 0 1.5px var(--dsw-alias-bg-module-platform, #fff)",
        opacity: online === null ? 0 : 1
      };

      return jsxRuntime.jsxs(React.Fragment, {
        children: [
          jsxRuntime.jsxs("button", {
            type: "button",
            title: t ? t("action.tooltip") : "打开 RPA 工作流编辑器",
            onClick: function () { setOpen(!open); },
            onMouseEnter: function () { setHovered(true); },
            onMouseLeave: function () { setHovered(false); },
            style: iconStyle,
            children: [
              jsxRuntime.jsx("svg", {
                width: 17,
                height: 17,
                viewBox: "0 0 24 24",
                fill: "none",
                stroke: "currentColor",
                strokeWidth: 2,
                strokeLinecap: "round",
                strokeLinejoin: "round",
                children: [
                  jsxRuntime.jsx("path", { d: "M12 8V4H8" }),
                  jsxRuntime.jsx("rect", { width: 16, height: 12, x: 4, y: 8, rx: 2 }),
                  jsxRuntime.jsx("path", { d: "M2 14h2" }),
                  jsxRuntime.jsx("path", { d: "M20 14h2" }),
                  jsxRuntime.jsx("path", { d: "M15 13v2" }),
                  jsxRuntime.jsx("path", { d: "M9 13v2" })
                ]
              }),
              jsxRuntime.jsx("span", {
                style: { fontSize: 12, fontWeight: 600, letterSpacing: "0.02em" },
                children: "RPA"
              }),
              online !== null && jsxRuntime.jsx("span", { style: dotStyle, title: online ? "后端在线" : "后端离线" })
            ]
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
              boxShadow: "var(--dsw-shadow-overlay, -10px 0 40px rgba(0, 0, 0, 0.2))",
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
                  jsxRuntime.jsx("span", { style: { fontWeight: 600, fontSize: 14, color: "var(--dsw-alias-label-primary, #1f2329)" }, children: t ? t("action.title") : "RPA 控制台" }),
                  jsxRuntime.jsx("span", { style: { fontSize: 12, color: "var(--dsw-alias-label-tertiary, #9ca3af)" }, children: t ? t("panel.hint") : "内嵌 RPA 工作流编辑器；若加载失败请确认后端已启动，或点右上角新窗口打开。" }),
                  jsxRuntime.jsx("span", { style: { flex: 1 } }),
                  jsxRuntime.jsx("span", { style: { fontSize: 11, color: "var(--dsw-alias-label-tertiary, #9ca3af)" }, children: tip }),
                  jsxRuntime.jsx("button", {
                    type: "button",
                    onClick: function () { onStartBackend(online ? "restart" : "start"); },
                    disabled: busy,
                    title: online ? "重启后端" : "启动后端",
                    style: {
                      border: "1px solid var(--dsw-alias-border-subtle, #e5e7eb)",
                      background: "var(--dsw-alias-bg-module-platform, #fafafa)",
                      cursor: busy ? "wait" : "pointer",
                      borderRadius: 6,
                      padding: "3px 10px",
                      fontSize: 12,
                      color: "var(--dsw-alias-label-secondary, #6b7280)"
                    },
                    children: busy
                      ? "\u23F3 启动中..."
                      : (online ? "\u21BB 重启" : "\u25B6 启动")
                  }),
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

    /** 流程编辑 tab 内容：内嵌 workflow-editor，URL 带 project=当前目录。 */
    function FlowView(props) {
      var projectDir = props.projectDir || "";
      var themeState = React.useState(readDshTheme());
      var theme = themeState[0];
      var setTheme = themeState[1];
      var baseState = React.useState("");
      var base = baseState[0];
      var setBase = baseState[1];

      React.useEffect(function () {
        var alive = true;
        discoverBackendBase().then(function (b) { if (alive && b) setBase(b); });
        return function () { alive = false; };
      }, []);

      // 主题联动（与抽屉一致）
      React.useEffect(function () {
        if (typeof MutationObserver === "undefined") return;
        var mo = new MutationObserver(function () { setTheme(readDshTheme()); });
        if (document.body) mo.observe(document.body, { attributes: true, attributeFilter: ["data-ds-dark-theme"] });
        return function () { mo.disconnect(); };
      }, []);

      var src = base
        ? base + "/workflow-editor/?theme=" + theme
          + "&dshBase=" + encodeURIComponent(window.location.origin)
          + "&project=" + encodeURIComponent(projectDir)
          + "#/project"
        : "";

      return jsxRuntime.jsx("div", {
        style: { position: "relative", width: "100%", height: "100%", display: "flex", flexDirection: "column" },
        children: jsxRuntime.jsx("iframe", {
          src: src,
          title: "RPA workflow editor",
          style: { flex: 1, width: "100%", border: "none", background: "var(--dsw-alias-bg-base, #ffffff)" }
        })
      });
    }

    function apply(ctx) {
      var t = ctx.locale.bind(NS);
      ctx.effect(function () {
        ctx.locale.register(NS, { zh: zh, en: en });
      }, "rpa-console: dictionaries");

      // 会话头部右上角工具区（与关闭/操作按钮同区域）；kind: list 可多 entry 共存
      ctx.slots.inject("conversation.session.header.utilities", function () {
        return ctx.slots.register({
          name: "conversation.session.header.utilities",
          id: "rpa-console",
          locale: NS,
          inject: function () { return {}; }
        }, RpaPanel);
      });

      /* -------- RPA 流程编辑 tab（conversation.view，仅 RPA 工作区会话动态注册） --------
       * tab 栏（ui-conversation）把 conversation.view 的所有 entry 全列出、无过滤，
       * 因此"普通工作区不出现流程 tab"靠动态注册实现：监听当前会话，
       * 目录含 rpa.json（经 node 侧 /rpa-bridge/project-check 探测）才注册 entry，
       * 否则注销。切换会话时自动增删，tab 栏经 useSyncExternalStore 即时刷新。
       */
      var flowTabDisposer = null;
      var flowTabCwd = null;

      function registerFlowTab(cwd) {
        if (flowTabDisposer) return;
        flowTabCwd = cwd;
        flowTabDisposer = ctx.slots.inject("conversation.view", function () {
          return ctx.slots.register({
            name: "conversation.view",
            id: "rpa-flow",
            order: 20,
            locale: NS,
            label: function () { return t("flowTab.label"); },
            inject: function (sessionId) {
              return { projectDir: flowTabCwd };
            }
          }, FlowView);
        });
      }
      function unregisterFlowTab() {
        if (flowTabDisposer) {
          flowTabDisposer();
          flowTabDisposer = null;
          flowTabCwd = null;
        }
      }
      /** 异步探测目录是否为 RPA 流程工作区（node 侧同源 HTTP）。 */
      function probeProject(cwd, onResult) {
        fetch("/rpa-bridge/project-check?path=" + encodeURIComponent(cwd), {
          signal: AbortSignal.timeout(4000)
        })
          .then(function (r) { return r.json().catch(function () { return {}; }); })
          .then(function (d) { onResult(Boolean(d && d.ok && d.isRpa)); })
          .catch(function () { onResult(false); });
      }
      /** 会话切换时同步流程 tab（幂等：重复探测同一会话跳过）。 */
      var lastProbedCwd = null;
      var lastProbedResult = null;
      function syncFlowTab() {
        var snap;
        try { snap = ctx.sessions.list.getSnapshot(); } catch (e) { return; }
        var current = snap && snap.current;
        var summary = current === undefined || current === null ? undefined : (snap.byId || {})[current];
        var cwd = summary && summary.cwd;
        if (!cwd) {
          lastProbedCwd = null;
          lastProbedResult = null;
          unregisterFlowTab();
          return;
        }
        // 定时重探：目录可能在会话存活期间被 rpa_project_create 初始化（无需刷新）
        if (cwd === lastProbedCwd) return;
        lastProbedCwd = cwd;
        probeProject(cwd, function (isRpa) {
          if (cwd !== lastProbedCwd) return; // 探测期间会话又切换了
          lastProbedResult = isRpa;
          if (isRpa) registerFlowTab(cwd);
          else unregisterFlowTab();
        });
      }
      ctx.effect(function () {
        var unsub = null;
        try { unsub = ctx.sessions.list.subscribe(syncFlowTab); } catch (e) {}
        syncFlowTab();
        // 每 4s 重探当前会话目录（rpa_project_create / 删除 rpa.json 后自动增删 tab）
        var timer = setInterval(syncFlowTab, 4000);
        return function () {
          if (unsub) unsub();
          clearInterval(timer);
          unregisterFlowTab();
        };
      }, "rpa-console: flow tab sync");
    }

    exports.apply = apply;
    exports.inject = ["slots", "locale", "sessions"];
    return module.exports;
  }
});
