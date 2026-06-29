import re
from src.runtime.workflow.commands import COMMAND_REGISTRY

with open('extension/content.js', 'r', encoding='utf-8') as f:
    js = f.read()

handler_blocks = {}
for m in re.finditer(r'^\s*([A-Za-z_]\w*)\s*\(([^)]*)\)\s*\{', js, re.MULTILINE):
    name = m.group(1)
    if name in ('if', 'while', 'for', 'switch', 'catch', 'with'):
        continue
    start = m.end() - 1
    depth = 0
    i = start
    while i < len(js):
        c = js[i]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                i += 1
                break
        i += 1
    body = js[start:i].strip()
    handler_blocks[name] = body

ANNOTATIONS = [
    (r"(const el = resolveLocator\(locator, locatorType, extra\?\.visibleOnly\);)", r"\1  // 根据定位器查找目标元素"),
    (r"(if \(!el\) throw new Error\(`([^`]+)`\);)", r"\1  // 未找到元素时抛出错误"),
    (r"(el\.value = '';)", r"\1  // 清空输入框的当前值"),
    (r"(el\.dispatchEvent\(new Event\('input', \{ bubbles: true \}\)\);)", r"\1  // 触发 input 事件，通知前端框架值已变化"),
    (r"(el\.dispatchEvent\(new Event\('change', \{ bubbles: true \}\)\);)", r"\1  // 触发 change 事件，通知表单校验/框架状态更新"),
    (r"(el\.value = text;)", r"\1  // 设置输入框为目标文本"),
    (r"(if \(extra\?\.pressEnter\) \{)", r"\1  // 如果指令标记了输入后按回车"),
    (r"(el\.dispatchEvent\(new KeyboardEvent\('keydown', \{ key: 'Enter', bubbles: true \}\)\);)",
     r"\1  // 模拟按下 Enter 键"),
    (r"(el\.dispatchEvent\(new KeyboardEvent\('keyup', \{ key: 'Enter', bubbles: true \}\)\);)",
     r"\1  // 模拟松开 Enter 键"),
    (r"(const attr = extra\?\.attribute;)", r"\1  // 读取要提取的属性名（null=文本）"),
    (r"(if \(attr === 'innerHTML'\) \{)", r"\1  // 提取 innerHTML"),
    (r"(} else if \(attr === 'value'\) \{)", r"\1  // 提取 value 属性"),
    (r"(} else if \(attr\) \{)", r"\1  // 提取指定属性"),
    (r"(value = el\.textContent\?\.trim\(\) \?\? '';)", r"\1  // 默认提取可见文本内容"),
    (r"(return \{ extracted: value \};)", r"\1  // 返回提取结果"),
    (r"(const url = extra\?\.url;)", r"\1  // 读取目标网址"),
    (r"(if \(!url\) throw new Error\('([^']+)'\);)", r"\1  // 缺少必需参数时报错"),
    (r"(window\.location\.href = url;)", r"\1  // 当前标签页跳转到目标网址"),
    (r"(return \{ navigatedTo: url \};)", r"\1  // 返回跳转结果"),
    (r"(if \(el\.click\) \{)", r"\1  // 优先使用原生 click 方法"),
    (r"(el\.click\(\);)", r"\1  // 触发原生点击"),
    (r"(const evt = new MouseEvent\('click', "
     r"\{ bubbles: true, cancelable: true, view: window \}\);)",
     r"\1  // 构造点击事件"),
    (r"(el\.dispatchEvent\(evt\);)", r"\1  // 通过事件派发模拟点击"),
    (r"(return \{ clicked: true, tagName: el\.tagName \};)", r"\1  // 返回点击成功及元素标签名"),
    (r"(const text = extra\?\.text \?\? '';)", r"\1  // 读取要输入的文本"),
    (r"(const clearFirst = extra\?\.clearFirst !== false;)", r"\1  // 默认先清空输入框"),
    (r"(if \(clearFirst\) \{)", r"\1  // 需要时先清空现有内容"),
    (r"(return \{ input: true, length: text\.length \};)", r"\1  // 返回输入成功及文本长度"),
    (r"(const ms = \(extra\?\.seconds \|\| 1\) \* 1000;)", r"\1  // 将秒数转换为毫秒"),
    (r"(return new Promise\((resolve) => \{)", r"\1  // 返回 Promise，支持异步等待"),
    (r"(setTimeout\(\(\) => resolve\(\{ waited: ms \}\), ms\);)", r"\1  // 延迟指定时间后 resolve"),
    (r"(const direction = extra\?\.direction \|\| 'down';)", r"\1  // 读取滚动方向，默认向下"),
    (r"(const amount = extra\?\.amount \|\| 500;)", r"\1  // 读取滚动距离，默认 500px"),
    (r"(if \(direction === 'down'\) \{)", r"\1  // 向下滚动"),
    (r"(window\.scrollBy\(0, amount\);)", r"\1  // 相对当前位置向下滚动"),
    (r"(} else if \(direction === 'up'\) \{)", r"\1  // 向上滚动"),
    (r"(window\.scrollBy\(0, -amount\);)", r"\1  // 相对当前位置向上滚动"),
    (r"(} else if \(direction === 'bottom'\) \{)", r"\1  // 滚动到底部"),
    (r"(window\.scrollTo\(0, document\.body\.scrollHeight\);)", r"\1  // 直接跳转到页面最底部"),
    (r"(} else if \(direction === 'top'\) \{)", r"\1  // 滚动到顶部"),
    (r"(window\.scrollTo\(0, 0\);)", r"\1  // 直接跳转到页面最顶部"),
    (r"(return \{ scrolled: direction, amount \};)", r"\1  // 返回滚动方向和距离"),
    (r"(window\.history\.back\(\);)", r"\1  // 浏览器历史回退"),
    (r"(return \{ wentBack: true \};)", r"\1  // 返回操作结果"),
    (r"(window\.history\.forward\(\);)", r"\1  // 浏览器历史前进"),
    (r"(return \{ wentForward: true \};)", r"\1  // 返回操作结果"),
    (r"(window\.location\.reload\(\);)", r"\1  // 重新加载当前页面"),
    (r"(return \{ refreshed: true \};)", r"\1  // 返回刷新结果"),
    (r"(const key = extra\?\.key \|\| 'Enter';)", r"\1  // 读取按键，默认 Enter"),
    (r"(document\.dispatchEvent\(new KeyboardEvent\('keydown', \{ key, bubbles: true \}\)\);)", r"\1  // 模拟按键按下"),
    (r"(document\.dispatchEvent\(new KeyboardEvent\('keyup', \{ key, bubbles: true \}\)\);)", r"\1  // 模拟按键松开"),
    (r"(return \{ pressed: key \};)", r"\1  // 返回按下的键名"),
    (r"(el\.dispatchEvent\(new MouseEvent\('mouseover', "
     r"\{ bubbles: true, cancelable: true, view: window \}\)\);)",
     r"\1  // 模拟鼠标移入"),
    (r"(el\.dispatchEvent\(new MouseEvent\('mouseenter', "
     r"\{ bubbles: true, cancelable: true, view: window \}\)\);)",
     r"\1  // 模拟鼠标进入"),
    (r"(return \{ hovered: true, tagName: el\.tagName \};)", r"\1  // 返回悬停成功及元素标签名"),
    (r"(return \{ cleared: true \};)", r"\1  // 返回清空成功"),
    (r"(const value = extra\?\.value;)", r"\1  // 读取要选中的选项值"),
    (r"(let option = el\.querySelector\(`option\[value=", r"\1  // 先按 value 属性匹配选项"),
    (r"(if \(!option\) \{)", r"\1  // 按 value 找不到时 fallback"),
    (r"(option = Array\.from\(el\.options\)\.find\(o => o\.textContent\.trim\(\) === value\);)", r"\1  // 按选项文本内容匹配"),
    (r"(if \(option\) \{)", r"\1  // 找到匹配选项"),
    (r"(el\.value = option\.value;)", r"\1  // 设置 select 的选中值"),
    (r"(el\.dispatchEvent\(new Event\('change', \{ bubbles: true \}\)\);)", r"\1  // 触发 change 事件通知框架"),
    (r"(return \{ selected: option\.value, text: option\.textContent \};)", r"\1  // 返回选中的值和文本"),
    (r"(throw new Error\(`selectOption: option ", r"\1  // 选项不存在时报错"),
    (r"(window\.open\(url, '_blank'\);)", r"\1  // 在新标签页打开网址"),
    (r"(return \{ opened: url \};)", r"\1  // 返回打开结果"),
    (r"(const script = extra\?\.script;)", r"\1  // 读取要执行的 JS 代码"),
    (r"(const result = eval\(script\);)", r"\1  // 在当前页面上下文执行 JS"),
    (r"(return \{ executed: true, result: String\(result\) \};)", r"\1  // 返回执行结果"),
]

