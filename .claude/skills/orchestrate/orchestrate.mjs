#!/usr/bin/env node
import { mkdir, writeFile, appendFile, readFile, access } from "node:fs/promises";
import { existsSync } from "node:fs";
import { resolve, join, isAbsolute } from "node:path";
import { spawn } from "node:child_process";

const PATTERNS = {
  pipeline: ["Explore current state", "Plan implementation", "Implement scoped change", "Review result"],
  fanout: ["Search implementation patterns", "Search tests and validation", "Search docs and user-facing behavior"],
  fanin: ["Collect candidate approaches", "Compare tradeoffs", "Recommend one path"],
  "expert-pool": ["Architecture review", "Security review", "Reliability review"],
  "red-team": ["Find failure modes", "Find unsafe assumptions", "Find missing verification"],
  supervisor: ["Define subtasks", "Assign owners", "Track blockers and completion"],
};

function parseArgs(argv) {
  const opts = {
    pattern: "fanout",
    run: false,
    transport: "claude-cli",
    maxConcurrency: 3,
    maxTurns: 8,
    failFast: true,
    outDir: null,
    permissionMode: "bypassPermissions",
    model: process.env.AHK_E2E_CLAUDE_MODEL || "",
    timeoutMs: 180_000,
    retries: 0,
    resume: null,
    cancel: null,
    validateRun: null,
    telemetry: true,
    mockDelayMs: 0,
    mockFail: new Set(),
    mockFailOnce: new Set(),
    specified: new Set(),
  };
  const taskParts = [];

  for (const arg of argv) {
    if (arg === "--run") opts.run = true;
    else if (arg === "--no-fail-fast") opts.failFast = false;
    else if (arg === "--no-telemetry") opts.telemetry = false;
    else if (arg.startsWith("--pattern=")) {
      opts.pattern = arg.slice("--pattern=".length);
      opts.specified.add("pattern");
    } else if (arg.startsWith("--transport=")) {
      opts.transport = arg.slice("--transport=".length);
      opts.specified.add("transport");
    } else if (arg.startsWith("--max-concurrency=")) {
      opts.maxConcurrency = parsePositiveInt(arg.slice("--max-concurrency=".length), opts.maxConcurrency);
      opts.specified.add("maxConcurrency");
    } else if (arg.startsWith("--max-turns=")) {
      opts.maxTurns = parsePositiveInt(arg.slice("--max-turns=".length), opts.maxTurns);
      opts.specified.add("maxTurns");
    }
    else if (arg.startsWith("--out-dir=")) opts.outDir = arg.slice("--out-dir=".length);
    else if (arg.startsWith("--permission-mode=")) {
      opts.permissionMode = arg.slice("--permission-mode=".length);
      opts.specified.add("permissionMode");
    } else if (arg.startsWith("--model=")) {
      opts.model = arg.slice("--model=".length);
      opts.specified.add("model");
    }
    else if (arg.startsWith("--timeout-ms=")) {
      opts.timeoutMs = parsePositiveInt(arg.slice("--timeout-ms=".length), opts.timeoutMs);
      opts.specified.add("timeoutMs");
    } else if (arg.startsWith("--retries=")) {
      opts.retries = parseNonNegativeInt(arg.slice("--retries=".length), opts.retries);
      opts.specified.add("retries");
    }
    else if (arg.startsWith("--resume=")) {
      opts.run = true;
      opts.resume = arg.slice("--resume=".length);
    } else if (arg.startsWith("--cancel=")) {
      opts.cancel = arg.slice("--cancel=".length);
    } else if (arg.startsWith("--validate-run=")) {
      opts.validateRun = arg.slice("--validate-run=".length);
    } else if (arg.startsWith("--mock-delay-ms=")) {
      opts.mockDelayMs = parseNonNegativeInt(arg.slice("--mock-delay-ms=".length), opts.mockDelayMs);
    } else if (arg.startsWith("--mock-fail=")) {
      opts.mockFail = csvSet(arg.slice("--mock-fail=".length));
    } else if (arg.startsWith("--mock-fail-once=")) {
      opts.mockFailOnce = csvSet(arg.slice("--mock-fail-once=".length));
    }
    else if (!arg.startsWith("--")) taskParts.push(arg);
  }

  return { task: taskParts.join(" ").trim(), opts };
}

