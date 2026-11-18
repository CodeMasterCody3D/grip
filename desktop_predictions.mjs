#!/usr/bin/env node
/** Read the installed Codex composer's existing grey-text state through CDP.
 * No model calls, draft editing, key presses, application patches or sends.
 */
import { readFileSync, writeFileSync, renameSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';

export function localEndpoint(value) {
  const url = new URL(value);
  if (url.protocol !== 'http:' || !['127.0.0.1', '[::1]'].includes(url.hostname) ||
      !url.port || url.username || url.password || url.search || url.hash || url.pathname !== '/') {
    throw new Error('Use a literal loopback HTTP endpoint with an explicit port, such as http://127.0.0.1:9222');
  }
  return url;
}

/** Serialized into the renderer. Keep this self-contained and read-only. */
export function readComposerPrediction(expectedTurn) {
  const visible = element => {
    const style = getComputedStyle(element);
    return element.getClientRects().length > 0 && style.display !== 'none' && style.visibility !== 'hidden';
  };
  const editors = [...document.querySelectorAll('.ProseMirror[contenteditable="true"]')].filter(visible);
  let hasView = false;
  let hasPlugin = false;
  let hasDifferentTurn = false;
  let hasDraft = false;
  for (const element of editors) {
    // This build's DocViewDesc has no view pointer. Its React composer keeps
    // the controller in props/hooks. Search only known controller/ref shapes,
    // and accept a view only if it owns this exact DOM element.
    const candidates = [];
    const consider = value => {
      if (!value || typeof value !== 'object') return;
      for (const item of [value, value.view, value.editorView, value.controller?.view,
        value.editorController?.view, value.composerController?.view, value.current, value.current?.view]) {
        if (item?.dom === element && item.state?.plugins) candidates.push(item);
      }
    };
    consider(element.pmViewDesc?.view);
    consider(element.editor);
    let dom = element;
    for (let ancestor = 0; dom && ancestor < 8 && !candidates.length; ancestor++, dom = dom.parentElement) {
      const key = Object.keys(dom).find(k => k.startsWith('__reactFiber$') || k.startsWith('__reactInternalInstance$'));
      let fiber = key ? dom[key] : null;
      for (let depth = 0; fiber && depth < 24 && !candidates.length; depth++, fiber = fiber.return) {
        consider(fiber.memoizedProps?.controller);
        consider(fiber.memoizedProps?.composerController);
        consider(fiber.memoizedProps?.editorController);
        consider(fiber.memoizedProps?.editorView);
        let hook = fiber.memoizedState;
        for (let index = 0; hook && index < 40 && !candidates.length; index++, hook = hook.next) {
          consider(hook.memoizedState);
          if (Array.isArray(hook.memoizedState)) consider(hook.memoizedState[0]);
        }
      }
    }
    const view = candidates[0];
    if (!view?.state || view.isDestroyed) continue;
    hasView = true;
    const plugin = view.state.plugins.find(p => typeof p.key === 'string' && /^cumberbatch\$/.test(p.key));
    if (!plugin || typeof plugin.getState !== 'function') continue;
    hasPlugin = true;
    const current = plugin.getState(view.state);
    const prediction = current?.prediction;
    if (!prediction || typeof prediction.sourceTurnId !== 'string') continue;
    // Do not return another chat's prediction text. Turn UUIDs identify the
    // exact bound thread's current completed turn, independently of UI routing.
    if (prediction.sourceTurnId !== expectedTurn) { hasDifferentTurn = true; continue; }
    const doc = view.state.doc;
    const empty = doc?.childCount === 1 && doc.firstChild?.type === doc.type.schema.nodes.paragraph &&
      doc.firstChild.content.size === 0;
    if (!empty || view.composing || current.hiddenForComposition) { hasDraft = true; continue; }
    const grey = element.querySelector('[data-cumberbatch] .cumberbatch-content');
    if (!grey || !visible(grey)) continue;
    if (typeof prediction.text !== 'string' || !prediction.text.trim() || prediction.text.length > 8000) continue;
    return { captured: true, source: 'codex-composer-prosemirror', sourceTurnId: prediction.sourceTurnId,
      text: prediction.text, displayed: true, composerEmpty: true };
  }
  return { captured: false, reason: hasDraft ? 'draft_or_composition_present' :
    hasDifferentTurn ? 'different_source_turn' : !editors.length ? 'no_visible_composer' :
    !hasView ? 'editor_view_unavailable' : !hasPlugin ? 'prediction_plugin_unavailable' : 'no_displayed_prediction' };
}

/** First-live-check fallback: exact displayed text, without invented metadata. */
export function readVisibleGreyText() {
  const matches = [...document.querySelectorAll('[data-cumberbatch] .cumberbatch-content')].filter(element => {
    const style = getComputedStyle(element);
    return element.getClientRects().length > 0 && style.display !== 'none' && style.visibility !== 'hidden';
  });
  if (matches.length !== 1) return { captured: false, reason: matches.length ? 'ambiguous_visible_predictions' : 'no_displayed_prediction' };
  const text = matches[0].textContent;
  if (!text?.trim() || text.length > 8000) return { captured: false, reason: 'empty_or_oversized_prediction' };
  return { captured: true, source: 'codex-composer-dom', displayed: true, text, sourceTurnId: null,
    ingestionEligible: false };
}

/** Live-verified composer props, metadata only. Does not inspect message text. */
export function readDesktopContext(expectedThread) {
  const editors = [...document.querySelectorAll('.ProseMirror[contenteditable="true"]')].filter(e =>
    e.getClientRects().length && getComputedStyle(e).display !== 'none' && getComputedStyle(e).visibility !== 'hidden');
  if (editors.length !== 1) return { available: false, reason: 'no_unique_visible_composer' };
  const element = editors[0];
  let view;
  const ids = new Set();
  let sawTurn = false;
  let busy = false;
  let blocked = false;
  for (let dom = element, count = 0; dom && count < 6; dom = dom.parentElement, count++) {
    const key = Object.keys(dom).find(k => k.startsWith('__reactFiber$'));
    for (let f = key ? dom[key] : null, depth = 0; f && depth < 95; f = f.return, depth++) {
      const p = f.memoizedProps;
      if (!p || typeof p !== 'object') continue;
      if (typeof p.conversationId === 'string') ids.add(p.conversationId);
      const candidate = p.composerController?.view;
      if (candidate?.dom === element && candidate.state?.plugins) view = candidate;
      if (p.turn && typeof p.turn.serverInProgress === 'boolean') {
        sawTurn = true;
        busy ||= p.turn.serverInProgress || !!p.turn.floatingSubmissionPending || !!p.turn.hasFloatingStopTarget;
        blocked ||= !!p.turn.transitionBlocksSubmit;
      }
      busy ||= p.isSubmitting === true || p.workingStartedAtMs != null;
      blocked ||= p.isThreadResuming === true || p.isThreadHistoryLoading === true ||
        p.hasThreadResumeFailed === true || p.isThreadHandoffInProgress === true || p.historyBlocksSubmit === true;
    }
  }
  if (ids.size !== 1 || !ids.has(expectedThread)) return { available: false, reason: 'different_visible_thread' };
  if (!view || view.isDestroyed || !sawTurn) return { available: false, reason: 'live_context_unavailable' };
  const doc = view.state.doc;
  const empty = doc?.childCount === 1 && doc.firstChild?.type === doc.type.schema.nodes.paragraph && doc.firstChild.content.size === 0;
  return { available: true, threadId: expectedThread, idle: !busy && !blocked,
    composerEmpty: !!empty && !view.composing, transitionBlocked: blocked };
}

export function predictionEvent(result, threadId) {
  if (!threadId || !result.captured || !result.displayed || !result.composerEmpty ||
      typeof result.sourceTurnId !== 'string' || !result.sourceTurnId ||
      typeof result.text !== 'string' || !result.text.trim() || result.text.length > 8000) {
    throw new Error('A displayed prediction with an exact source turn is required');
  }
  return { method: 'thread/prediction/updated', grip_capture_source: 'desktop_composer_cdp', params: { threadId,
    sourceTurnId: result.sourceTurnId, result: { type: 'completed', text: result.text } } };
}

class Cdp {
  constructor(url) {
    this.pending = new Map();
    this.id = 0;
    this.socket = new WebSocket(url);
    this.ready = new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.socket.close(); reject(new Error('CDP connection timed out')); }, 5000);
      this.socket.addEventListener('open', () => { clearTimeout(timer); resolve(); }, { once: true });
      this.socket.addEventListener('error', () => { clearTimeout(timer); reject(new Error('CDP connection failed')); }, { once: true });
    });
    this.socket.addEventListener('message', event => {
      const message = JSON.parse(event.data);
      const item = this.pending.get(message.id);
      if (!item) return;
      clearTimeout(item.timer);
      this.pending.delete(message.id);
      if (message.error) item.reject(new Error(message.error.message));
      else item.resolve(message.result);
    });
    this.socket.addEventListener('close', () => {
      for (const item of this.pending.values()) {
        clearTimeout(item.timer); item.reject(new Error('CDP disconnected'));
      }
      this.pending.clear();
    });
  }
  async request(method, params) {
    await this.ready;
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(id); reject(new Error('CDP request timed out')); }, 5000);
      this.pending.set(id, { resolve, reject, timer });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }
  close() { this.socket.close(); }
}

