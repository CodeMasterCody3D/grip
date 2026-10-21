import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { setupGripEvents, controllerCommand, registryPath } from '../plugins/grip-events.mjs';

test('controller resolves from the installed plugin and accepts explicit interpreter/path overrides', () => {
  const old = { ...process.env };
  try {
    delete process.env.GRIP_PYTHON;
    delete process.env.GRIP_CONTROLLER;
    assert.deepEqual(controllerCommand(), ['python3', fileURLToPath(new URL('../grip.py', import.meta.url))]);
    process.env.GRIP_PYTHON = 'custom-python';
    process.env.GRIP_CONTROLLER = 'custom-controller';
    assert.deepEqual(controllerCommand(), ['custom-python', 'custom-controller']);
    assert.deepEqual(controllerCommand({ python: 'explicit-python', controllerPath: 'explicit-controller' }),
      ['explicit-python', 'explicit-controller']);
  } finally { process.env = old; }
});

test('registry respects the current user cache, XDG and explicit overrides', () => {
  const old = { ...process.env };
  try {
    delete process.env.GRIP_CACHE_DIR;
    process.env.XDG_CACHE_HOME = join(tmpdir(), 'different user cache');
    assert.equal(registryPath(), resolve(process.env.XDG_CACHE_HOME, 'grip/bindings.json'));
    process.env.GRIP_CACHE_DIR = join(tmpdir(), 'selected grip cache');
    assert.equal(registryPath(), join(process.env.GRIP_CACHE_DIR, 'bindings.json'));
    assert.equal(registryPath({ registry: 'selected-registry' }), 'selected-registry');
  } finally { process.env = old; }
});

function stream(signal) {
  const queue = [];
  let wake;
  signal.addEventListener('abort', () => wake?.(), { once: true });
  return { push: value => { queue.push(value); wake?.(); },
    async *[Symbol.asyncIterator]() {
      while (!signal.aborted) {
        if (!queue.length) await new Promise(resolve => { wake = resolve; });
        while (queue.length) yield queue.shift();
      }
    } };
}

test('actual bridge registers current API hooks, filters sessions and emits metadata only', async () => {
  const root = await mkdtemp(join(tmpdir(), 'grip-hook-'));
  try {
    const registry = join(root, 'bindings.json');
    await writeFile(registry, JSON.stringify({ sessions: { actual: { state_path: '/fixture/state.json' } } }));
    const hooks = {}, sent = [];
    let events, disposals = 0;
    const ctx = { tool: { hook: async (name, fn) => { hooks[name] = fn; return { dispose: async () => disposals++ }; } },
      session: { hook: async (name, fn) => { hooks[name] = fn; return { dispose: async () => disposals++ }; } },
      event: { subscribe: ({ signal }) => (events = stream(signal)) } };
    let wake;
    const cleanup = await setupGripEvents(ctx, { registry, send: async (state, args) => { sent.push({ state, args }); wake?.(); } });
    assert(sent.some(r => r.args.includes('hook_loaded')));
    await hooks['execute.before']({ sessionID: 'foreign', id: 'foreign-tool', agent: 'build', input: 'PRIVATE' });
    assert.equal(sent.length, 1);
    await hooks['execute.before']({ sessionID: 'actual', id: 'tool-a', agent: 'build', input: 'PRIVATE' });
    await hooks['execute.after']({ sessionID: 'actual', id: 'tool-a', agent: 'build', result: { content: 'PRIVATE-OUTPUT' } });
    await hooks.context({ sessionID: 'actual', agent: 'plan', messages: 'PRIVATE-CONTEXT' });
    assert(sent.some(r => r.args.includes('tool_start')));
    assert(sent.some(r => r.args.includes('tool_end')));
    assert(sent.some(r => r.args.includes('plan')));
    const observed = new Promise(resolve => { wake = () => { if (sent.some(r => r.args.includes('turn_end'))) resolve(); }; });
    events.push({ type: 'session.execution.succeeded', id: 'real-event', created: 1234, data: { sessionID: 'actual' } });
    await observed;
    assert(sent.find(r => r.args.includes('turn_end')).args.includes('1234'));
    const idle = new Promise(resolve => { wake = () => { if (sent.some(r => r.args.includes('idle'))) resolve(); }; });
    events.push({ type: 'session.idle', id: 'foreign-idle', properties: { sessionID: 'foreign' } });
    events.push({ type: 'session.idle', id: 'idle', properties: { sessionID: 'actual', text: 'PRIVATE' } });
    await idle;
    assert.equal(sent.filter(r => r.args.includes('idle')).length, 1);
    const stopped = new Promise(resolve => { wake = () => { if (sent.some(r => r.args.includes('interrupted'))) resolve(); }; });
    events.push({ type: 'session.execution.interrupted', id: 'stop', properties: { sessionID: 'actual', reason: 'user' } });
    await stopped;
    assert(!JSON.stringify(sent).includes('PRIVATE'));
    await cleanup();
    assert.equal(disposals, 3);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test('unknown agent is fail-closed planning, and registry absence is inert', async () => {
  const root = await mkdtemp(join(tmpdir(), 'grip-hook-'));
  try {
    const registry = join(root, 'bindings.json');
    let context, sent = [];
    const ctx = { tool: { hook: async () => ({ dispose() {} }) },
      session: { hook: async (_, fn) => { context = fn; return { dispose() {} }; } },
      event: { subscribe: ({ signal }) => stream(signal) } };
    const cleanup = await setupGripEvents(ctx, { registry, send: async (_, args) => sent.push(args) });
    await context({ sessionID: 'actual', agent: 'build' });
    assert.equal(sent.length, 0);
    await writeFile(registry, JSON.stringify({ sessions: { actual: { state_path: '/fixture/state.json' } } }));
    await context({ sessionID: 'actual', agent: 'custom-unselected-agent' });
    assert(sent[0].includes('plan'));
    await cleanup();
  } finally { await rm(root, { recursive: true, force: true }); }
});