function usage() {
  console.error('Usage: node .claude/skills/orchestrate/orchestrate.mjs "task" [--pattern=fanout] [--run] [--transport=claude-cli|mock]');
  console.error("       node .claude/skills/orchestrate/orchestrate.mjs --resume=<run-id-or-dir>");
  console.error("       node .claude/skills/orchestrate/orchestrate.mjs --validate-run=<run-id-or-dir>");
  console.error("       node .claude/skills/orchestrate/orchestrate.mjs --cancel=<run-id-or-dir>");
}

function parsePositiveInt(value, fallback) {
  const n = Number.parseInt(value, 10);
  return Number.isFinite(n) && n > 0 ? n : fallback;
}

function parseNonNegativeInt(value, fallback) {
  const n = Number.parseInt(value, 10);
  return Number.isFinite(n) && n >= 0 ? n : fallback;
}

function csvSet(value) {
  return new Set(String(value || "").split(",").map((item) => item.trim()).filter(Boolean));
}

function timestamp() {
  return new Date().toISOString().replace(/[:.]/g, "-");
}

function stepsFor(pattern) {
  return PATTERNS[pattern] || PATTERNS.fanout;
}

function agentPrompt(task, pattern, step, index) {
  return `You are agent ${index + 1} in an agent-harness-kit ${pattern} orchestration.

Task:
${task}

Your bounded slice:
${step}

Rules:
- Stay inside this slice.
- Prefer read-only inspection unless this prompt explicitly asks for implementation.
- Report concise findings, critical files, risks, and recommended next action.
- Include verification evidence when you run commands.
`;
}

function createManifest(task, pattern, opts, runId, outDir) {
  const steps = stepsFor(pattern);
  return {
    schemaVersion: 1,
    runId,
    task,
    pattern,
    transport: opts.transport,
    maxConcurrency: opts.maxConcurrency,
    maxTurns: opts.maxTurns,
    timeoutMs: opts.timeoutMs,
    retries: opts.retries,
    permissionMode: opts.permissionMode,
    model: opts.model,
    failFast: opts.failFast,
    outDir,
    createdAt: new Date().toISOString(),
    agents: steps.map((step, index) => ({
      id: `agent-${index + 1}`,
      index,
      step,
      prompt: agentPrompt(task, pattern, step, index),
    })),
  };
}

async function writePacket(task, pattern) {
  const dir = resolve(process.cwd(), ".harness/docs/orchestration");
  await mkdir(dir, { recursive: true });
  const created = new Date().toISOString();
  const path = `.harness/docs/orchestration/${timestamp()}-${pattern}.md`;
  const manifest = createManifest(task, pattern, { transport: "packet", maxConcurrency: 0, failFast: true }, "packet", "");
  const body = `# Orchestration Packet: ${pattern}

**Task:** ${task}
**Created:** ${created}
**Synthesis owner:** main agent

## Agent prompts

${manifest.agents.map((agent) => `### ${agent.id}: ${agent.step}

${agent.prompt}
`).join("\n")}
## Completion checklist

${manifest.agents.map((agent) => `- [ ] ${agent.step}`).join("\n")}
- [ ] Main agent synthesizes results and chooses next step
`;
  await writeFile(resolve(process.cwd(), path), body);
  return { pattern, agents: manifest.agents.length, path, task };
}

function sleep(ms) {
  return new Promise((resolveSleep) => setTimeout(resolveSleep, ms));
}

async function runMockAgent(agent, transcriptPath, opts, attempt) {
  if (opts.mockDelayMs > 0) await sleep(opts.mockDelayMs);
  const shouldFail = opts.mockFail.has(agent.id) || (attempt === 1 && opts.mockFailOnce.has(agent.id));
  const event = {
    type: "result",
    subtype: "mock",
    agent_id: agent.id,
    total_cost_usd: shouldFail ? 0.0002 : 0.0001,
    usage: {
      input_tokens: agent.prompt.length,
      output_tokens: 64,
      cache_creation_input_tokens: 8,
      cache_read_input_tokens: 16,
    },
    is_error: shouldFail,
    result: shouldFail ? `Mock failure for ${agent.step}` : `Mock result for ${agent.step}`,
  };
  await writeFile(transcriptPath, JSON.stringify(event) + "\n");
  return { exitCode: shouldFail ? 1 : 0, events: [event], stderr: shouldFail ? "mock failure" : "", output: event.result };
}

