# 扩展模式指令完整参考

## navigate（打开网页）

- **Handler**: `navigate`
- **执行方式**: 远程(extension)
- **分类**: 页面导航 - 打开网页
- **参数**: `url`(网址), `waitLoad`(等待加载完成), `timeout`(超时秒数), `saveToVar`(保存网页对象到)
- **Emitter 转换**: 无
- **content.js 行为**:

```javascript
navigate({ extra }) {
  const url = extra?.url;                       // 读取目标网址
  if (!url) throw new Error('navigate: url required');  // 缺少必需参数时报错
  window.location.href = url;                   // 当前标签页跳转到目标网址
  return { navigatedTo: url };                  // 返回跳转结果
}
```

---

## goBack（返回上一页）

- **Handler**: `goBack`
- **执行方式**: 远程(extension)
- **分类**: 页面导航 - 返回上一页
- **参数**: 无
- **Emitter 转换**: 无
- **content.js 行为**:

```javascript
goBack() {
  window.history.back();                        // 浏览器历史回退
  return { wentBack: true };                    // 返回操作结果
}
```

---

## goForward（前进）

- **Handler**: `goForward`
- **执行方式**: 远程(extension)
- **分类**: 页面导航 - 前进
- **参数**: 无
- **Emitter 转换**: 无
- **content.js 行为**:

```javascript
goForward() {
  window.history.forward();                     // 浏览器历史前进
  return { wentForward: true };                 // 返回操作结果
}
```

---

## refresh（刷新页面）

- **Handler**: `refresh`
- **执行方式**: 远程(extension)
- **分类**: 页面导航 - 刷新页面
- **参数**: `hardReload`(强制刷新忽略缓存)
- **Emitter 转换**: 无（content.js 未实现 `hardReload`，始终普通刷新）
- **content.js 行为**:

```javascript
refresh() {
  window.location.reload();                     // 重新加载当前页面
  return { refreshed: true };                   // 返回刷新结果
}
```

---

## newTab（新建标签页）

- **Handler**: `newTab`
- **执行方式**: 远程(extension)
- **分类**: 页面导航 - 新建标签页
- **参数**: `url`(网址，可选)
- **Emitter 转换**: 无
- **content.js 行为**:

```javascript
newTab({ extra }) {
  const url = extra?.url;                       // 读取目标网址
  if (!url) throw new Error('newTab: url required');  // 缺少必需参数时报错
  window.open(url, '_blank');                   // 在新标签页打开网址
  return { opened: url };                       // 返回打开结果
}
```

---

## click（点击元素）

- **Handler**: `click`
- **执行方式**: 远程(extension)
- **分类**: 元素点击 - 点击元素
- **参数**: `locator`(元素定位器), `locator_type`(定位方式), `method`(查找方法), `forceJs`(强制JS点击)
- **Emitter 转换**: 无
- **content.js 行为**:

```javascript
click({ locator, locatorType, extra }) {
  const el = resolveLocator(locator, locatorType, extra?.visibleOnly);  // 根据定位器查找目标元素
  if (!el) throw new Error(`click: element not found: ${locator}`);     // 未找到元素时抛出错误

  if (el.click) {                               // 优先使用原生 click 方法
    el.click();                                 // 触发原生点击
  } else {
    const evt = new MouseEvent('click', { bubbles: true, cancelable: true, view: window });  // 构造点击事件
    el.dispatchEvent(evt);                      // 通过事件派发模拟点击
  }
  return { clicked: true, tagName: el.tagName };  // 返回点击成功及元素标签名
}
```

---

## input（输入文本）

- **Handler**: `input`
- **执行方式**: 远程(extension)
- **分类**: 文本输入 - 输入文本
- **参数**: `locator`(元素定位器), `locator_type`(定位方式), `text`(输入内容), `clearFirst`(先清空)
- **Emitter 转换**: 无
- **content.js 行为**:

