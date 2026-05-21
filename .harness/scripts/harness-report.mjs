#!/usr/bin/env node
// harness:report — aggregate eval results + skill telemetry into a per-skill
// summary. Reads .harness/eval/results/*.jsonl and .harness/telemetry.jsonl.
//
// Output:
//   ### Eval results (last 7 days)
//   <per-task: pass/fail counts, avg tokens>
//   ### Skill invocations (last 7 days)
//   <per-skill: invocation count, sessions, last seen>
//   ### Drift signals
//   <skills that haven't been invoked in N days; tasks that have started failing>
//
// No external deps — pure Node stdlib.

import { readdir, readFile, stat } from "node:fs/promises";
import { existsSync } from "node:fs";
import { resolve, join } from "node:path";
import { isSkillInvocationRecord } from "./_lib/telemetry-schema.mjs";

const ROOT = process.cwd();
const RESULTS_DIR = resolve(ROOT, ".harness/eval/results");
const TELEMETRY = resolve(ROOT, ".harness/telemetry.jsonl");
const SKILLS_DIR = resolve(ROOT, ".claude/skills");
const NOW = Date.now();
const ONE_DAY = 24 * 60 * 60 * 1000;
const SEVEN_DAYS = 7 * ONE_DAY;
const FOURTEEN_DAYS = 14 * ONE_DAY;

async function readJsonl(path) {
  if (!existsSync(path)) return [];
  const raw = await readFile(path, "utf8");
  const out = [];
  for (const line of raw.split("\n")) {
    if (!line.trim()) continue;
    try {
      out.push(JSON.parse(line));
    } catch {
      /* skip malformed line */
    }
  }
  return out;
}

async function loadEvalResults() {
  if (!existsSync(RESULTS_DIR)) return [];
  const files = await readdir(RESULTS_DIR);
  const all = [];
  for (const f of files) {
    if (!f.endsWith(".jsonl")) continue;
    const path = join(RESULTS_DIR, f);
    const st = await stat(path);
    const rows = await readJsonl(path);
    for (const r of rows) {
      r._mtime = st.mtimeMs;
      all.push(r);
    }
  }
  return all;
}

function recent(rows, key = "ts") {
  return rows.filter((r) => {
    const t = r[key] ? new Date(r[key]).getTime() : r._mtime ?? 0;
    return NOW - t <= SEVEN_DAYS;
  });
}

async function loadKnownSkills() {
  if (!existsSync(SKILLS_DIR)) return [];
  const entries = await readdir(SKILLS_DIR, { withFileTypes: true });
  return entries
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort();
}

// Rows aged 7–14 days. Used as the comparator for week-over-week deltas
// so users can spot drift instead of staring at a single-week snapshot.
function priorWeek(rows, key = "ts") {
  return rows.filter((r) => {
    const t = r[key] ? new Date(r[key]).getTime() : r._mtime ?? 0;
    const age = NOW - t;
    return age > SEVEN_DAYS && age <= FOURTEEN_DAYS;
  });
}

function tokensOf(row) {
  return (row.grades ?? [])
    .filter((g) => g.dim === "efficiency")
    .reduce((sum, g) => {
      const m = g.info?.match(/^(\d+) tokens/);
      return sum + (m ? parseInt(m[1], 10) : 0);
    }, 0);
}

function fmtPct(num, total) {
  if (total === 0) return "n/a";
  return `${Math.round((num / total) * 100)}%`;
}

function summarizeEvals(rows) {
  const byTask = new Map();
  for (const r of rows) {
    const arr = byTask.get(r.taskId) ?? [];
    arr.push(r);
    byTask.set(r.taskId, arr);
  }
  console.log(`\n### Eval results (last 7 days, ${rows.length} runs)`);
  if (rows.length === 0) {
    console.log("  (no recent runs — try `npm run harness:eval -- --quick --transport=mock`)");
    return;
  }
  console.log(
    "  task                    pass-rate    runs   avg-tokens",
  );
  console.log(
    "  ----------------------  ----------   -----  ----------",
  );
  for (const [taskId, taskRows] of [...byTask.entries()].sort()) {
    const passed = taskRows.filter((r) => r.passed).length;
    const tokens = taskRows.reduce((s, r) => s + tokensOf(r), 0);
    const avgTokens = taskRows.length > 0 ? Math.round(tokens / taskRows.length) : 0;
    const pct = fmtPct(passed, taskRows.length);
    console.log(
      `  ${taskId.padEnd(22)}  ${pct.padStart(8)}     ${String(taskRows.length).padStart(3)}    ${String(avgTokens).padStart(8)}`,
    );
  }
}

function summarizeTelemetry(rows) {
  console.log(`\n### Skill invocations (last 7 days, ${rows.length} events)`);
  if (rows.length === 0) {
    console.log(
      "  (no skill invocations recorded — telemetry hook may not be installed)",
    );
    console.log(
      "  Verify `.claude/hooks/hooks.json` includes the Skill matcher.",
    );
    return;
  }
  const bySkill = new Map();
  for (const r of rows) {
    const arr = bySkill.get(r.skill) ?? [];
    arr.push(r);
    bySkill.set(r.skill, arr);
  }
  console.log("  skill                          invocations   last-seen");
  console.log("  -----------------------------  -----------   --------------------");
  for (const [skill, events] of [...bySkill.entries()].sort(
    (a, b) => b[1].length - a[1].length,
  )) {
    const last = events
      .map((e) => e.ts)
      .sort()
      .at(-1);
    console.log(
      `  ${skill.padEnd(29)}  ${String(events.length).padStart(8)}      ${last ?? "?"}`,
    );
  }
}

