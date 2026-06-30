#!/usr/bin/env node
// improvement-bundle.mjs — deterministic step for /propose-harness-improvement.
// Replaces the "ask the agent to summarize recent failures" LLM turn with a
// mechanical sweep over telemetry + git history + bypass log.
//
// Output (JSON, stdout or --out):
//   {
//     window_days: <n>,
//     recent_failures: [ {ts, event, source, detail} ],
//     recurring_patterns: [ {pattern, count, sample_ts} ],
//     classification: { context, rule, tool_skill, architecture, prompt },
//     fix_targets: [ {file, why} ]
//   }
//
// Classification rubric mirrors the (a)-(e) buckets in the SKILL.md:
//   (a) context        — pretooluse denials referencing rules in .harness/docs/
//   (b) rule           — structural-test failures / baseline drift
//   (c) tool/skill     — bypass.log entries / missing-skill prompt-guard hits
//   (d) architecture   — layer-violation patterns appearing >=3 times
//   (e) prompt         — skill_invoked followed by failure within same session
//
// The buckets are heuristic; an LLM still makes the final call. The point is
// to hand it a dense, factual digest instead of forcing it to scan files
// blind.

import { readFileSync, existsSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";

const ROOT = process.env.CLAUDE_PROJECT_DIR || process.cwd();

function parseArgs(argv) {
  const out = { window: 14, out: null };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--window") out.window = Number(argv[++i]) || 14;
    else if (argv[i] === "--out") out.out = argv[++i];
  }
  return out;
}

function readJsonl(path) {
  if (!existsSync(path)) return [];
  const body = readFileSync(path, "utf8");
  const out = [];
  for (const line of body.split("\n")) {
    if (!line.trim()) continue;
    try { out.push(JSON.parse(line)); } catch { /* skip malformed */ }
  }
  return out;
}

function isWithin(ts, days) {
  const t = Date.parse(ts);
  if (!Number.isFinite(t)) return false;
  return (Date.now() - t) <= days * 24 * 3600 * 1000;
}

function gitLogFixes(days) {
  const since = `${days}.days`;
  const r = spawnSync("git", ["log", `--since=${since}`, "--oneline", "--grep=fix\\|revert\\|hotfix"], {
    cwd: ROOT, encoding: "utf8",
  });
  if (r.status !== 0) return [];
  return (r.stdout || "").split("\n").filter(Boolean).slice(0, 50);
}

function summariseFailures(telemetry, bypass, windowDays) {
  const failures = [];
  for (const rec of telemetry) {
    if (!rec.ts || !isWithin(rec.ts, windowDays)) continue;
    if (rec.event === "structural_test_fail" || rec.event === "precompletion_block" ||
        rec.event === "permission_denied" || rec.event === "userprompt_block") {
      failures.push({
        ts: rec.ts,
        event: rec.event,
        source: rec.source || rec.rule || "(unspecified)",
        detail: (rec.reason || rec.detail || rec.skill || "").slice(0, 200),
      });
    }
  }
  for (const rec of bypass) {
    if (!rec.ts || !isWithin(rec.ts, windowDays)) continue;
    failures.push({
      ts: rec.ts,
      event: "bypass",
      source: rec.rule || rec.bypass || "(unspecified)",
      detail: (rec.command || rec.file || "").slice(0, 200),
    });
  }
  failures.sort((a, b) => a.ts.localeCompare(b.ts));
  return failures.slice(-40);
}

function recurringPatterns(failures) {
  const counts = new Map();
  const samples = new Map();
  for (const f of failures) {
    const key = `${f.event}::${f.source}`;
    counts.set(key, (counts.get(key) || 0) + 1);
    if (!samples.has(key)) samples.set(key, f.ts);
  }
  const out = [];
  for (const [key, count] of counts) {
    if (count >= 2) out.push({ pattern: key, count, sample_ts: samples.get(key) });
  }
  out.sort((a, b) => b.count - a.count);
  return out.slice(0, 20);
}

function classify(failures, recurring) {
  const buckets = { context: 0, rule: 0, tool_skill: 0, architecture: 0, prompt: 0 };
  for (const f of failures) {
    if (f.event === "structural_test_fail") buckets.rule++;
    else if (f.event === "precompletion_block") buckets.rule++;
    else if (f.event === "permission_denied") buckets.context++;
    else if (f.event === "userprompt_block") buckets.context++;
    else if (f.event === "bypass") buckets.tool_skill++;
  }
  for (const r of recurring) {
    if (r.count >= 3 && r.pattern.startsWith("structural_test_fail::")) {
      buckets.architecture++;
    }
  }
  return buckets;
}

function fixTargets(buckets) {
  const out = [];
  if (buckets.rule > 0) {
    out.push({ file: ".harness/config.json", why: "structural rule lives here; consider tightening" });
    out.push({ file: ".harness/structural-baseline.json", why: "review whether baseline entries should drain" });
  }
  if (buckets.context > 0) {
    out.push({ file: ".harness/docs/golden-principles.md", why: "context gap surfaced via permission denials" });
    out.push({ file: "CLAUDE.md", why: "consider a pointer (not a paste) to relevant doc" });
  }
  if (buckets.tool_skill > 0) {
    out.push({ file: ".claude/skills/", why: "missing skill or wrong skill chosen — write or edit one" });
  }
  if (buckets.architecture > 0) {
    out.push({ file: ".harness/docs/adr/", why: "recurring violation suggests an ADR is needed" });
  }
  if (buckets.prompt > 0) {
    out.push({ file: ".claude/skills/<name>/SKILL.md", why: "prompt ambiguity led the agent astray" });
  }
  return out;
}

function main() {
  const { window: windowDays, out: outPath } = parseArgs(process.argv.slice(2));
  const telemetry = readJsonl(resolve(ROOT, ".harness/telemetry.jsonl"));
  const bypass = readJsonl(resolve(ROOT, ".harness/bypass.log"));
  const recentFailures = summariseFailures(telemetry, bypass, windowDays);
  const recurring = recurringPatterns(recentFailures);
  const classification = classify(recentFailures, recurring);
  const targets = fixTargets(classification);
  const fixCommits = gitLogFixes(windowDays);

  const payload = {
    window_days: windowDays,
    recent_failures: recentFailures,
    recurring_patterns: recurring,
    classification,
    fix_targets: targets,
    recent_fix_commits: fixCommits,
  };
  const text = JSON.stringify(payload, null, 2);
  if (outPath) writeFileSync(resolve(ROOT, outPath), text + "\n");
  else process.stdout.write(text + "\n");
}

main();
