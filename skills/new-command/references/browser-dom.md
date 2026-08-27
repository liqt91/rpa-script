# 浏览器页面指令（DOM handler）

> 实现文件 `extension/dom_handlers_new/<cmd>.js`，Python 桩只做注册（勿手改）。
> 先读 `fact-card-browser.md` 的环境事实（重载/CSP/生效差异/编译），再读本文件的建设规则。

## JS handler 签名

```js
registerHandler('myCmd', async ({ locator, selectorFamily, extra }) => {
  const el = findTarget(locator, selectorFamily, extra);   // 有 element 参数时才用
  // extra 里有你 JSON 定义的参数名
  return { value: "结果文本", count: 3, items: [...] };     // 返回 dict
});
```

## 结果写回变量（extension_runner.py:407/1652 规则）

runner 读 `resultVar`/`saveToVar`/`varName` 作为目标变量名，从返回 dict 取主值写入：

- 返回 dict 里**优先** `extracted` → `navigatedTo` → `value` → 否则整 dict。
- 写回 `vars[<resultVar名>]`（例如 `extra.resultVar="links"` → 写 `vars.links`）。

所以要"返回一个列表/结果给变量"，**返回 dict 里放 `value`（或 extracted）**，JSON 定义个 `resultVar`(str-var) 参数即可。

> 示例：`getLinksByRegex` 返回 `{ value: links数组, count: links.length }`，定义 `resultVar` 参数 → runner 把 `links` 数组写入 `vars[resultVar]`。

## extension 链路关键机制（不用读源码，这些就是规则）

- **type 匹配**：指令的 `type` = cmd 名，`content.js` 里 `registerHandler('<cmd>', fn)` 与其匹配。JS handler 在 `extension/dom_handlers_new/<cmd>.js`，构建时拼进 `content.js`。
- **locator 注入**：指令若有 **element 类参数**（用户选了元素），runner 把定位器放进 `args.locator` + `args.selectorFamily`；无元素时这俩为空。参数其余值进 `args.extra`。
- **免定位器规则（自动，不需改代码）**：指令**没有必填的 element 参数**时，允许空 locator（= 全页面统计 / 页面级操作）。判断由 `extension_runner._cmd_requires_locator` 自动完成——只要 JSON 里 element 参数不是 `required:true`，就能全页面跑，**无需登记白名单**。
- **可用 helper**（content_base.js 提供）：`findTarget`、`checkVisibility(el, mode)`、`getVisibilityMode`、`resolveLocator`、`resolveAllLocators`、`sleep`、`randNormal`、`coordsResult` 等。

## 验证优先级

1. **逻辑验证用 Node 桩（默认方式，别起 HTTP 服务/导入工作流）**：`rpa_new_command(cmd, verify={...})` 对 extension 指令自动跑 `scripts/verify_web_handler.mjs`，**无需重载扩展**即可验证 JS 逻辑（加 `--extra-file`/`--links` 注入参数与示例 DOM）。
2. **真机 E2E（最终确认，可选）**：通过 `rpa_new_command` 已自动重载扩展、无需手动；在「已开着且不重新导航的页面」上直接测时，才需手动刷新那一个页面。
