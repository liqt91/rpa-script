#!/usr/bin/env node
/**
 * 项目 skill 同步检查：比较仓库 skills/ 与用户级 ~/.dsh/skills/。
 *
 * 背景（见 .harness/docs/agent-failures.md #project-skill-sync-drift）：
 * DSH 实际加载的是 ~/.dsh/skills/<id>/，不是仓库 skills/。agent 改仓库 skill 后
 * 若不同步，新事实/修正永不生效。本脚本机械比较两者，暴露漂移。
 *
 * 检查项：
 *   - 源（仓库 skills/）每个 skill 在目标（~/.dsh/skills/）存在；
 *   - skill.json 的 version 一致；
 *   - SKILL.md 内容 hash 一致（捕获「内容改了但 version 没 bump」的漂移）；
 *   - references/ 等附属文件按递归 hash 比对（SKILL.md 之外的内容漂移）。
 *
 * 用法：
 *   node .harness/scripts/check-project-skill-sync.mjs [--json] [--fix-days=N]
 *   --json        输出 JSON（供 agent 程序化读取）
 *   --report-only 只报告不退出非零
 */
import { readdir, readFile, stat } from "node:fs/promises";
import { existsSync } from "node:fs";
import { createHash } from "node:crypto";
import { join, resolve, relative } from "node:path";
import { homedir } from "node:os";

function parseArgs(argv) {
  const opts = { json: false, reportOnly: false, cwd: process.cwd() };
  for (const arg of argv) {
    if (arg === "--json") opts.json = true;
    else if (arg === "--report-only") opts.reportOnly = true;
    else if (arg.startsWith("--cwd=")) opts.cwd = resolve(arg.slice("--cwd=".length));
  }
  return opts;
}

const opts = parseArgs(process.argv.slice(2));
const root = resolve(opts.cwd);
const SRC = resolve(root, "skills");
const DST = process.env.DSH_SKILLS_DIR || join(homedir(), ".dsh", "skills");

async function sha256(buf) {
  return createHash("sha256").update(buf).digest("hex").slice(0, 16);
}

async function fileHash(p) {
  try {
    return await sha256(await readFile(p));
  } catch {
    return null;
  }
}

async function dirFingerprint(dir) {
  // 返回 { [相对路径]: hash } 的映射，覆盖目录内所有非 node_modules/__pycache__ 文件
  const out = {};
  async function walk(d, prefix) {
    let entries;
    try {
      entries = await readdir(d, { withFileTypes: true });
    } catch {
      return;
    }
    for (const e of entries) {
      if (e.name === "node_modules" || e.name === "__pycache__") continue;
      const full = join(d, e.name);
      const rel = prefix ? `${prefix}/${e.name}` : e.name;
      if (e.isDirectory()) {
        await walk(full, rel);
      } else if (e.isFile()) {
        const h = await fileHash(full);
        if (h != null) out[rel] = h;
      }
    }
  }
  await walk(dir, "");
  return out;
}

async function sourceSkills() {
  const ids = [];
  const entries = await readdir(SRC, { withFileTypes: true });
  for (const e of entries) {
    if (!e.isDirectory()) continue;
    // 只有含 skill.json 的目录才算 skill（排除 scripts/、__pycache__ 等）
    if (existsSync(join(SRC, e.name, "skill.json"))) ids.push(e.name);
  }
  return ids.sort();
}

async function main() {
  const drift = [];
  const warnings = [];
  const ids = await sourceSkills();
  let checked = 0;

  for (const id of ids) {
    const srcDir = join(SRC, id);
    const dstDir = join(DST, id);
    if (!existsSync(dstDir)) {
      drift.push({ id, kind: "missing-in-dst", detail: `${id}: 目标 ~/.dsh/skills 中不存在` });
      continue;
    }
    checked++;

    // version 比对
    const srcVer = (JSON.parse(await readFile(join(srcDir, "skill.json"), "utf8"))).version;
    const dstVerPath = join(dstDir, "skill.json");
    if (!existsSync(dstVerPath)) {
      drift.push({ id, kind: "missing-skill.json", detail: `${id}: 目标缺 skill.json` });
      continue;
    }
    const dstVer = (JSON.parse(await readFile(dstVerPath, "utf8"))).version;
    if (srcVer !== dstVer) {
      drift.push({ id, kind: "version-drift", detail: `${id}: version 漂移 (仓库 ${srcVer} != 目标 ${dstVer})` });
    }

    // 内容 hash 比对（SKILL.md + references 等附属文件）
    const srcFp = await dirFingerprint(srcDir);
    const dstFp = await dirFingerprint(dstDir);
    for (const [rel, h] of Object.entries(srcFp)) {
      if (dstFp[rel] !== h) {
        drift.push({
          id,
          kind: "content-drift",
          detail: `${id}: 文件内容漂移 (${rel}${dstFp[rel] == null ? " 目标缺失" : " hash 不一致"})`,
        });
      }
    }
  }

  // 目标里多出的（源没有的）skill，仅警告（可能是用户级手工装的）
  let dstIds = [];
  try {
    dstIds = (await readdir(DST, { withFileTypes: true }))
      .filter((e) => e.isDirectory() && existsSync(join(DST, e.name, "skill.json")))
      .map((e) => e.name);
  } catch {}
  const srcIdSet = new Set(ids);
  for (const d of dstIds) {
    if (!srcIdSet.has(d)) warnings.push(`${d}: 目标有、仓库无（可能是用户级独立安装，忽略）`);
  }

  const status = drift.length === 0 ? "passed" : "failed";
  const payload = {
    status,
    source: relative(root, SRC) || "skills",
    target: DST,
    skills: ids.length,
    checked,
    drift,
    warnings,
  };

  if (opts.json) {
    console.log(JSON.stringify(payload, null, 2));
  } else {
    console.log(`project skill sync: ${status} (${checked}/${ids.length} skills 已核实)`);
    console.log(`  source=${payload.source}  target=${DST}`);
    for (const d of drift) console.error(`drift: ${d.detail}`);
    for (const w of warnings) console.warn(`warning: ${w}`);
  }

  if (!opts.reportOnly && status !== "passed") process.exit(1);
}

main();