function driftSignals(evalRows, telemetryRows, knownSkills) {
  console.log(`\n### Drift signals`);
  const seen = new Set(telemetryRows.map((r) => r.skill));
  const unseen = knownSkills.filter((s) => !seen.has(s));
  if (unseen.length > 0) {
    console.log(`  skills not invoked in 7 days: ${unseen.join(", ")}`);
  }
  // Tasks failing in their most recent run.
  const latest = new Map();
  for (const r of evalRows.sort((a, b) => (a.ts ?? "").localeCompare(b.ts ?? ""))) {
    latest.set(r.taskId, r);
  }
  const regressing = [...latest.values()].filter((r) => !r.passed);
  if (regressing.length > 0) {
    console.log(
      `  tasks failing in their latest run: ${regressing.map((r) => r.taskId).join(", ")}`,
    );
  }
  if (unseen.length === 0 && regressing.length === 0) {
    console.log("  (none)");
  }
}

// Aggregate eval rows by task into { passed, total, tokens }.
function aggregateEvals(rows) {
  const byTask = new Map();
  for (const r of rows) {
    const cur = byTask.get(r.taskId) ?? { passed: 0, total: 0, tokens: 0 };
    cur.total++;
    if (r.passed) cur.passed++;
    cur.tokens += tokensOf(r);
    byTask.set(r.taskId, cur);
  }
  return byTask;
}

// Render a single delta line. signMode controls icon meaning — for pass-rate,
// up is good; for tokens, up is bad; for skill invocations, neutral.
function fmtDelta(now, then, signMode = "neutral", unit = "") {
  if (then === undefined) return `(new) ${now}${unit}`;
  const diff = now - then;
  if (diff === 0) return `${now}${unit} → ${then}${unit}  (=)`;
  let arrow = diff > 0 ? "↑" : "↓";
  // Color the arrow by "is this a regression?"
  let marker = " ";
  if (signMode === "good-up") marker = diff > 0 ? "+" : "-";
  else if (signMode === "good-down") marker = diff > 0 ? "-" : "+";
  return `${now}${unit} ← ${then}${unit}  (${arrow}${marker} ${Math.abs(diff)}${unit})`;
}

function weekOverWeek(evalRecent, evalPrior, telRecent, telPrior) {
  console.log(`\n### Week-over-week (last 7d vs prior 7d)`);
  const aRecent = aggregateEvals(evalRecent);
  const aPrior = aggregateEvals(evalPrior);

  if (aRecent.size === 0 && aPrior.size === 0) {
    console.log("  (no eval data in either window — run `npm run harness:eval`)");
  } else {
    console.log("  task                    pass-rate (now ← prior)        avg-tokens (now ← prior)");
    console.log("  ----------------------  ----------------------------   --------------------------");
    const taskIds = new Set([...aRecent.keys(), ...aPrior.keys()]);
    for (const t of [...taskIds].sort()) {
      const now = aRecent.get(t);
      const prior = aPrior.get(t);
      const nowRate = now ? Math.round((now.passed / now.total) * 100) : null;
      const priorRate = prior ? Math.round((prior.passed / prior.total) * 100) : null;
      const nowTok = now && now.total > 0 ? Math.round(now.tokens / now.total) : 0;
      const priorTok = prior && prior.total > 0 ? Math.round(prior.tokens / prior.total) : 0;
      const rateCell = nowRate === null
        ? "(absent now)"
        : priorRate === null
          ? `${nowRate}% (new)`
          : `${nowRate}% ← ${priorRate}%  (${nowRate - priorRate >= 0 ? "+" : ""}${nowRate - priorRate})`;
      const tokCell = nowTok === 0 && priorTok === 0
        ? "—"
        : `${nowTok} ← ${priorTok}  (${nowTok - priorTok >= 0 ? "+" : ""}${nowTok - priorTok})`;
      console.log(
        `  ${t.padEnd(22)}  ${rateCell.padEnd(30)} ${tokCell}`,
      );
    }
  }

  // Skill invocation deltas.
  const recentBySkill = new Map();
  for (const r of telRecent) recentBySkill.set(r.skill, (recentBySkill.get(r.skill) ?? 0) + 1);
  const priorBySkill = new Map();
  for (const r of telPrior) priorBySkill.set(r.skill, (priorBySkill.get(r.skill) ?? 0) + 1);

  const allSkills = new Set([...recentBySkill.keys(), ...priorBySkill.keys()]);
  if (allSkills.size > 0) {
    console.log("\n  skill                          invocations (now ← prior)");
    console.log("  -----------------------------  -------------------------------");
    for (const s of [...allSkills].sort()) {
      const n = recentBySkill.get(s) ?? 0;
      const p = priorBySkill.get(s) ?? 0;
      const d = n - p;
      const cell = p === 0 ? `${n}  (new)` : `${n} ← ${p}  (${d >= 0 ? "+" : ""}${d})`;
      console.log(`  ${s.padEnd(29)}  ${cell}`);
    }
  }
}

async function main() {
  const evalAll = await loadEvalResults();
  const telemetryAll = await readJsonl(TELEMETRY);
  const skillTelemetryAll = telemetryAll.filter(isSkillInvocationRecord);
  const knownSkills = await loadKnownSkills();
  const evalRows = recent(evalAll);
  const evalPrior = priorWeek(evalAll);
  const telemetryRows = recent(skillTelemetryAll);
  const telemetryPrior = priorWeek(skillTelemetryAll);

  console.log("=== agent-harness-kit report ===");
  console.log(`Generated: ${new Date().toISOString()}`);
  summarizeEvals(evalRows);
  summarizeTelemetry(telemetryRows);
  weekOverWeek(evalRows, evalPrior, telemetryRows, telemetryPrior);
  driftSignals(evalRows, telemetryRows, knownSkills);
  console.log("");
}

await main();
