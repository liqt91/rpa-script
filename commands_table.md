# 扩展模式指令清单
| 命令类型 | Handler | 本地执行 | 说明 | 参数 |
|---|---|---|---|---|
| openBrowser | openBrowser | 否 | 页面导航 - 打开浏览器 | browserType, url, windowState, saveToVar |
| closeBrowser | closeBrowser | 否 | 页面导航 - 关闭浏览器窗口 | windowVar |
| newTab | newTab | 否 | 页面导航 - 新建标签页 | windowVar, url |
| navigate | navigate | 否 | 页面导航 - 打开网页 | url, windowVar, waitLoad, timeout, saveToVar |
| getCurrentUrl | getCurrentUrl | 否 | 页面导航 - 获取当前URL | windowVar, varName |
| click | click | 否 | 元素点击 - 点击元素 | windowVar, element_name, scope, forceJs, humanLike |
| hover | hover | 否 | 元素点击 - 悬停 | element_name, scope |
| unhover | unhover | 否 | 元素点击 - 取消悬停 | windowVar, element_name, scope |
| sleep | wait | 否 | 等待 - 等待固定时间 | windowVar, seconds |
| waitForElement | wait | 否 | 等待 - 等待元素出现 | windowVar, element_name, scope, timeout |
| scrollOneScreen | scroll | 否 | 滚动 - 滚动一屏 | windowVar, humanLike |
| scrollToBottom | scroll | 否 | 滚动 - 滚动到底部 | windowVar, humanLike |
| scrollToTop | scroll | 否 | 滚动 - 滚动到顶部 | windowVar, humanLike |
| scrollBy | scroll | 否 | 滚动 - 滚动指定距离 | windowVar, x, y, humanLike |
| setVar | setVar | 是 | 变量与数据 - 设置变量 | name, value, valueType |
| appendToList | appendToList | 是 | 变量与数据 - 追加到列表 | listName, value |
| stringConcat | stringConcat | 是 | 变量与数据 - 字符串拼接 | targetVar, part1, part2, part3 |
| increment | increment | 是 | 变量与数据 - 计数器累加 | varName, step |
| setDictValue | setDictValue | 是 | 变量与数据 - 设置字典值 | dictName, key, value |
| getDictValue | getDictValue | 是 | 变量与数据 - 获取字典值 | dictName, key, varName |
| removeDictKey | removeDictKey | 是 | 变量与数据 - 删除字典键 | dictName, key |
| input | input | 否 | 文本输入 - 输入文本 | windowVar, element_name, scope, text, clearFirst |
| inputAndPressEnter | input | 否 | 文本输入 - 输入并回车 | windowVar, element_name, scope, text, clearFirst |
| clearInput | clearInput | 否 | 文本输入 - 清空输入框 | windowVar, element_name |
| pressKey | pressKey | 否 | 文本输入 - 按键 | windowVar, key |
| selectOption | selectOption | 否 | 文本输入 - 下拉框选择 | windowVar, element_name, by, value |
| getText | extract | 否 | 数据提取 - 获取元素文本 | windowVar, element_name, scope, varName |
| getAttr | extract | 否 | 数据提取 - 获取元素属性 | windowVar, element_name, scope, attrName, varName |
| getHtml | extract | 否 | 数据提取 - 获取元素HTML | windowVar, element_name, mode, varName |
| getValue | extract | 否 | 数据提取 - 获取输入框值 | windowVar, element_name, varName |
| readTableCell | readTableCell | 是 | 数据表格 - 读取表格单元格 | rowIndex, columnName, varName |
| writeTableCell | writeTableCell | 是 | 数据表格 - 写入表格单元格 | rowIndex, columnName, value |
| getTableRowCount | getTableRowCount | 是 | 数据表格 - 获取表格行数 | varName |
| writeTableRow | writeTableRow | 是 | 数据表格 - 写入表格行 | writeMode, rowIndex, rowData |
| ifElementVisible | - | 否 | 条件判断 - 如果元素可见/不可见 | element_name, element_names, scope, operator |
| ifTextContains | - | 否 | 条件判断 - 如果元素文本 | element_name, scope, operator, text |
| ifTextEquals | - | 否 | 条件判断 - 如果元素文本等于 | element_name, text |
| ifVarEquals | - | 否 | 条件判断 - 如果变量比较 | varName, operator, value, valueType |
| ifVarContains | - | 否 | 条件判断 - 如果变量匹配 | varName, operator, value |
| ifListContains | - | 否 | 条件判断 - 如果列表包含 | listName, value |
| ifDictContains | - | 否 | 条件判断 - 如果字典包含键 | dictName, key |
| else | - | 否 | 条件判断 - 否则 | - |
| endIf | - | 否 | 条件判断 - 结束如果 | - |
| forEachElement | - | 否 | 循环 - 循环相似元素 | element_name, scope, itemVar, indexVar |
| forRange | - | 否 | 循环 - 循环次数 | start, end, step, varName |
| forList | - | 否 | 循环 - 循环列表 | listVar, itemVar, indexVar |
| forEachTableRow | - | 否 | 循环 - 循环表格 | itemVar, indexVar |
| whileCondition | - | 否 | 循环 - 循环直到条件成立 | conditionType, element_name, scope, urlPattern, varName, varValue, maxIterations |
| break | - | 否 | 循环 - 跳出循环 | - |
| continue | - | 否 | 循环 - 继续下一次循环 | - |
| endFor | - | 否 | 循环 - 结束循环 | - |
| log | log | 是 | 输出与日志 - 记录日志 | message, level |
| httpRequest | httpRequest | 是 | 网络请求 - HTTP请求 | method, url, headers, body, timeout, resultVar |
| try | - | 否 | 异常处理 - 捕获异常 | - |
| catch | - | 否 | 异常处理 - 异常处理 | errorVar |
| endTry | - | 否 | 异常处理 - 结束捕获 | - |
| custom | custom | 是 | 自定义 - 自定义代码 | code, description, resultVar |
| executeJs | executeJs | 否 | 自定义 - 执行JS | script, resultVar |
