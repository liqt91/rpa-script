---
name: check-command
description: 检查指令（command）的定义一致性和完整性。用于新增指令后、修改 JSON 后、或怀疑配置不一致时排查问题。
---

# 指令一致性检查

## 检查时机

- 新增指令完成后
- 修改 `commands/<type>.json` 后
- `auto_register()` 报错或指令在 UI 不显示时
- 怀疑 JSON 与 handler 代码不一致时

## 检查流程

按顺序执行以下检查，发现一项修一项，修完重新跑，直到全部通过。

### 1. JSON 定义完整性

遍历 `commands/` 下所有 `.json` 文件，检查每条指令的必需字段：

```
□ cmd         — 非空，camelCase，与文件名一致（xxx.json → cmd: "xxx"）
□ label       — 非空，中文显示名
□ runtime     — 必须是 "extension" | "backend" | "control"
□ params      — 数组，可为空数组 []
□ handler.kind — 必须是 "extension" | "backend" | "control"
```

**检查方法：**

```bash
# 列出所有 JSON，逐条检查必需字段
python -c "
import json, os
for f in sorted(os.listdir('commands')):
    if f.endswith('.json'):
        with open(f'commands/{f}') as fp:
            d = json.load(fp)
        cmd = d.get('cmd', 'MISSING')
        label = d.get('label', 'MISSING')
        runtime = d.get('runtime', 'MISSING')
        kind = d.get('handler', {}).get('kind', 'MISSING')
        ok = '✓' if cmd and label and runtime in ('extension','backend','control') and kind in ('extension','backend','control') else '✗'
        print(f'{ok} {f:<30} cmd={cmd:<25} runtime={runtime:<12} kind={kind}')
"
```

### 2. JSON 字段值互相一致

```
□ runtime 与 handler.kind 匹配：
  - runtime="extension" → handler.kind 必须是 "extension"
  - runtime="backend"   → handler.kind 必须是 "backend"
  - runtime="control"   → handler.kind 必须是 "control"
□ handler.source 指向的目录与 handler.kind 一致：
  - kind="extension" → 指向 extension_commands/
  - kind="backend"   → 指向 backend_commands/ 或 desktop_commands/
  - kind="control"   → 指向 control_commands/
```

```bash
python -c "
import json, os
for f in sorted(os.listdir('commands')):
    if not f.endswith('.json'): continue
    with open(f'commands/{f}') as fp:
        d = json.load(fp)
    runtime = d.get('runtime','')
    kind = d.get('handler',{}).get('kind','')
    source = d.get('handler',{}).get('source','')
    issues = []
    if runtime != kind:
        issues.append(f'runtime={runtime} kind={kind} mismatch')
    if source:
        if kind=='extension' and 'extension_commands' not in source:
            issues.append(f'extension source should be in extension_commands/')
        if kind=='backend' and 'backend_commands' not in source and 'desktop_commands' not in source:
            issues.append(f'backend source should be in backend_commands/ or desktop_commands/')
        if kind=='control' and 'control_commands' not in source:
            issues.append(f'control source should be in control_commands/')
    status = '✗' if issues else '✓'
    print(f'{status} {d[\"cmd\"]}', end='')
    if issues:
        print(f'  ← {\" | \".join(issues)}')
    else:
        print()
"
```

### 3. Python handler 文件存在且可注册

```
□ handler.source 指向的 .py 文件存在
□ 文件包含 @register_handler(...) 装饰器
□ 装饰器中 cmd/label/category/runtime 与 JSON 一致
□ params 列表与 JSON 的 params[].name 一一对应
□ backend/desktop/control 指令必须有 async def execute()
```

**逐个对比 JSON ↔ Python：**

对每条指令，读取 JSON 和对应的 Python 文件，逐项对比：

