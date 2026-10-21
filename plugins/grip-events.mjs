// Metadata only. This bridge never prompts, creates sessions, or touches model data.
import { readFile } from 'node:fs/promises';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { homedir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const run = promisify(execFile);

export function controllerCommand(options = {}) {
  return [options.python ?? process.env.GRIP_PYTHON ?? 'python3',
    options.controllerPath ?? process.env.GRIP_CONTROLLER ?? fileURLToPath(new URL('../grip.py', import.meta.url))];
}

export function registryPath(options = {}) {
  const cache = process.env.GRIP_CACHE_DIR
    ? resolve(process.env.GRIP_CACHE_DIR)
    : resolve(process.env.XDG_CACHE_HOME ?? join(homedir(), '.cache'), 'grip');
  return options.registry ?? join(cache, 'bindings.json');
}

export async function setupGripEvents(ctx, options = {}) {
  const registry = registryPath(options);
  const send = options.send ?? (async (state, args) => {
    const [python, controller] = controllerCommand(options);
    await run(python, [controller, '--state', state, 'event', ...args], { timeout: 10000 });
  });
  const registrations = [];
  const abort = new AbortController();
  async function emit(sessionID, kind, extra = {}) {
    try {
      const bindings = JSON.parse(await readFile(registry, 'utf8'));
      const binding = bindings.sessions?.[sessionID];
      if (!binding) return;
      const args = ['--session-id', sessionID, '--kind', kind];
      if (extra.callID) args.push('--call-id', extra.callID);
      if (extra.agent) args.push('--agent', extra.agent === 'build' ? 'build' : 'plan');
       if (extra.eventID) args.push('--event-id', extra.eventID);
       if (Number.isFinite(extra.atMS)) args.push('--at-ms', String(extra.atMS));
      await send(binding.state_path, args);
    } catch (error) {
      // Do not expose tool data or prevent normal user tool execution. Persisted
      // final-turn/tool checks remain required when the hook transport is absent.
      if (options.onError) options.onError(error);
    }
  }
  try {
    const bindings = JSON.parse(await readFile(registry, 'utf8'));
    for (const sessionID of Object.keys(bindings.sessions ?? {})) await emit(sessionID, 'hook_loaded');
  } catch (error) { if (error.code !== 'ENOENT') throw error; }
  registrations.push(await ctx.tool.hook('execute.before', event => emit(event.sessionID, 'tool_start', {
    callID: event.id, agent: event.agent, eventID: 'before:' + event.id,
  })));
  registrations.push(await ctx.tool.hook('execute.after', event => emit(event.sessionID, 'tool_end', {
    callID: event.id, agent: event.agent, eventID: 'after:' + event.id,
  })));
  registrations.push(await ctx.session.hook('context', event => emit(event.sessionID, 'agent', {
    agent: event.agent,
  })));
  const events = (async () => {
    try {
      for await (const event of ctx.event.subscribe({ signal: abort.signal })) {
        const data = event.data ?? event.properties;
        const id = data?.sessionID;
        if (!id) continue;
        const kind = { 'session.execution.started': 'turn_start',
          'session.execution.succeeded': 'turn_end',
          'session.execution.failed': 'turn_end', 'session.idle': 'idle' }[event.type];
        if (kind) await emit(id, kind, { eventID: event.id, atMS: event.created });
        if (event.type === 'session.execution.interrupted' && data.reason === 'user')
          await emit(id, 'interrupted', { eventID: event.id, atMS: event.created });
      }
    } catch (error) { if (!abort.signal.aborted && options.onError) options.onError(error); }
  })();
  return async () => {
    abort.abort();
    for (const registration of registrations.reverse()) await registration.dispose();
    await events;
  };
}
