import { cpSync, existsSync, mkdirSync, readFileSync, rmSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const source = resolve(root, 'public');
const output = resolve(root, 'dist');
const required = ['index.html', 'app.js', 'styles.css', 'data/current.json'];
for (const file of required) {
  if (!existsSync(resolve(source, file))) throw new Error(`Missing public asset: ${file}`);
}
const data = JSON.parse(readFileSync(resolve(source, 'data/current.json'), 'utf8'));
if (!Array.isArray(data.candidates)) throw new Error('Invalid scanner data');
rmSync(output, { recursive: true, force: true });
mkdirSync(output, { recursive: true });
cpSync(source, output, { recursive: true });
for (const file of required) {
  if (!existsSync(resolve(output, file))) throw new Error(`Missing build asset: ${file}`);
}
console.log(`Static website ready: ${required.join(', ')}; ${data.candidates.length} patterns as of ${data.as_of}`);
