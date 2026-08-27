# Change matrix — 改动路径速查

> 本项目 **six 类改动的验证动作完全不同**。本文件是 AGENTS.md「改动路径速查」的完整展开。
> 原则：**机械执行 > 文字约束**——凡能做成脚本检查的，绝不只写"请注意"。
> 结构测试只管 backend 层序（`config.json` `domains[].layers`），各域一致性由下表"机械兜底"列守护。

## 改动路径矩阵

| 改动路径 | 必须动作 | 机械兜底（现状 → 目标） |
|---|---|---|
| `commands/*.json` / handler | `rpa_new_command` 复跑（生成→构建→门禁→热重载一条龙） | ✅ 已机械化（`command_builder.py` → `check_command_quality.py`） |
| `src/runtime/commands/{desktop,control}_commands/` | 复跑 `command_builder.py` 校验注册一致；改控制流 evaluate 逻辑需 pytest | ⚠️ 全量目录一致性未机械化（单指令门禁为主） |
| `extension/` JS 源 | build_content/background → **dist 重建** → 自动重载扩展 | ⚠️ → 待建 `check-extension-dist-sync.mjs`（源 hash vs dist） |
| `src/runtime` 核心（runner/emitter） | **重启后端** + pytest（热重载不覆盖已在内存模块） | ⚠️ → 待建 dev-watch-restart（TODO P0-验证#3） |
| `skills/` | bump version + 同步 `~/.dsh/skills/` | ✅ `skills/scripts/check-project-skill-sync.mjs` |
| `rpa-dsh-plugin/lib/index.js`（服务端） | 极保守 + 重启 dsh web 验证 | ⚠️ → 待建 schema 冒烟（拦 `additionalProperties` 类事故） |
| workflow-editor 前端 | rebuild + 同步两处 profile 副本 | ⚠️ → 待建 `check-editor-bundle-sync.mjs` |
| 跨 ≥2 层 | 自审 + 提交信息声明 | ✅ `harness:check` 报 layer-spanning（golden #10） |

## 三个 scripts 目录职责

| 目录 | 归属 | 内容 | 能否动 |
|---|---|---|---|
| `scripts/` | **产品工具链** | generate/build/command_builder/verify_web_handler/native_host/安装脚本 等 17 个 | 产品代码，随项目走，**绝不并入 harness** |
| `skills/scripts/` | **项目 skill 依赖** | check_command_quality.py、check-project-skills.mjs、check-project-skill-sync.mjs、run/read_run.py 等 | 跟 skill 走，`command_builder` 也从此路径调用 |
| `.harness/scripts/` | **kit 骨架 + 少量项目脚本** | 40+ 个 kit 无关脚本 + ast_structural_check.py + (曾) check-project-skill-sync.mjs | kit 契约，**不硬删**（见下） |

**收拢方式不是合并目录，而是统一入口**：`npm run harness:check` 编排散在三处的项目门禁。

## 四个门禁脚本分工（勿混）

| 脚本 | 域 | 作用 |
|---|---|---|
| `scripts/command_builder.py` | 指令 | 编排器：写 JSON→生成桩→拼 JS→校验→调用质量门禁→热重载（`rpa_new_command` 执行体） |
| `skills/scripts/check_command_quality.py` | 指令 | 质量门禁：JSON 必需字段、handler 参数对齐、无哨兵、有 execute()、completed+=1 |
| `skills/scripts/check-project-skills.mjs` | skill | 仓库内部契约：skill.json ↔ project-skills.json 对齐（name/version/capabilities/description） |
| `skills/scripts/check-project-skill-sync.mjs` | skill | 跨目录同步：仓库 `skills/` ↔ `~/.dsh/skills/`（版本 + 内容 hash） |

## 结构检查的双实现（收拢时以谁为准）

- `npm run harness:check` → `node .harness/runners/structural-check.mjs` —— **空壳**，只打印 PASSED。
- `config.json` `structuralTest.command` → `python .harness/scripts/ast_structural_check.py` —— **权威实现**。

**收拢决策**：以 Python AST 为准，`harness:check` 编排时调用它；Node runner 退役或对齐。

## 环境事实（本机，可提权）

- **项目跑在本机**，无远程桌面。DSH GUI 与浏览器自动化同机，但**多窗口共存 + 无物理焦点在场**仍是 `rpa_capture` 绑错窗口的根因（需程序化绑定 `workWindowId`）。
- **沙箱可提权**：默认 `workspace-write` 只写工作区；用户可给 full access。RPA 后端要写 `RPA_HOME`、长期驻留、spawn 浏览器，需在提权后启动，不能用默认沙箱 pwsh 启动。

## kit 无关脚本处理

- 单人项目用不到 bench/eval/regression/ab/telemetry 等 ~30 个 kit 脚本：**不硬删**（可能被 hooks/config 引用，删除破坏 kit 契约 + 无实际收益）。
- 处理方式：harness:check 只编排项目用得到的；停用清单见架构文档。