```bash
python -c "
import json, os, re, ast

def get_expected_dir(kind, source):
    '''推断 handler 文件应存在的目录'''
    if source and os.path.exists(source):
        return source
    if kind == 'extension':
        return f'src/runtime/commands/extension_commands/{{cmd}}.py'
    if kind == 'backend':
        # 检查是否在 desktop_commands
        return f'src/runtime/commands/backend_commands/{{cmd}}.py'
    if kind == 'control':
        return f'src/runtime/commands/control_commands/{{cmd}}.py'
    return None

for f in sorted(os.listdir('commands')):
    if not f.endswith('.json'): continue
    with open(f'commands/{f}') as fp:
        d = json.load(fp)
    cmd = d['cmd']
    kind = d['handler']['kind']
    source = d['handler'].get('source', '')
    
    # 推断 Python 文件路径
    if source:
        py_path = source
    else:
        py_path = f'src/runtime/commands/{kind}_commands/{cmd}.py'
    
    if not os.path.exists(py_path):
        # 可能是 desktop_commands
        alt = py_path.replace('backend_commands', 'desktop_commands')
        if os.path.exists(alt):
            py_path = alt
    
    if not os.path.exists(py_path):
        print(f'✗ {cmd}: Python file not found at {py_path}')
        continue
    
    with open(py_path, encoding='utf-8') as fp:
        py_code = fp.read()
    
    issues = []
    
    # 检查 @register_handler 存在
    if '@register_handler' not in py_code:
        issues.append('missing @register_handler')
    
    # 检查 cmd
    if f'cmd=\"{cmd}\"' not in py_code:
        issues.append(f'cmd mismatch in @register_handler')
    
    # 检查 runtime
    expected_runtime = d['runtime']
    if f'runtime=\"{expected_runtime}\"' not in py_code:
        issues.append(f'runtime mismatch, expected \"{expected_runtime}\"')
    
    # 检查 params 名称
    json_params = {p['name'] for p in d.get('params', [])}
    # 粗略提取 Param(\"xxx\" 中的参数名
    py_params = set(re.findall(r'Param\(\s*\"(\w+)\"', py_code))
    missing = json_params - py_params
    extra = py_params - json_params
    if missing:
        issues.append(f'params in JSON but not Python: {missing}')
    if extra:
        issues.append(f'params in Python but not JSON: {extra}')
    
    # 检查 execute (backend/desktop/control)
    if kind in ('backend', 'control') and 'def execute' not in py_code:
        issues.append('missing execute()')
    
    status = '✗' if issues else '✓'
    print(f'{status} {cmd}: {py_path}', end='')
    if issues:
        print(f'  ← {\" | \".join(issues)}')
    else:
        print()
"
```

### 4. JS handler 检查（仅 extension）

```
□ extension/dom_handlers_new/<cmd>.js 存在
□ 文件包含 registerHandler('<cmd>', ...) 调用
□ 如果是 function delegate，目标函数存在
```

```bash
python -c "
import json, os

for f in sorted(os.listdir('commands')):
    if not f.endswith('.json'): continue
    with open(f'commands/{f}') as fp:
        d = json.load(fp)
    if d['runtime'] != 'extension':
        continue
    cmd = d['cmd']
    handler = d.get('handler', {})
    
    js_path = f'extension/dom_handlers_new/{cmd}.js'
    if not os.path.exists(js_path):
        # 也检查旧路径
        js_path = f'extension/dom_handlers/{cmd}.js'
    
    if not os.path.exists(js_path):
        # background handler
        source = handler.get('source', '')
        if 'background_handlers' in source:
            print(f'✓ {cmd}: background handler: {source}')
            continue
        print(f'✗ {cmd}: JS file not found at extension/dom_handlers_new/{cmd}.js')
        continue
    
    with open(js_path, encoding='utf-8') as fp:
        js_code = fp.read()
    
    issues = []
    if f\"registerHandler('{cmd}'\" not in js_code and f'registerHandler(\"{cmd}\"' not in js_code:
        issues.append(f'registerHandler call missing or wrong cmd name')
    
    # 检查 function delegate
    func = handler.get('function', '')
    if func and func not in js_code:
        issues.append(f'delegate function \"{func}\" not found in JS')
    
    status = '✗' if issues else '✓'
    print(f'{status} {cmd}: {js_path}', end='')
    if issues:
        print(f'  ← {\" | \".join(issues)}')
    else:
        print()
"
```

