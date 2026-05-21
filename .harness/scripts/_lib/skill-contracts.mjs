import { readdir, readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { join, resolve, relative } from "node:path";

export function parseFrontmatter(text) {
  const match = text.match(/^---\n([\s\S]*?)\n---/);
  if (!match) return {};
  const fields = {};
  for (const line of match[1].split("\n")) {
    const m = line.match(/^([A-Za-z0-9_-]+):\s*(.*)$/);
    if (m) fields[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
  return fields;
}

export async function readJson(path) {
  return JSON.parse(await readFile(path, "utf8"));
}

export async function skillIds(skillsDir) {
  if (!existsSync(skillsDir)) return [];
  const entries = await readdir(skillsDir, { withFileTypes: true });
  return entries.filter((entry) => entry.isDirectory()).map((entry) => entry.name).sort();
}

export async function readSkillFrontmatter(skillDir) {
  for (const name of ["SKILL.md", "SKILL.md.hbs"]) {
    const path = join(skillDir, name);
    if (existsSync(path)) return parseFrontmatter(await readFile(path, "utf8"));
  }
  return {};
}

export async function readSkillContract(skillDir) {
  const contractPath = join(skillDir, "skill.json");
  if (!existsSync(contractPath)) return null;
  return await readJson(contractPath);
}

export async function discoverContracts(skillsDir) {
  const contracts = [];
  for (const id of await skillIds(skillsDir)) {
    const skillDir = join(skillsDir, id);
    const frontmatter = await readSkillFrontmatter(skillDir);
    const contract = await readSkillContract(skillDir);
    contracts.push({
      id,
      frontmatter,
      contract,
      source: normalizeRelative(skillDir),
    });
  }
  return contracts;
}

export async function validateSkillContracts({ skillsDir, registryPath, permissionsPath }) {
  const errors = [];
  const warnings = [];
  const discovered = await discoverContracts(skillsDir);
  const registry = existsSync(registryPath) ? await readJson(registryPath) : null;
  const permissions = existsSync(permissionsPath) ? await readJson(permissionsPath) : null;
  const registryById = new Map((registry?.skills || []).map((skill) => [skill.id, skill]));

  if (!registry) errors.push(`missing skill registry: ${registryPath}`);
  else if (registry.schemaVersion !== 1) errors.push("skill registry schemaVersion must be 1");

  for (const item of discovered) {
    const { id, frontmatter, contract } = item;
    if (!contract) {
      errors.push(`${id}: missing skill.json`);
      continue;
    }
    if (contract.schemaVersion !== 1) errors.push(`${id}: skill.json schemaVersion must be 1`);
    if (contract.id !== id) errors.push(`${id}: skill.json id must match directory name`);
    if (frontmatter.name && contract.name !== frontmatter.name) errors.push(`${id}: skill.json name must match SKILL.md frontmatter`);
    if (!/^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/.test(contract.version || "")) errors.push(`${id}: version must be semver`);
    if (!Array.isArray(contract.capabilities) || contract.capabilities.length === 0) errors.push(`${id}: capabilities must be a non-empty array`);
    if (!contract.permissions || typeof contract.permissions !== "object") errors.push(`${id}: permissions object is required`);
    for (const key of ["allow", "deny"]) {
      if (!Array.isArray(contract.permissions?.[key])) errors.push(`${id}: permissions.${key} must be an array`);
    }
    const registered = registryById.get(id);
    if (!registered) {
      errors.push(`${id}: missing from ${registryPath}`);
    } else {
      for (const key of ["name", "version"]) {
        if (registered[key] !== contract[key]) errors.push(`${id}: registry ${key} drift (${registered[key]} != ${contract[key]})`);
      }
      if (JSON.stringify(registered.capabilities || []) !== JSON.stringify(contract.capabilities || [])) {
        errors.push(`${id}: registry capabilities drift`);
      }
    }
    const declaredPermissions = contract.permissions || {};
    const policyPermissions = permissions?.skills?.[id];
    if ((declaredPermissions.allow?.length || declaredPermissions.deny?.length) && !policyPermissions) {
      errors.push(`${id}: declares explicit permissions but is missing from permissions policy`);
    }
  }

  const discoveredIds = new Set(discovered.map((item) => item.id));
  for (const skill of registry?.skills || []) {
    if (!discoveredIds.has(skill.id)) errors.push(`${skill.id}: registry entry has no matching skill directory`);
  }
  for (const skill of Object.keys(permissions?.skills || {})) {
    if (!discoveredIds.has(skill)) warnings.push(`${skill}: permissions policy entry has no matching skill directory`);
  }

  return {
    status: errors.length === 0 ? "passed" : "failed",
    skills: discovered.length,
    registrySkills: registry?.skills?.length || 0,
    errors,
    warnings,
  };
}

export async function compareSkillSurfaces(surfaces) {
  const entries = [];
  for (const surface of surfaces) {
    entries.push({ ...surface, ids: await skillIds(surface.path) });
  }
  const all = new Set(entries.flatMap((entry) => entry.ids));
  const drift = {};
  for (const entry of entries) {
    const set = new Set(entry.ids);
    drift[entry.name] = {
      count: entry.ids.length,
      missing: [...all].filter((id) => !set.has(id)).sort(),
      extra: entry.ids.filter((id) => ![...all].includes(id)).sort(),
    };
  }
  return { surfaces: entries.map(({ name, path, ids }) => ({ name, path: normalizeRelative(path), count: ids.length, ids })), drift };
}

export function normalizeRelative(path) {
  return relative(resolve("."), path).replaceAll("\\", "/") || ".";
}