```javascript
input({ locator, locatorType, extra }) {
  const el = resolveLocator(locator, locatorType, extra?.visibleOnly);  // 根据定位器查找目标元素
  if (!el) throw new Error(`input: element not found: ${locator}`);     // 未找到元素时抛出错误

  const text = extra?.text ?? '';               // 读取要输入的文本
  const clearFirst = extra?.clearFirst !== false;  // 默认先清空输入框

  if (clearFirst) {                             // 需要时先清空现有内容
    el.value = '';                              // 清空输入框的当前值
    el.dispatchEvent(new Event('input', { bubbles: true }));   // 触发 input 事件，通知前端框架值已变化
    el.dispatchEvent(new Event('change', { bubbles: true }));  // 触发 change 事件，通知表单校验/框架状态更新
  }

  el.value = text;                              // 设置输入框为目标文本
  el.dispatchEvent(new Event('input', { bubbles: true }));     // 触发 input 事件
  el.dispatchEvent(new Event('change', { bubbles: true }));    // 触发 change 事件

  // 如果指令标记了输入后按回车（inputAndPressEnter 会设置 pressEnter: true）
  if (extra?.pressEnter) {
    el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));  // 模拟按下 Enter 键
    el.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', bubbles: true }));    // 模拟松开 Enter 键
  }

  return { input: true, length: text.length };  // 返回输入成功及文本长度
}
```

---

## inputAndPressEnter（输入并回车）

- **Handler**: `input`（与 input 共用 handler）
- **执行方式**: 远程(extension)
- **分类**: 文本输入 - 输入并回车
- **参数**: `locator`(元素定位器), `locator_type`(定位方式), `text`(输入内容), `clearFirst`(先清空)
- **Emitter 转换**: 自动在 extra 中增加 `"pressEnter": true`
- **content.js 行为**: 同 `input`，当 `extra.pressEnter` 为 `true` 时额外派发 Enter 键盘事件。

---

## clearInput（清空输入框）

- **Handler**: `clearInput`
- **执行方式**: 远程(extension)
- **分类**: 文本输入 - 清空输入框
- **参数**: `locator`(元素定位器), `locator_type`(定位方式)
- **Emitter 转换**: 无
- **content.js 行为**:

```javascript
clearInput({ locator, locatorType, extra }) {
  const el = resolveLocator(locator, locatorType, extra?.visibleOnly);  // 根据定位器查找目标元素
  if (!el) throw new Error(`clearInput: element not found: ${locator}`); // 未找到元素时抛出错误
  el.value = '';                                // 清空输入框的当前值
  el.dispatchEvent(new Event('input', { bubbles: true }));   // 触发 input 事件
  el.dispatchEvent(new Event('change', { bubbles: true }));  // 触发 change 事件
  return { cleared: true };                     // 返回清空成功
}
```

---

## pressKey（按键）

- **Handler**: `pressKey`
- **执行方式**: 远程(extension)
- **分类**: 文本输入 - 按键
- **参数**: `key`(按键，默认 Enter)
- **Emitter 转换**: 无
- **content.js 行为**:

```javascript
pressKey({ extra }) {
  const key = extra?.key || 'Enter';            // 读取按键，默认 Enter
  document.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));  // 模拟按键按下
  document.dispatchEvent(new KeyboardEvent('keyup', { key, bubbles: true }));    // 模拟按键松开
  return { pressed: key };                      // 返回按下的键名
}
```

---

## selectOption（下拉框选择）

- **Handler**: `selectOption`
- **执行方式**: 远程(extension)
- **分类**: 文本输入 - 下拉框选择
- **参数**: `locator`(元素定位器), `locator_type`(定位方式), `by`(选择方式), `value`(值)
- **Emitter 转换**: 无（`by` 字段未在 content.js 中使用，始终先按 value 再按 text 匹配）
- **content.js 行为**:

```javascript
selectOption({ locator, locatorType, extra }) {
  const el = resolveLocator(locator, locatorType, extra?.visibleOnly);  // 根据定位器查找目标元素
  if (!el) throw new Error(`selectOption: element not found: ${locator}`);  // 未找到元素时抛出错误
  const value = extra?.value;                   // 读取要选中的选项值
  if (!value) throw new Error('selectOption: value required');  // 缺少值时报错

  // 先按 value 属性匹配选项
  let option = el.querySelector(`option[value="${CSS.escape(value)}"]`);
  if (!option) {                                // 按 value 找不到时 fallback
    option = Array.from(el.options).find(o => o.textContent.trim() === value);  // 按选项文本内容匹配
  }
  if (option) {                                 // 找到匹配选项
    el.value = option.value;                    // 设置 select 的选中值
    el.dispatchEvent(new Event('change', { bubbles: true }));  // 触发 change 事件通知框架
    return { selected: option.value, text: option.textContent };  // 返回选中的值和文本
  }
  throw new Error(`selectOption: option "${value}" not found`);  // 选项不存在时报错
}
```

