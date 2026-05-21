#!/usr/bin/env node
import { existsSync, readFileSync, appendFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";

const ROOT = process.env.CLAUDE_PROJECT_DIR || process.cwd();
const POLICY_PATH = resolve(ROOT, ".harness/permissions.json");
const TELEMETRY_PATH = resolve(ROOT, ".harness/telemetry.jsonl");

function readStdin() {
  return new Promise((resolveRead) => {
    let input = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => {
      input += chunk;
    });
    process.stdin.on("end", () => resolveRead(input));
  });
}

function parseJson(text, fallback = null) {
  try {
    return JSON.parse(text);
  } catch {
    return fallback;
  }
}

function readPolicy() {
  if (!existsSync(POLICY_PATH)) return null;
  return parseJson(readFileSync(POLICY_PATH, "utf8"));
}

function inferSkillFromTelemetry(sessionId) {
  if (!sessionId || !existsSync(TELEMETRY_PATH)) return "";
  const lines = readFileSync(TELEMETRY_PATH, "utf8").trim().split("\n").filter(Boolean).slice(-500);
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    const row = parseJson(lines[i]);
    if (!row || row.event !== "skill_invoked") continue;
    if ((row.session_id || row.sessionId || "") === sessionId && row.skill) return row.skill;
  }
  return "";
}

function activeSkill(payload) {
  return (
    process.env.AHK_ACTIVE_SKILL ||
    payload.active_skill ||
    payload.activeSkill ||
    payload.skill ||
    payload.tool_input?.active_skill ||
    payload.tool_input?.skill_context ||
    inferSkillFromTelemetry(payload.session_id || payload.sessionId) ||
    ""
  );
}

function toolCommand(payload) {
  return payload.tool_input?.command || payload.tool_input?.pattern || payload.tool_input?.file_path || "";
}

function wildcardToRegExp(pattern) {
  const escaped = pattern.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\\\*/g, ".*");
  return new RegExp(`^${escaped}$`);
}

function permissionMatches(permission, payload) {
  const toolName = payload.tool_name || "";
  if (permission === "*" || permission === toolName) return true;
  const bashMatch = permission.match(/^Bash\((.*)\)$/);
  if (toolName === "Bash" && bashMatch) {
    return wildcardToRegExp(bashMatch[1]).test(toolCommand(payload));
  }
  return false;
}

function policyForSkill(policy, skill) {
  const skillPolicy = policy?.skills?.[skill];
  if (!skillPolicy) return policy?.default || null;
  return {
    allow: skillPolicy.allow ?? policy?.default?.allow ?? [],
    deny: [...(policy?.default?.deny ?? []), ...(skillPolicy.deny ?? [])],
  };
}

function deny(reason) {
  const out = {
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: reason,
    },
  };
  process.stdout.write(JSON.stringify(out));
}

function logBypass(skill, payload, reason) {
  mkdirSync(resolve(ROOT, ".harness"), { recursive: true });
  const row = {
    ts: new Date().toISOString(),
    bypass: process.env.AHK_ALLOW_BYPASS === "1" ? "AHK_ALLOW_BYPASS" : "AHK_SKILL_PERMISSIONS_MODE=warn",
    rule: "skill-permission-guard",
    skill,
    tool: payload.tool_name || "",
    reason,
  };
  appendFileSync(resolve(ROOT, ".harness/bypass.log"), JSON.stringify(row) + "\n");
}

const input = await readStdin();
const payload = parseJson(input, {});
const policy = readPolicy();
if (!policy) process.exit(0);

const skill = activeSkill(payload);
if (!skill) process.exit(0);

const rule = policyForSkill(policy, skill);
if (!rule) process.exit(0);

const denied = (rule.deny || []).find((permission) => permissionMatches(permission, payload));
let reason = "";
if (denied) {
  reason = `Skill "${skill}" is not allowed to use ${payload.tool_name || "this tool"} by deny rule ${denied}.`;
} else if (Array.isArray(rule.allow) && rule.allow.length > 0) {
  const allowed = rule.allow.some((permission) => permissionMatches(permission, payload));
  if (!allowed) {
    reason = `Skill "${skill}" is not allowed to use ${payload.tool_name || "this tool"} by .harness/permissions.json.`;
  }
}

if (!reason) process.exit(0);

if (process.env.AHK_ALLOW_BYPASS === "1" || process.env.AHK_SKILL_PERMISSIONS_MODE === "warn") {
  logBypass(skill, payload, reason);
  process.exit(0);
}

deny(reason);
