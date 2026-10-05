import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { test } from 'node:test';

const webRequire = createRequire(resolve('apps/web/package.json'));
const configRequire = createRequire(webRequire.resolve('eslint-config-next'));
const pluginRequire = createRequire(configRequire.resolve('@next/eslint-plugin-next'));
const globRequire = createRequire(pluginRequire.resolve('fast-glob'));
const matchRequire = createRequire(globRequire.resolve('micromatch'));
const braces = matchRequire('braces');

test('the ESLint dependency rejects deep patterns before recursive traversal', () => {
  const pattern = '{'.repeat(4000) + 'a,b' + '}'.repeat(4000);
  for (const operation of ['parse', 'compile', 'expand', 'stringify']) {
    assert.throws(() => braces[operation](pattern), {
      name: 'SyntaxError',
      message: 'Brace nesting exceeds 64 levels',
    });
  }
});

test('recursive walkers also bound externally supplied ASTs', () => {
  for (const operation of ['compile', 'expand', 'stringify']) {
    let ast = { type: 'text', value: 'a' };
    for (let depth = 0; depth < 80; depth += 1) ast = { type: 'root', nodes: [ast] };
    assert.throws(() => braces[operation](ast), {
      name: 'SyntaxError',
      message: 'Brace nesting exceeds 64 levels',
    });
  }
});

test('normal source globs, nested alternatives and ranges remain supported', () => {
  assert.deepEqual(braces.expand('src/{app,components}/**/*.{ts,tsx}'), [
    'src/app/**/*.ts',
    'src/app/**/*.tsx',
    'src/components/**/*.ts',
    'src/components/**/*.tsx',
  ]);
  assert.deepEqual(braces.expand('{a,{b,c}}'), ['a', 'b', 'c']);
  assert.deepEqual(braces.expand('{1..3}'), ['1', '2', '3']);
});
