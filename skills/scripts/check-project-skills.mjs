#!/usr/bin/env node
// check-project-skills.mjs — contract check for the project's own skills in skills/.
// Independent from the kit's .harness/scripts/check-skill-contracts.mjs (which only
// scans .claude/skills/). Same rule model: skill.json contract + frontmatter name
// match + registry (skills/project-skills.json) alignment.
//
// Usage: node skills/scripts/check-project-skills.mjs [--json]

import { existsSync } from "node:fs";
import { readdir, readFile } from "node:fs/promises";
import { join, resolve } from "node:path";

const ROOT = process.cwd();
const SKILLS_DIR = resolve(ROOT, "skills");
const REGISTRY_PATH = join(SKILLS_DIR, "project-skills.json");

function parseFrontmatter(text) {
  const match = text.match(/^---\n([\s\S]*?)\n---/);
  if (!match) return {};
  const fields = {};
  for (const line of match[1].split("\n")) {
    const m = line.match(/^([A-Za-z0-9_-]+):\s*(.*)$/);
    if (m) fields[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
  return fields;
}

async function main() {
  const errors = [];
  const entries = (await readdir(SKILLS_DIR, { withFileTypes: true }))
    .filter((e) => e.isDirectory() && e.name !== "scripts")
    .map((e) => e.name)
    .sort();

  const registry = existsSync(REGISTRY_PATH)
    ? JSON.parse(await readFile(REGISTRY_PATH, "utf8"))
    : null;
  if (!registry) errors.push(`missing project skill registry: skills/project-skills.json`);
  else if (registry.schemaVersion !== 1) errors.push("project-skills.json schemaVersion must be 1");
  const registryById = new Map((registry?.skills || []).map((s) => [s.id, s]));

  for (const id of entries) {
    const dir = join(SKILLS_DIR, id);
    const mdPath = join(dir, "SKILL.md");
    const jsonPath = join(dir, "skill.json");
    if (!existsSync(mdPath)) { errors.push(`${id}: missing SKILL.md`); continue; }
    if (!existsSync(jsonPath)) { errors.push(`${id}: missing skill.json`); continue; }

    const fm = parseFrontmatter(await readFile(mdPath, "utf8"));
    let contract = null;
    try { contract = JSON.parse(await readFile(jsonPath, "utf8")); }
    catch { errors.push(`${id}: skill.json is not valid JSON`); continue; }

    if (contract.schemaVersion !== 1) errors.push(`${id}: skill.json schemaVersion must be 1`);
    if (contract.id !== id) errors.push(`${id}: skill.json id must match directory name`);
    if (fm.name && contract.name !== fm.name)
      errors.push(`${id}: skill.json name must match SKILL.md frontmatter (${contract.name} != ${fm.name})`);
    if (!/^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/.test(contract.version || ""))
      errors.push(`${id}: version must be semver`);
    if (!Array.isArray(contract.capabilities) || contract.capabilities.length === 0)
      errors.push(`${id}: capabilities must be a non-empty array`);
    if (!contract.permissions || typeof contract.permissions !== "object")
      errors.push(`${id}: permissions object is required`);
    for (const key of ["allow", "deny"]) {
      if (!Array.isArray(contract.permissions?.[key]))
        errors.push(`${id}: permissions.${key} must be an array`);
    }

    const reg = registryById.get(id);
    if (!reg) errors.push(`${id}: missing from skills/project-skills.json`);
    else {
      if (reg.name !== contract.name) errors.push(`${id}: registry name drift (${reg.name} != ${contract.name})`);
      if (reg.version !== contract.version) errors.push(`${id}: registry version drift (${reg.version} != ${contract.version})`);
      if (JSON.stringify(reg.capabilities || []) !== JSON.stringify(contract.capabilities || []))
        errors.push(`${id}: registry capabilities drift`);
    }
  }

  const discoveredIds = new Set(entries);
  for (const s of registry?.skills || []) {
    if (!discoveredIds.has(s.id)) errors.push(`${s.id}: registry entry has no matching skills/ directory`);
  }

  const status = errors.length === 0 ? "passed" : "failed";
  if (process.argv.includes("--json")) {
    console.log(JSON.stringify({ status, skills: entries.length, errors }, null, 2));
  } else {
    console.log(`project skills: ${status} (${entries.length} skills)`);
    for (const e of errors) console.error(`error: ${e}`);
  }
  if (status !== "passed") process.exit(1);
}

main();