---

## getText（获取元素文本）

- **Handler**: `extract`（与 getAttr/getHtml/getValue 共用 handler）
- **执行方式**: 远程(extension)
- **分类**: 数据提取 - 获取元素文本
- **参数**: `locator`(元素定位器), `locator_type`(定位方式), `method`(查找方法), `varName`(保存到变量)
- **Emitter 转换**: 自动在 extra 中增加 `"attribute": null`
- **content.js 行为**: 当 `extra.attribute` 为 `null` 时，提取元素的 `textContent.trim()`。

---

## getAttr（获取元素属性）

- **Handler**: `extract`（共用 handler）
- **执行方式**: 远程(extension)
- **分类**: 数据提取 - 获取元素属性
- **参数**: `locator`(元素定位器), `locator_type`(定位方式), `method`(查找方法), `attrName`(属性名), `varName`(保存到变量)
- **Emitter 转换**: 自动将 `attrName` 映射为 `extra.attribute`
- **content.js 行为**: 当 `extra.attribute` 为普通字符串时，调用 `el.getAttribute(attr)`。

---

## getHtml（获取元素HTML）

- **Handler**: `extract`（共用 handler）
- **执行方式**: 远程(extension)
- **分类**: 数据提取 - 获取元素HTML
- **参数**: `locator`(元素定位器), `locator_type`(定位方式), `method`(查找方法), `mode`(模式 inner/outer), `varName`(保存到变量)
- **Emitter 转换**: 自动在 extra 中增加 `"attribute": "innerHTML"`
- **content.js 行为**: 当 `extra.attribute === 'innerHTML'` 时，读取 `el.innerHTML`。

---

## getValue（获取输入框值）

- **Handler**: `extract`（共用 handler）
- **执行方式**: 远程(extension)
- **分类**: 数据提取 - 获取输入框值
- **参数**: `locator`(元素定位器), `locator_type`(定位方式), `varName`(保存到变量)
- **Emitter 转换**: 自动在 extra 中增加 `"attribute": "value"`
- **content.js 行为**: 当 `extra.attribute === 'value'` 时，读取 `el.value`。

---

### extract 统一 handler 源码

```javascript
extract({ locator, locatorType, extra }) {
  const el = resolveLocator(locator, locatorType, extra?.visibleOnly);  // 根据定位器查找目标元素
  if (!el) throw new Error(`extract: element not found: ${locator}`);   // 未找到元素时抛出错误

  const attr = extra?.attribute;                // 读取要提取的属性名（null=文本）
  let value;
  if (attr === 'innerHTML') {                   // 提取 innerHTML
    value = el.innerHTML;
  } else if (attr === 'value') {                // 提取 value 属性
    value = el.value;
  } else if (attr) {                            // 提取指定属性
    value = el.getAttribute(attr);
  } else {
    value = el.textContent?.trim() ?? '';       // 默认提取可见文本内容
  }
  return { extracted: value };                  // 返回提取结果
}
```

---

## scrollToBottom（滚动到底部）

- **Handler**: `scroll`（共用 handler）
- **执行方式**: 远程(extension)
- **分类**: 滚动 - 滚动到底部
- **参数**: `smooth`(平滑滚动)
- **Emitter 转换**: 自动在 extra 中增加 `"direction": "bottom"`
- **content.js 行为**: `direction === 'bottom'` 时执行 `window.scrollTo(0, document.body.scrollHeight)`。

---

## scrollToTop（滚动到顶部）