export async function main(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i++) {
    const key = argv[i];
    if (['--list', '--ingest', '--visible-text', '--context', '--help'].includes(key)) args[key] = true;
    else if (['--endpoint', '--target-id', '--source-turn', '--thread-id', '--state', '--bridge', '--watch-seconds', '--out'].includes(key)) {
      if (!argv[i + 1] || argv[i + 1].startsWith('--')) throw new Error(`Missing value for ${key}`);
      args[key] = argv[++i];
    } else throw new Error(`Unknown argument: ${key}`);
  }
  if (args['--help']) {
    console.log('Read only: desktop_predictions.mjs --endpoint http://127.0.0.1:9222 --list\n' +
      'Capture: --target-id ID --source-turn EXACT_TURN [--thread-id THREAD --ingest]\n' +
      'First live check: --target-id ID --visible-text (does not invent turn metadata or ingest)\n' +
      'Wait for this turn to finish: --watch-seconds 300 --out /absolute/capture.json\n' +
      'Read idle/draft context: --target-id ID --thread-id THREAD --context\n' +
      'A bound --state FILE supplies thread and current observed turn. Nothing is sent to a chat.');
    return;
  }
  const endpoint = localEndpoint(args['--endpoint'] || 'http://127.0.0.1:9222');
  const response = await fetch(new URL('/json/list', endpoint), { signal: AbortSignal.timeout(3000), redirect: 'error' });
  if (!response.ok) throw new Error(`CDP discovery returned HTTP ${response.status}`);
  const targets = (await response.json()).filter(t => t.type === 'page');
  if (args['--list']) {
    console.log(JSON.stringify(targets.map(({ id, title, url }) => ({ id, title, url })), null, 2));
    return;
  }
  if (!args['--target-id']) throw new Error('Select the Codex app page explicitly with --target-id (see --list)');
  let threadId = args['--thread-id'];
  let sourceTurn = args['--source-turn'];
  if (args['--state']) {
    const state = JSON.parse(readFileSync(args['--state'], 'utf8'));
    if (state.harness !== 'codex') throw new Error('Not a Codex GRIP state');
    if ((threadId && threadId !== state.session_id) || (sourceTurn && sourceTurn !== state.codex?.last_observed_turn)) {
      throw new Error('Explicit thread/turn conflicts with the bound state');
    }
    threadId = state.session_id;
    sourceTurn = state.codex?.last_observed_turn;
  }
  if (args['--visible-text'] && args['--ingest']) throw new Error('DOM-only text cannot be ingested without verified turn metadata');
  if (args['--context'] && (!threadId || args['--ingest'] || args['--watch-seconds'])) throw new Error('Context needs a thread ID and is read-only, single-shot');
  if (!sourceTurn && !args['--visible-text'] && !args['--context']) throw new Error('An exact --source-turn or observed --state is required');
  const target = targets.find(t => t.id === args['--target-id']);
  if (!target?.webSocketDebuggerUrl) throw new Error('The selected page is not available');
  const websocket = new URL(target.webSocketDebuggerUrl);
  if (websocket.protocol !== 'ws:' || websocket.hostname !== endpoint.hostname || websocket.port !== endpoint.port || websocket.username || websocket.password) {
    throw new Error('CDP websocket must stay on the selected loopback endpoint');
  }
  const cdp = new Cdp(websocket.href);
  try {
    if (args['--context']) {
      const remote = await cdp.request('Runtime.evaluate', { expression: `(${readDesktopContext.toString()})(${JSON.stringify(threadId)})`,
        returnByValue: true, silent: true, timeout: 3000 });
      if (remote.exceptionDetails || !remote.result?.value) throw new Error('Live context inspection failed');
      console.log(JSON.stringify(remote.result.value));
      return;
    }
    const seconds = Number(args['--watch-seconds'] || 0);
    if (!Number.isFinite(seconds) || seconds < 0 || seconds > 600) throw new Error('watch-seconds must be between 0 and 600');
    const save = value => {
      if (!args['--out']) return;
      const temporary = `${args['--out']}.${process.pid}.tmp`;
      writeFileSync(temporary, JSON.stringify(value, null, 2) + '\n', { mode: 0o600 });
      renameSync(temporary, args['--out']);
    };
    const scope = { targetId: target.id, threadId: threadId || null, expectedSourceTurnId: sourceTurn || null };
    const started = Date.now();
    if (seconds) save({ status: 'waiting_for_prediction', ...scope, startedAt: new Date(started).toISOString(), durationSeconds: seconds });
    let captured;
    do {
      const remote = await cdp.request('Runtime.evaluate', {
        expression: args['--visible-text'] ? `(${readVisibleGreyText.toString()})()` :
          `(${readComposerPrediction.toString()})(${JSON.stringify(sourceTurn)})`,
        returnByValue: true, silent: true, userGesture: false, timeout: 3000,
      });
      if (remote.exceptionDetails) throw new Error('Composer inspection failed in the renderer');
      captured = remote.result?.value;
      if (!captured || typeof captured.captured !== 'boolean') throw new Error('Unexpected composer result');
      if (captured.captured || Date.now() - started >= seconds * 1000) break;
      await new Promise(resolve => setTimeout(resolve, 1000));
    } while (true);
    save({ status: captured.captured ? 'captured' : seconds ? 'capture_timeout' : 'not_displayed',
      ...scope, ...captured, observedAt: new Date().toISOString() });
    if (args['--ingest'] && captured.captured) {
      const event = predictionEvent(captured, threadId);
      const bridge = args['--bridge'] || fileURLToPath(new URL('./codex_bridge.py', import.meta.url));
      const child = spawnSync('python3', [bridge, 'ingest-prediction'], {
        input: JSON.stringify(event), encoding: 'utf8', timeout: 5000, maxBuffer: 16384,
      });
      if (child.error || child.status !== 0) throw new Error('GRIP prediction ingestion failed');
      console.log(JSON.stringify({ captured: true, sourceTurnId: captured.sourceTurnId,
        characters: captured.text.length, ingestion: JSON.parse(child.stdout) }));
    } else console.log(JSON.stringify(captured));
  } finally { cdp.close(); }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main(process.argv.slice(2)).catch(error => {
    console.error(`GRIP desktop prediction probe: ${error.message}`);
    process.exitCode = 1;
  });
}
