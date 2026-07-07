# 夜间 Loop 操作手册

## 前置准备（每台新电脑执行一次）

### 1. Deep Code 权限配置

在 Deep Code 的 settings.json 中（项目级 `.deepcode/settings.json` 或用户级 `~/.deepcode/settings.json`），将夜间任务涉及的权限设为 `"allow"`：

```json
{
  "permissions": {
    "defaultMode": "ask",
    "allow": [
      "Bash(read-in-cwd:*)",
      "Bash(write-in-cwd:*)",
      "Bash(delete-in-cwd:*)",
      "Bash(query-git-log:*)",
      "Bash(mutate-git-log:*)",
      "Bash(network:*)",
      "Read(*)",
      "Write(*)",
      "Edit(*)"
    ]
  }
}
```

> `"network:*"` 是 git push/pull 必须的。如果不放心长期开，可以每晚手动 `chmod` 切换。

### 2. Git 代理（如果在内网）

```bash
git config --global http.proxy http://127.0.0.1:7890
git config --global https.proxy http://127.0.0.1:7890
```

### 3. 确保环境可用

```bash
cd ~/Projects/rpa-script
.venv/Scripts/pip install -r requirements.txt --quiet
cd src/ui/workflow-editor && npm install --silent
```

---

## 每晚操作流程

### Step 1: 拉取最新代码 + 确定今晚任务

```bash
cd ~/Projects/rpa-script
git pull origin master
cat TODO.md | grep '\[ \]' | head -3   # 看前三个待办
```

### Step 2: 打开 Deep Code，粘贴以下提示词

---

```
## 会话指令

你正在执行夜间自动化任务。请严格遵守以下流程：

### 0. 环境检查
- 如果 package.json 或 requirements.txt 自上次会话有变更，先 npm install / pip install
- 如果 src/ui/ 有变更，先 npm run build

### 1. 选择任务
读 TODO.md，选择第一个标记为 [ ] 的夜间任务。

### 2. 执行任务
- 只改任务相关的文件，不做无关"优化"
- 每个改动后立即运行相关测试
- 如果测试失败，修复后重试，最多 3 次
- 如果 3 次后仍失败，跳过该任务，在 TODO.md 该任务后追加 `(FAILED: <原因>)`

### 3. 验收
- 对照任务的"验收"条件逐一检查
- 如果验收不通过，回到步骤 2

### 4. 提交
- `git add -A`
- `git commit -m "<分类前缀>: <任务描述>"`
- 不 push，早上手动 `git push origin master`

### 5. 标记完成 + 记录进度
- 将 TODO.md 中该任务的 [ ] 改为 [x]
- 在 .harness/PROGRESS.md 末尾追加一行: `YYYY-MM-DD HH:MM | night_loop | <任务编号> | <简要结果>`
- `git add TODO.md .harness/PROGRESS.md && git commit -m "night: complete <任务编号>"`

### 6. 继续下一个
- 如果还有未完成的夜间任务，回到步骤 1 继续
- 检查方式: `grep '\[ \]' TODO.md | head -1`
- 如果 TODO.md 中没有 [ ] 夜间任务了，输出 `NIGHT_LOOP_DONE: 全部完成`
- 单任务超 30 分钟仍未完成的，跳过并标记 `(TIMEOUT)`，继续下一个

### 注意事项
- 不要改 CLAUDE.md、AGENTS.md、.harness/ 下非 PROGRESS.md 的文件
- 不要改 TODO.md 中非夜间任务区段的内容
- 遇到需要用户确认的决策（如选择方案 A/B），选择最保守/最简单的方案，在 commit message 中注明
```

---

### 期望结果

每天早上检查：

```bash
cd ~/Projects/rpa-script
git pull
cat .harness/PROGRESS.md | tail -3
cat TODO.md | grep '\[x\].*夜间' | wc -l  # 已完成数量
cat TODO.md | grep '\[ \].*夜间'          # 剩余待办
```
