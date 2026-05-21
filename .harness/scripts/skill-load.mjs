#!/usr/bin/env node
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
const name = process.argv[2];
if (!name) { console.error('Usage: node .harness/scripts/skill-load.mjs <skill-name>'); process.exit(1); }
const path = resolve(process.cwd(), `.claude/skills/${name}/SKILL.md`);
if (!existsSync(path)) { console.error(`Skill not found: ${name}`); process.exit(1); }
console.log(readFileSync(path, 'utf8'));