- **Handler**: `scroll`（共用 handler）
- **执行方式**: 远程(extension)
- **分类**: 滚动 - 滚动到顶部
- **参数**: `smooth`(平滑滚动)
- **Emitter 转换**: 自动在 extra 中增加 `"direction": "top"`
- **content.js 行为**: `direction === 'top'` 时执行 `window.scrollTo(0, 0)`。

---

## scrollBy（滚动指定距离）

- **Handler**: `scroll`（共用 handler）
- **执行方式**: 远程(extension)
- **分类**: 滚动 - 滚动指定距离
- **参数**: `x`(水平距离), `y`(垂直距离)
- **Emitter 转换**: 自动将 `y` 映射为 `direction`（up/down）和 `amount`（绝对值）
- **content.js 行为**: `direction === 'down'` 时 `window.scrollBy(0, amount)`，`up` 时 `window.scrollBy(0, -amount)`。

---

### scroll 统一 handler 源码

```javascript
scroll({ extra }) {
  const direction = extra?.direction || 'down'; // 读取滚动方向，默认向下
  const amount = extra?.amount || 500;          // 读取滚动距离，默认 500px
  if (direction === 'down') {                   // 向下滚动
    window.scrollBy(0, amount);                 // 相对当前位置向下滚动
  } else if (direction === 'up') {              // 向上滚动
    window.scrollBy(0, -amount);                // 相对当前位置向上滚动
  } else if (direction === 'bottom') {          // 滚动到底部
    window.scrollTo(0, document.body.scrollHeight);  // 直接跳转到页面最底部
  } else if (direction === 'top') {             // 滚动到顶部
    window.scrollTo(0, 0);                      // 直接跳转到页面最顶部
  }
  return { scrolled: direction, amount };       // 返回滚动方向和距离
}
```

---

## sleep（等待固定时间）

- **Handler**: `wait`（共用 handler）
- **执行方式**: 远程(extension)
- **分类**: 等待 - 等待固定时间
- **参数**: `seconds`(等待秒数，默认 1)
- **Emitter 转换**: 无
- **content.js 行为**:

```javascript
wait({ extra }) {
  const ms = (extra?.seconds || 1) * 1000;      // 将秒数转换为毫秒
  return new Promise((resolve) => {              // 返回 Promise，支持异步等待
    setTimeout(() => resolve({ waited: ms }), ms);  // 延迟指定时间后 resolve
  });
}
```

---

## waitForElement（等待元素出现）

- **Handler**: `wait`（与 sleep 共用 handler）
- **执行方式**: 远程(extension)
- **分类**: 等待 - 等待元素出现
- **参数**: `locator`(元素定位器), `locator_type`(定位方式), `timeout`(超时秒数)
- **Emitter 转换**: 无（**当前 content.js 的 `wait` handler 只支持 `seconds` 参数，不支持元素轮询等待**；后端若需等待元素，应自行实现轮询逻辑）
- **content.js 行为**: 同 `sleep`，仅做固定延时。

---

## hover（悬停）

- **Handler**: `hover`
- **执行方式**: 远程(extension)
- **分类**: 元素点击 - 悬停
- **参数**: `locator`(元素定位器), `locator_type`(定位方式), `method`(查找方法)
- **Emitter 转换**: 无
- **content.js 行为**:

```javascript
hover({ locator, locatorType, extra }) {
  const el = resolveLocator(locator, locatorType, extra?.visibleOnly);  // 根据定位器查找目标元素
  if (!el) throw new Error(`hover: element not found: ${locator}`);     // 未找到元素时抛出错误
  el.dispatchEvent(new MouseEvent('mouseover', { bubbles: true, cancelable: true, view: window }));  // 模拟鼠标移入
  el.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true, cancelable: true, view: window })); // 模拟鼠标进入
  return { hovered: true, tagName: el.tagName };  // 返回悬停成功及元素标签名
}
```

---

## executeJs（执行JS）

- **Handler**: `executeJs`
- **执行方式**: 远程(extension)
- **分类**: 自定义 - 执行JS
- **参数**: `script`(JavaScript代码), `resultVar`(返回值变量)
- **Emitter 转换**: 无
- **content.js 行为**:

```javascript
executeJs({ extra }) {
  const script = extra?.script;                 // 读取要执行的 JS 代码
  if (!script) throw new Error('executeJs: script required');  // 缺少代码时报错
  // eslint-disable-next-line no-eval
  const result = eval(script);                  // 在当前页面上下文执行 JS
  return { executed: true, result: String(result) };  // 返回执行结果
}
```

---

## setVar（设置变量）

- **Handler**: `setVar`
- **执行方式**: 本地(backend)
- **分类**: 变量与数据 - 设置变量
- **参数**: `name`(变量名), `value`(值), `valueType`(值类型)
- **Emitter 转换**: 无
- **content.js 行为**: 无 — 该指令在 Python 后端直接执行，不发送到浏览器扩展。

---

## log（记录日志）

- **Handler**: `log`
- **执行方式**: 本地(backend)
- **分类**: 输出与日志 - 记录日志
- **参数**: `message`(日志内容), `level`(级别)
- **Emitter 转换**: 无
- **content.js 行为**: 无 — 该指令在 Python 后端直接执行，不发送到浏览器扩展。

---

# 附录：resolveLocator（元素定位核心函数）

所有需要操作 DOM 的 handler 都通过 `resolveLocator(locator, locatorType, visibleOnly)` 查找目标元素。

```javascript
function resolveLocator(locator, locatorType, visibleOnly) {
  if (!locator) return document;                // 无定位器时返回 document（极少使用）

  // Normalize css:/xpath: prefixes
  if (locator.startsWith('css:')) {
    locator = locator.slice(4);
    locatorType = 'css';
  }
  if (locator.startsWith('xpath:')) {
    locator = locator.slice(6);
    locatorType = 'xpath';
  }
  const inferred = inferLocatorType(locator);
  if (inferred && inferred !== locatorType) locatorType = inferred;

  let el = null;
  switch (locatorType) {
    case 'xpath':
      el = document.evaluate(locator, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
      break;
    case 'id':
      el = locator.startsWith('#') ? document.querySelector(locator) : document.getElementById(locator);
      break;
    case 'class':
      el = document.querySelector(locator.startsWith('.') ? locator : '.' + locator);
      break;
    case 'text': {
      const text = locator.startsWith('text=') ? locator.slice(5) : locator;
      el = document.evaluate(`//*[contains(text(), ${JSON.stringify(text)})]`, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
      break;
    }
    case 'tag_text': {
      const m = locator.match(/^tag:(\w+)@text\(\)=(.+)$/);
      if (m) {
        el = document.evaluate(`//${m[1]}[contains(text(), ${JSON.stringify(m[2])})]`, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
      }
      break;
    }
    case 'data-attr':
    case 'aria':
    case 'name': {
      let l = locator;
      if (l.startsWith('@')) l = l.slice(1);
      const eq = l.indexOf('=');
      if (eq > 0) {
        el = document.querySelector(`[${l.slice(0, eq)}=${JSON.stringify(l.slice(eq + 1))}]`);
      } else {
        el = document.querySelector(`[data-${l}]`);
      }
      break;
    }
    case 'tag_attr': {
      const m = locator.match(/^tag:(\w+)@(\w+)=(.+)$/);
      if (m) el = document.querySelector(`${m[1]}[${m[2]}=${JSON.stringify(m[3])}]`);
      break;
    }
    case 'tag_class': {
      const m = locator.match(/^tag:(\w+)@class=(.+)$/);
      if (m) el = document.querySelector(`${m[1]}.${m[2]}`);
      break;
    }
    case 'multi_attr': {
      const parts = locator.match(/@@class:([^@]+)/g);
      if (parts) {
        const cls = parts.map(p => '.' + p.replace('@@class:', '')).join('');
        el = document.querySelector(cls);
      }
      break;
    }
    case 'css':
    default:
      el = document.querySelector(locator);
  }

  if (!el) {
    try { el = document.querySelector(locator); } catch (e) {}
    try { el = document.evaluate(locator, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue; } catch (e) {}
  }

  if (!el || !visibleOnly) return el;
  if (!isVisible(el)) {
    const all = resolveAllLocators(locator, locatorType);
    const v = all.find(isVisible);
    if (v) return v;
  }
  return el;
}
```
