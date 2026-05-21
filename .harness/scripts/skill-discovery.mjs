#!/usr/bin/env node
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { resolve, join } from 'node:path';
const ROOT = process.cwd();
const skillsDir = resolve(ROOT, '.claude/skills');
const outPath = resolve(ROOT, '.harness/skill-index.json');
function parseFrontmatter(text) {
  const m = text.match(/^---\n([\s\S]*?)\n---/);
  if (!m) return {};
  return Object.fromEntries(m[1].split('\n').map(l => l.match(/^([^:]+):\s*(.*)$/)).filter(Boolean).map(([,k,v]) => [k.trim(), v.trim()]));
}
const skills = existsSync(skillsDir) ? readdirSync(skillsDir, { withFileTypes: true }).filter(e=>e.isDirectory()).map(e => {
  const skillPath = join(skillsDir, e.name, 'SKILL.md');
  const text = existsSync(skillPath) ? readFileSync(skillPath, 'utf8') : '';
  const fm = parseFrontmatter(text);
  return { name: fm.name || e.name, description: fm.description || '', path: `.claude/skills/${e.name}/SKILL.md`, loaded: false };
}).sort((a,b)=>a.name.localeCompare(b.name)) : [];
mkdirSync(resolve(ROOT, '.harness'), { recursive: true });
writeFileSync(outPath, JSON.stringify({ generatedAt: new Date().toISOString(), count: skills.length, skills }, null, 2) + '\n');
console.log(JSON.stringify({ outPath, count: skills.length }, null, 2));
