#!/usr/bin/env node
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { spawnSync } from 'node:child_process';

const ROOT = process.cwd();
const args = process.argv.slice(2);
const title = args.find(a => !a.startsWith('--'));
if (!title) {
  console.error('Usage: node .claude/skills/create-story/create-story.mjs "Feature title" [--classification=normal] [--hours=2]');
  process.exit(1);
}
const opt = Object.fromEntries(args.filter(a => a.startsWith('--')).map(a => {
  const [k, v = 'true'] = a.slice(2).split('=');
  return [k, v];
}));
const classification = opt.classification || 'normal';
const hours = opt.hours || '2';
const today = new Date().toISOString().slice(0, 10);
const storiesDir = resolve(ROOT, '.harness/docs/stories');
mkdirSync(storiesDir, { recursive: true });

function slugify(s) {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 60) || 'story';
}
function nextFeatureId() {
  const listPath = resolve(ROOT, '.harness/feature_list.json');
  if (!existsSync(listPath)) return 'feature-1';
  try {
    const data = JSON.parse(readFileSync(listPath, 'utf8'));
    const arr = Array.isArray(data) ? data : data.features || [];
    const nums = arr.map(f => String(f.id || '').match(/^feature-(\d+)$/)?.[1]).filter(Boolean).map(Number);
    return `feature-${Math.max(0, ...nums) + 1}`;
  } catch { return 'feature-1'; }
}
function readFeatureListDoc() {
  const listPath = resolve(ROOT, '.harness/feature_list.json');
  if (!existsSync(listPath)) {
    return {
      isArray: false,
      doc: {
        $schema: './.harness/feature-list.schema.json',
        version: '0.1',
        project: ROOT.split('/').filter(Boolean).at(-1) || 'project',
        features: [],
      },
      features: [],
    };
  }
  try {
    const parsed = JSON.parse(readFileSync(listPath, 'utf8'));
    if (Array.isArray(parsed)) return { isArray: true, doc: parsed, features: parsed };
    return {
      isArray: false,
      doc: {
        $schema: parsed.$schema || './.harness/feature-list.schema.json',
        version: parsed.version || '0.1',
        project: parsed.project || ROOT.split('/').filter(Boolean).at(-1) || 'project',
        ...parsed,
        features: Array.isArray(parsed.features) ? parsed.features : [],
      },
      features: Array.isArray(parsed.features) ? parsed.features : [],
    };
  } catch {
    return { isArray: false, doc: { version: '0.1', features: [] }, features: [] };
  }
}
function writeFeatureListDoc(docInfo) {
  const listPath = resolve(ROOT, '.harness/feature_list.json');
  const payload = docInfo.isArray ? docInfo.features : { ...docInfo.doc, features: docInfo.features };
  writeFileSync(listPath, JSON.stringify(payload, null, 2) + '\n');
}
function recordProjectMemory({ id, title, classification, storyPath, reviewer }) {
  if (process.env.AHK_DISABLE_MEMORY === '1') return;
  const script = resolve(ROOT, '.harness/scripts/project-memory.mjs');
  if (!existsSync(script)) return;
  spawnSync(process.execPath, [
    script,
    'feature-created',
    '--feature-id', id,
    '--title', title,
    '--classification', classification,
    '--story-path', storyPath,
    '--status', 'story-draft',
    ...(reviewer ? ['--reviewer', reviewer] : []),
  ], { cwd: ROOT, stdio: 'ignore' });
}
const id = opt.id || nextFeatureId();
const storyPath = `.harness/docs/stories/${id}-${slugify(title)}.md`;
const absStory = resolve(ROOT, storyPath);
if (existsSync(absStory)) {
  console.error(`Story already exists: ${storyPath}`);
  process.exit(1);
}
const reviewer = classification === 'high-risk' ? (opt.reviewer || 'architecture-reviewer') : '';
const body = `# Story: ${title}

**ID:** ${id}  
**Classification:** ${classification}  
**Estimated Hours:** ${hours}  
**Status:** draft  
**Created:** ${today}  
**Assigned Reviewer:** ${reviewer || 'n/a'}

---

## Description

What needs to be built and why it matters.

---

## Acceptance Criteria

- [ ] **AC1:** Primary behavior is implemented and visible to the user.
- [ ] **AC2:** Error or empty state is handled at the system boundary.
- [ ] **AC3:** Existing behavior remains unchanged unless explicitly listed here.

---

## Test Expectations

### Unit Tests
- [ ] Core logic is covered where applicable.

### Integration Tests
- [ ] Main workflow is exercised end-to-end where practical.

### Manual Verification
- [ ] Golden path verified.
- [ ] Relevant edge case verified.

---

## Agent Work Units

- [ ] Inspect current implementation and affected files.
- [ ] Implement the smallest vertical slice.
- [ ] Run structural checks and targeted tests.
- [ ] Update feature tracking with proof.

---

## Dependencies

- **Blocks:** none
- **Blocked by:** none
- **Related ADRs:** ${classification === 'high-risk' ? 'required before implementation' : 'n/a'}

---

## Definition of Done

- [ ] All acceptance criteria met
- [ ] Tests or manual proof recorded
- [ ] No new structural test violations
- [ ] Feature list entry links this story
${classification === 'high-risk' ? '- [ ] ADR accepted and reviewer completed\n' : ''}`;
writeFileSync(absStory, body);

const featureDoc = readFeatureListDoc();
if (!featureDoc.features.some(f => f.id === id)) {
  featureDoc.features.push({
    id,
    title,
    passes: false,
    classification,
    estimatedHours: Number(hours),
    storyPath,
    status: 'story-draft',
    steps: [],
    updatedAt: new Date().toISOString(),
  });
  writeFeatureListDoc(featureDoc);
}
recordProjectMemory({ id, title, classification, storyPath, reviewer });
console.log(JSON.stringify({ id, title, classification, storyPath, status: 'created' }, null, 2));