async function runClaudeAgent(agent, transcriptPath, opts) {
  return await new Promise((resolveRun) => {
    let timedOut = false;
    const proc = spawn(
      "claude",
      [
        "-p",
        agent.prompt,
        "--output-format",
        "stream-json",
        "--verbose",
        ...(opts.model ? ["--model", opts.model] : []),
        "--permission-mode",
        opts.permissionMode,
        "--max-turns",
        String(opts.maxTurns),
      ],
      { cwd: process.cwd(), stdio: ["ignore", "pipe", "pipe"] },
    );

    const timeout = setTimeout(() => {
      timedOut = true;
      proc.kill("SIGTERM");
      setTimeout(() => {
        if (!proc.killed) proc.kill("SIGKILL");
      }, 2_000).unref();
    }, opts.timeoutMs);
    timeout.unref();

    const events = [];
    let stderr = "";
    let buffer = "";
    proc.stdout.on("data", (chunk) => {
      buffer += chunk.toString();
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const event = JSON.parse(line);
          events.push(event);
          appendFile(transcriptPath, JSON.stringify(event) + "\n");
        } catch {
          appendFile(transcriptPath, JSON.stringify({ type: "raw", line }) + "\n");
        }
      }
    });
    proc.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    proc.on("exit", (code) => {
      clearTimeout(timeout);
      const result = [...events].reverse().find((event) => event.type === "result") || {};
      resolveRun({
        exitCode: timedOut ? 124 : code ?? 1,
        events,
        stderr: timedOut ? `${stderr}\ntimeout after ${opts.timeoutMs}ms`.trim() : stderr,
        output: result.result || "",
        timedOut,
      });
    });
  });
}

function summarizeRun(run) {
  const result = [...run.events].reverse().find((event) => event.type === "result") || {};
  const usage = result.usage || {};
  const inputTokens = usage.input_tokens || 0;
  const outputTokens = usage.output_tokens || 0;
  const cacheCreationInputTokens = usage.cache_creation_input_tokens || 0;
  const cacheReadInputTokens = usage.cache_read_input_tokens || 0;
  return {
    model: result.model || run.model || "",
    costUSD: result.total_cost_usd || 0,
    inputTokens,
    outputTokens,
    cacheCreationInputTokens,
    cacheReadInputTokens,
    totalTokens: inputTokens + outputTokens + cacheCreationInputTokens + cacheReadInputTokens,
    isError: Boolean(result.is_error) || run.exitCode !== 0,
    error: run.timedOut ? `timeout after ${run.timeoutMs || 0}ms` : result.error || "",
  };
}

async function runAttempt(agent, opts, transcriptDir, attempt) {
  const transcriptPath = join(transcriptDir, attempt === 1 ? `${agent.id}.jsonl` : `${agent.id}.attempt-${attempt}.jsonl`);
  const startedAt = Date.now();
  const work = opts.transport === "mock"
    ? runMockAgent(agent, transcriptPath, opts, attempt)
    : runClaudeAgent(agent, transcriptPath, opts);
  const run = await withTimeout(work, opts.timeoutMs, transcriptPath);
  run.timeoutMs = opts.timeoutMs;
  const metrics = summarizeRun(run);
  return {
    attempt,
    agentId: agent.id,
    step: agent.step,
    status: metrics.isError ? "failed" : "passed",
    transcriptPath,
    durationMs: Date.now() - startedAt,
    stderr: run.stderr,
    output: run.output,
    ...metrics,
  };
}

