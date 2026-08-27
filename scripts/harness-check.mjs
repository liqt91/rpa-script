#!/usr/bin/env node
/**
 * harness:check — 项目门禁统一入口（编排 L0 + L1）。
 *
 * 按序执行以下门禁，任一失败即整体失败（退出码非 0）：
 *   L0 静态：ast_structural_check.py（backend 层序，前向依赖）
 *   命令校验：validate_commands.py（COMMAND_REGISTRY 一致性）
 *   L1 契约：check_project_skills.mjs（仓库内部 skill 契约）
 *   L1 同步：check_project_skill_sync.mjs（仓库 skills/ ↔ ~/.dsh/skills/）
 *
 * 用法：node scripts/harness-check.mjs [--skip-tests]
 *   pytest（L2）较慢，不默认跑；`--with-tests` 追加 pytest -q。
 */

import { spawnSync } from "node:child_process";
import { resolve } from "node:path";

const ROOT = process.cwd();
const gates = [
  { label: "ast structural check", cmd: "python", args: [".harness/scripts/ast_structural_check.py"] },
  { label: "command registry validate", cmd: "python", args: [".harness/runners/validate_commands.py"] },
  { label: "skills contract", cmd: "node", args: ["skills/scripts/check-project-skills.mjs"] },
  { label: "skills sync", cmd: "node", args: ["skills/scripts/check-project-skill-sync.mjs"] },
];

const withTests = process.argv.includes("--with-tests");
if (withTests) {
  gates.push({ label: "pytest", cmd: "python", args: ["-m", "pytest", "-q"] });
}

let failed = 0;
for (const g of gates) {
  const r = spawnSync(g.cmd, g.args, { cwd: ROOT, stdio: "inherit", shell: process.platform === "win32" });
  const ok = r.status === 0;
  console.log(`\n[${ok ? "PASS" : "FAIL"}] ${g.label}`);
  if (!ok) failed++;
}

console.log(`\nharness:check ${failed === 0 ? "PASSED" : `FAILED (${failed} gate(s))`}`);
process.exit(failed === 0 ? 0 : 1);