def annotate(code: str) -> str:
    lines = code.split('\n')
    result = []
    for line in lines:
        annotated = line
        for pat, repl in ANNOTATIONS:
            annotated = re.sub(pat, repl, annotated)
        result.append(annotated)
    return '\n'.join(result)

with open('commands_full.md', 'w', encoding='utf-8') as out:
    out.write('# 扩展模式指令完整参考\n\n')
    for cmd_type, meta in sorted(COMMAND_REGISTRY.items()):
        ext = meta.get('runtimes', {}).get('extension')
        if not ext:
            continue
        handler = ext.get('handler', '')
        local = '本地(backend)' if ext.get('local') else '远程(extension)'
        label = meta.get('label', '')
        category = meta.get('category', '')
        fields = meta.get('fields', [])

        out.write(f'## {cmd_type}\n\n')
        out.write(f'- **Handler**: `{handler}`\n')
        out.write(f'- **执行方式**: {local}\n')
        out.write(f'- **分类**: {category} - {label}\n')
        if fields:
            params = ', '.join([f"`{f['name']}`({f.get('label','')})" for f in fields])
        else:
            params = '无'
        out.write(f'- **参数**: {params}\n')
        body = handler_blocks.get(handler, 'N/A')
        annotated = annotate(body)
        out.write('- **content.js 行为**:\n')
        out.write('  ```javascript\n')
        for line in annotated.split('\n'):
            out.write(f'  {line}\n')
        out.write('  ```\n')
        out.write('\n')

print('written commands_full.md')