async function withTimeout(promise, timeoutMs, transcriptPath) {
  let timeout;
  const timeoutPromise = new Promise((resolveTimeout) => {
    timeout = setTimeout(async () => {
      const event = {
        type: "result",
        subtype: "timeout",
        is_error: true,
        total_cost_usd: 0,
        usage: {},
        result: `timeout after ${timeoutMs}ms`,
      };
      await appendFile(transcriptPath, JSON.stringify(event) + "\n").catch(() => {});
      resolveTimeout({
        exitCode: 124,
        events: [event],
        stderr: `timeout after ${timeoutMs}ms`,
        output: "",
        timedOut: true,
      });
    }, timeoutMs);
    timeout.unref();
  });
  const result = await Promise.race([promise, timeoutPromise]);
  clearTimeout(timeout);
  return result;
}

async function runAgent(agent, opts, transcriptDir) {
  const attempts = [];
  for (let attempt = 1; attempt <= opts.retries + 1; attempt += 1) {
    const result = await runAttempt(agent, opts, transcriptDir, attempt);
    attempts.push({
      attempt,
      status: result.status,
      transcriptPath: result.transcriptPath,
      durationMs: result.durationMs,
      error: result.error || result.stderr || "",
    });
    if (result.status === "passed" || attempt > opts.retries) {
      return {
        ...result,
        attempts,
        retries: attempt - 1,
      };
    }
  }
  throw new Error(`unreachable retry loop for ${agent.id}`);
}

async function runWithLimit(items, limit, worker, failFast) {
  const results = [];
  let cursor = 0;
  let failed = false;

  async function next() {
    if (failed && failFast) return;
    const current = cursor;
    cursor += 1;
    if (current >= items.length) return;
    const result = await worker(items[current]);
    results[current] = result;
    if (result.status === "failed") failed = true;
    await next();
  }

  const workers = Array.from({ length: Math.max(1, Math.min(limit, items.length)) }, () => next());
  await Promise.all(workers);
  return results.filter(Boolean);
}

function resolveRunDir(value) {
  if (!value) return null;
  if (isAbsolute(value) || value.startsWith(".") || value.includes("/")) {
    return resolve(process.cwd(), value);
  }
  return resolve(process.cwd(), ".harness/orchestration", value);
}

async function readJson(path) {
  return JSON.parse(await readFile(path, "utf8"));
}