### 5. 哨兵注释检查

extension Python 桩文件应该包含哨兵注释。

```bash
grep -l "AUTO-GENERATED" src/runtime/commands/extension_commands/*.py 2>/dev/null && echo "---" || true
# 列出有哨兵注释的文件数量
grep -c "AUTO-GENERATED" src/runtime/commands/extension_commands/*.py 2>/dev/null
```

### 6. handler execute() 参数引用正确性

检查 `execute()` 中 `extra.get("xxx")` 的参数名是否与 JSON `params[].name` 一致：

```bash
python -c "
import json, os, re

for f in sorted(os.listdir('commands')):
    if not f.endswith('.json'): continue
    with open(f'commands/{f}') as fp:
        d = json.load(fp)
    cmd = d['cmd']
    kind = d['handler']['kind']
    source = d['handler'].get('source', '')
    
    if kind == 'extension':
        continue  # extension 的 extra.get 在 JS 侧
    
    # 找 Python 文件
    if source and os.path.exists(source):
        py_path = source
    else:
        py_path = f'src/runtime/commands/backend_commands/{cmd}.py'
        if not os.path.exists(py_path):
            py_path = f'src/runtime/commands/desktop_commands/{cmd}.py'
    
    if not os.path.exists(py_path):
        continue
    
    with open(py_path, encoding='utf-8') as fp:
        py_code = fp.read()
    
    if 'def execute' not in py_code:
        continue
    
    json_params = {p['name'] for p in d.get('params', [])}
    # 提取 extra.get(\"xxx\") 中的引用
    extra_refs = set(re.findall(r'extra\.get\(\s*\"(\w+)\"', py_code))
    
    # extra 引用如果不在 json params 中，可能是拼写错误
    unknown = extra_refs - json_params
    unused = json_params - extra_refs
    
    issues = []
    if unknown:
        issues.append(f'extra.get refs not in JSON params: {unknown}')
    if unused:
        issues.append(f'JSON params not referenced in execute: {unused}')
    
    status = '✗' if issues else '✓'
    print(f'{status} {cmd}: {py_path}', end='')
    if issues:
        print(f'  ← {\" | \".join(issues)}')
    else:
        print()
"
```

## 常见问题及修复

| 问题 | 原因 | 修复 |
|------|------|------|
| `cmd mismatch` | JSON 改了 cmd 名但 Python 没改 | 同步 `@register_handler(cmd="...")` |
| `runtime mismatch` | JSON 改了 runtime 但 Python 没改 | 同步 `@register_handler(runtime="...")` |
| `params in JSON but not Python` | JSON 新增了参数但没跑 `generate_commands.py` | 运行脚本重新生成桩 |
| `params in Python but not JSON` | Python 手写了 Param 但 JSON 没加 | 先改 JSON 再重新生成 |
| `missing execute()` | backend/control 手写文件忘了加 execute | 补充 `async def execute()` |
| `JS file not found` | extension 指令没建 JS handler | 运行 `generate_commands.py` 生成，或手写 |
| `registerHandler call missing` | JS 文件 cmd 名写错 | 修正 `registerHandler('正确的cmd', ...)` |
| 哨兵注释缺失 | 手写覆盖了脚本生成的文件 | 重新运行 `generate_commands.py` 恢复桩，手写逻辑移到独立文件 |

## 一键检查

```bash
python scripts/generate_commands.py
python scripts/build_content_js.py
curl -X POST http://localhost:xxxx/api/commands/sync-check
curl -X POST http://localhost:xxxx/api/commands/validate
```
