#!/usr/bin/env node
import { existsSync } from "node:fs";
import { resolve } from "node:path";
import {
  compareSkillSurfaces,
  validateSkillContracts,
} from "./_lib/skill-contracts.mjs";

function parseArgs(argv) {
  const opts = { cwd: process.cwd(), json: false, reportOnly: false };
  for (const arg of argv) {
    if (arg === "--json") opts.json = true;
    else if (arg === "--report-only") opts.reportOnly = true;
    else if (arg.startsWith("--cwd=")) opts.cwd = resolve(arg.slice("--cwd=".length));
  }
  return opts;
}

const opts = parseArgs(process.argv.slice(2));
const root = resolve(opts.cwd);
const templateSkills = resolve(root, "src/templates/.claude/skills");
const installedSkills = resolve(root, ".claude/skills");
const skillsDir = existsSync(templateSkills) ? templateSkills : installedSkills;
const registryPath = existsSync(templateSkills)
  ? resolve(root, "src/templates/.harness/skill-registry.json")
  : resolve(root, ".harness/skill-registry.json");
const permissionsPath = existsSync(templateSkills)
  ? resolve(root, "src/templates/.harness/permissions.json")
  : resolve(root, ".harness/permissions.json");

const validation = await validateSkillContracts({ skillsDir, registryPath, permissionsPath });
const report = await compareSkillSurfaces([
  { name: "templates", path: templateSkills },
  { name: "claude", path: installedSkills },
  { name: "agents", path: resolve(root, ".agents/skills") },
]);
const payload = { validation, report };

if (opts.json) {
  console.log(JSON.stringify(payload, null, 2));
} else {
  console.log(`skill contracts: ${validation.status} (${validation.skills} skills, registry ${validation.registrySkills})`);
  for (const surface of report.surfaces) {
    console.log(`  ${surface.name}: ${surface.count} skills at ${surface.path}`);
  }
  for (const [name, drift] of Object.entries(report.drift)) {
    if (drift.missing.length > 0) console.log(`  ${name} missing: ${drift.missing.join(", ")}`);
  }
  for (const warning of validation.warnings) console.warn(`warning: ${warning}`);
  for (const error of validation.errors) console.error(`error: ${error}`);
}

if (!opts.reportOnly && validation.status !== "passed") process.exit(1);