async function pathExists(path) {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

async function cancelRun(value) {
  const outDir = resolveRunDir(value);
  await mkdir(outDir, { recursive: true });
  const cancelledAt = new Date().toISOString();
  await writeFile(join(outDir, "CANCELLED"), JSON.stringify({ cancelledAt }, null, 2) + "\n");
  return { status: "cancelled", outDir, cancelledAt };
}

async function isCancelled(outDir) {
  return await pathExists(join(outDir, "CANCELLED"));
}

async function loadPreviousSummary(outDir) {
  const path = join(outDir, "summary.json");
  if (!(await pathExists(path))) return null;
  return await readJson(path);
}

function validateManifest(manifest) {
  const errors = [];
  if (!manifest || typeof manifest !== "object") errors.push("manifest must be an object");
  if (manifest?.schemaVersion !== 1) errors.push("manifest.schemaVersion must be 1");
  if (!manifest?.runId) errors.push("manifest.runId is required");
  if (!manifest?.task) errors.push("manifest.task is required");
  if (!PATTERNS[manifest?.pattern]) errors.push(`manifest.pattern is invalid: ${manifest?.pattern}`);
  if (!Array.isArray(manifest?.agents) || manifest.agents.length === 0) errors.push("manifest.agents must be a non-empty array");
  for (const [index, agent] of (manifest?.agents || []).entries()) {
    if (!agent.id) errors.push(`manifest.agents[${index}].id is required`);
    if (!agent.step) errors.push(`manifest.agents[${index}].step is required`);
    if (!agent.prompt) errors.push(`manifest.agents[${index}].prompt is required`);
  }
  return errors;
}

function validateSummary(summary, manifest) {
  const errors = [];
  if (!summary || typeof summary !== "object") errors.push("summary must be an object");
  if (summary?.schemaVersion !== 1) errors.push("summary.schemaVersion must be 1");
  if (manifest && summary?.runId !== manifest.runId) errors.push("summary.runId must match manifest.runId");
  if (!["passed", "failed", "cancelled"].includes(summary?.status)) errors.push("summary.status must be passed, failed, or cancelled");
  if (!Array.isArray(summary?.results)) errors.push("summary.results must be an array");
  for (const [index, result] of (summary?.results || []).entries()) {
    if (!result.agentId) errors.push(`summary.results[${index}].agentId is required`);
    if (!["passed", "failed", "skipped"].includes(result.status)) errors.push(`summary.results[${index}].status is invalid`);
    if (!result.transcriptPath) errors.push(`summary.results[${index}].transcriptPath is required`);
  }
  return errors;
}

async function validateTranscript(path) {
  const errors = [];
  const warnings = [];
  if (!(await pathExists(path))) return { errors: [`transcript missing: ${path}`], warnings };
  const text = await readFile(path, "utf8");
  const lines = text.split("\n").filter(Boolean);
  if (lines.length === 0) errors.push(`transcript empty: ${path}`);
  for (const [index, line] of lines.entries()) {
    try {
      const event = JSON.parse(line);
      if (!event || typeof event !== "object") errors.push(`${path}:${index + 1} event must be an object`);
      if (!event.type) errors.push(`${path}:${index + 1} event.type is required`);
    } catch {
      errors.push(`${path}:${index + 1} invalid JSON event`);
    }
  }
  return { errors, warnings };
}

async function validateRunDir(value) {
  const outDir = resolveRunDir(value);
  const errors = [];
  const warnings = [];
  const manifestPath = join(outDir, "manifest.json");
  const summaryPath = join(outDir, "summary.json");

  if (!(await pathExists(manifestPath))) errors.push(`missing manifest.json in ${outDir}`);
  if (!(await pathExists(summaryPath))) errors.push(`missing summary.json in ${outDir}`);
  if (errors.length > 0) return { status: "failed", outDir, errors, warnings };

  const manifest = await readJson(manifestPath);
  const summary = await readJson(summaryPath);
  errors.push(...validateManifest(manifest));
  errors.push(...validateSummary(summary, manifest));
  for (const result of summary.results || []) {
    const transcript = await validateTranscript(result.transcriptPath);
    errors.push(...transcript.errors);
    warnings.push(...transcript.warnings);
  }
  return {
    status: errors.length === 0 ? "passed" : "failed",
    outDir,
    errors,
    warnings,
    manifestAgents: manifest.agents?.length || 0,
    summaryResults: summary.results?.length || 0,
  };
}

function renderSummaryMarkdown(summary) {
  return `# Orchestration Run: ${summary.pattern}

Task: ${summary.task}

Status: ${summary.status}
Agents: ${summary.passed}/${summary.total} passed
Cost: $${summary.totalCostUSD.toFixed(4)}
Tokens: ${summary.totalTokens}
Cache read/write: ${summary.cacheReadInputTokens}/${summary.cacheCreationInputTokens}
Retries: ${summary.totalRetries}
Skipped on resume: ${summary.skipped}

| Agent | Step | Status | Cost | Tokens | Transcript |
| --- | --- | --- | ---: | ---: | --- |
${summary.results.map((r) => `| ${r.agentId} | ${r.step.replaceAll("|", "\\|")} | ${r.status} | $${r.costUSD.toFixed(4)} | ${r.totalTokens} | ${r.transcriptPath} |`).join("\n")}
`;
}

async function appendTelemetry(manifest, summary) {
  const telemetryPath = resolve(process.cwd(), ".harness/telemetry.jsonl");
  await mkdir(resolve(process.cwd(), ".harness"), { recursive: true });
  const rows = [];
  const now = new Date().toISOString();
  rows.push({
    schemaVersion: 1,
    ts: manifest.createdAt || now,
    event: "skill_invoked",
    session_id: manifest.runId,
    skill: "orchestrate",
    args: `--pattern=${manifest.pattern} --run`,
    orchestration_run_id: manifest.runId,
  });
  for (const result of summary.results) {
    if (result.status === "skipped") continue;
    const end = new Date().toISOString();
    const start = new Date(Date.now() - (result.durationMs || 0)).toISOString();
    rows.push({
      schemaVersion: 1,
      ts: start,
      event: "eval_run",
      session_id: manifest.runId,
      taskId: result.agentId,
      task_id: result.agentId,
      orchestration_run_id: manifest.runId,
      orchestration_step: result.step,
      passed: result.status === "passed",
    });
    rows.push({
      schemaVersion: 1,
      ts: end,
      event: "provider_call",
      session_id: manifest.runId,
      provider: manifest.transport === "mock" ? "mock" : "claude",
      model: result.model || (manifest.transport === "mock" ? "mock" : ""),
      skill: "orchestrate",
      task_id: result.agentId,
      orchestration_run_id: manifest.runId,
      orchestration_step: result.step,
      input_tokens: result.inputTokens || 0,
      output_tokens: result.outputTokens || 0,
      cache_creation_input_tokens: result.cacheCreationInputTokens || 0,
      cache_read_input_tokens: result.cacheReadInputTokens || 0,
      cost_usd: result.costUSD || 0,
      start_ts: start,
      end_ts: end,
      error: result.status === "failed" ? result.error || result.stderr || "failed" : "",
    });
  }
  rows.push({
    schemaVersion: 1,
    ts: now,
    event: "orchestration_summary",
    session_id: manifest.runId,
    skill: "orchestrate",
    task_id: manifest.runId,
    orchestration_run_id: manifest.runId,
    status: summary.status,
    total: summary.total,
    completed: summary.completed,
    passed: summary.passed,
    failed: summary.failed,
    total_cost_usd: summary.totalCostUSD,
    total_tokens: summary.totalTokens,
  });
  await appendFile(telemetryPath, rows.map(JSON.stringify).join("\n") + "\n");
  return telemetryPath;
}

async function runOrchestration(task, opts) {
  let pattern = PATTERNS[opts.pattern] ? opts.pattern : "fanout";
  let runId = `${timestamp()}-${pattern}`;
  let outDir = resolve(process.cwd(), opts.outDir || `.harness/orchestration/${runId}`);
  let manifest;
  let previousSummary = null;

  if (opts.resume) {
    outDir = resolveRunDir(opts.resume);
    manifest = await readJson(join(outDir, "manifest.json"));
    const manifestErrors = validateManifest(manifest);
    if (manifestErrors.length > 0) {
      throw new Error(`Cannot resume invalid manifest:\n${manifestErrors.join("\n")}`);
    }
    previousSummary = await loadPreviousSummary(outDir);
    pattern = manifest.pattern;
    runId = manifest.runId;
    task = task || manifest.task;
    opts = {
      ...opts,
      pattern,
      transport: opts.specified.has("transport") ? opts.transport : manifest.transport,
      maxConcurrency: opts.specified.has("maxConcurrency") ? opts.maxConcurrency : manifest.maxConcurrency,
      maxTurns: opts.specified.has("maxTurns") ? opts.maxTurns : manifest.maxTurns,
      timeoutMs: opts.specified.has("timeoutMs") ? opts.timeoutMs : manifest.timeoutMs,
      retries: opts.specified.has("retries") ? opts.retries : manifest.retries ?? 0,
      failFast: manifest.failFast,
      permissionMode: opts.specified.has("permissionMode") ? opts.permissionMode : manifest.permissionMode,
      model: opts.specified.has("model") ? opts.model : manifest.model || opts.model,
    };
  }

  const transcriptDir = join(outDir, "transcripts");
  await mkdir(transcriptDir, { recursive: true });

  if (!manifest) {
    manifest = createManifest(task, pattern, opts, runId, outDir);
    await writeFile(join(outDir, "manifest.json"), JSON.stringify(manifest, null, 2) + "\n");
  }

  const previousByAgent = new Map();
  for (const result of previousSummary?.results || []) {
    if (result.status === "passed") previousByAgent.set(result.agentId, { ...result, status: "skipped", skippedReason: "passed in previous run" });
  }
  const pendingAgents = manifest.agents.filter((agent) => !previousByAgent.has(agent.id));
  const cancelledBeforeRun = await isCancelled(outDir);

  const freshResults = cancelledBeforeRun
    ? []
    : await runWithLimit(
      pendingAgents,
      opts.maxConcurrency,
      async (agent) => {
        if (await isCancelled(outDir)) {
          return {
            agentId: agent.id,
            step: agent.step,
            status: "failed",
            transcriptPath: join(transcriptDir, `${agent.id}.jsonl`),
            durationMs: 0,
            stderr: "run cancelled",
            output: "",
            model: "",
            costUSD: 0,
            inputTokens: 0,
            outputTokens: 0,
            cacheCreationInputTokens: 0,
            cacheReadInputTokens: 0,
            totalTokens: 0,
            isError: true,
            error: "run cancelled",
            attempts: [],
            retries: 0,
          };
        }
        return runAgent(agent, opts, transcriptDir);
      },
      opts.failFast,
    );

  const freshByAgent = new Map(freshResults.map((result) => [result.agentId, result]));
  const results = manifest.agents
    .map((agent) => freshByAgent.get(agent.id) || previousByAgent.get(agent.id))
    .filter(Boolean);

  const passed = results.filter((result) => result.status === "passed" || result.status === "skipped").length;
  const cancelled = cancelledBeforeRun || await isCancelled(outDir);
  const summary = {
    schemaVersion: 1,
    runId,
    task,
    pattern,
    status: cancelled ? "cancelled" : passed === manifest.agents.length ? "passed" : "failed",
    total: manifest.agents.length,
    completed: results.length,
    passed: results.filter((result) => result.status === "passed" || result.status === "skipped").length,
    failed: results.filter((result) => result.status === "failed").length,
    skipped: results.filter((result) => result.status === "skipped").length,
    pending: manifest.agents.length - results.length,
    totalCostUSD: results.reduce((sum, result) => sum + result.costUSD, 0),
    totalTokens: results.reduce((sum, result) => sum + result.totalTokens, 0),
    cacheCreationInputTokens: results.reduce((sum, result) => sum + result.cacheCreationInputTokens, 0),
    cacheReadInputTokens: results.reduce((sum, result) => sum + result.cacheReadInputTokens, 0),
    totalRetries: results.reduce((sum, result) => sum + (result.retries || 0), 0),
    maxConcurrency: opts.maxConcurrency,
    timeoutMs: opts.timeoutMs,
    retries: opts.retries,
    failFast: opts.failFast,
    resumed: Boolean(opts.resume),
    outDir,
    results,
  };

  await writeFile(join(outDir, "summary.json"), JSON.stringify(summary, null, 2) + "\n");
  await writeFile(join(outDir, "summary.md"), renderSummaryMarkdown(summary));
  if (opts.telemetry) {
    summary.telemetryPath = await appendTelemetry(manifest, summary);
    await writeFile(join(outDir, "summary.json"), JSON.stringify(summary, null, 2) + "\n");
  }
  const validation = await validateRunDir(outDir);
  summary.validation = validation;
  await writeFile(join(outDir, "summary.json"), JSON.stringify(summary, null, 2) + "\n");
  return summary;
}

const { task, opts } = parseArgs(process.argv.slice(2));
if (opts.cancel) {
  const payload = await cancelRun(opts.cancel);
  console.log(JSON.stringify(payload, null, 2));
  process.exit(0);
}
if (opts.validateRun) {
  const validation = await validateRunDir(opts.validateRun);
  console.log(JSON.stringify(validation, null, 2));
  process.exit(validation.status === "passed" ? 0 : 1);
}
if (!task && !opts.resume) {
  usage();
  process.exit(1);
}

const pattern = PATTERNS[opts.pattern] ? opts.pattern : "fanout";
if (!opts.run) {
  const packet = await writePacket(task, pattern);
  console.log(JSON.stringify(packet, null, 2));
} else {
  const summary = await runOrchestration(task, { ...opts, pattern });
  console.log(JSON.stringify({
    runId: summary.runId,
    status: summary.status,
    pattern: summary.pattern,
    completed: summary.completed,
    total: summary.total,
    passed: summary.passed,
    failed: summary.failed,
    skipped: summary.skipped,
    pending: summary.pending,
    totalCostUSD: summary.totalCostUSD,
    totalTokens: summary.totalTokens,
    validation: summary.validation.status,
    outDir: summary.outDir,
  }, null, 2));
  if (summary.status !== "passed") process.exit(1);
}
