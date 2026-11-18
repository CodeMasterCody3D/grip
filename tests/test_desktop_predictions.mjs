import assert from 'node:assert/strict';
import test from 'node:test';
import { localEndpoint, predictionEvent, readComposerPrediction, readVisibleGreyText, readDesktopContext } from '../desktop_predictions.mjs';

function page({ prediction = { text: 'Check the output', sourceTurnId: 'turn-1' }, draft = false,
                visible = true, grey = true, plugin = true, composing = false } = {}) {
  const paragraph = {};
  const greyNode = { textContent: prediction?.text ?? '', getClientRects: () => [{}] };
  const view = { composing, state: {
    doc: { childCount: 1, firstChild: { type: paragraph, content: { size: draft ? 4 : 0 } },
           type: { schema: { nodes: { paragraph } } } },
    plugins: plugin ? [{ key: 'cumberbatch$', getState: () => ({ prediction }) }] : [],
  } };
  // Match the actual bundled DocViewDesc: no view property. The composer
  // controller lives in React hook state, rather than a fabricated DOM pointer.
  const element = { pmViewDesc: {}, getClientRects: () => visible ? [{}] : [],
    querySelector: () => grey ? greyNode : null };
  view.dom = element;
  element.__reactFiber$fixture = { memoizedState: { memoizedState: { view }, next: null } };
  globalThis.document = { querySelectorAll: selector => selector.includes('data-cumberbatch') ? grey ? [greyNode] : [] : [element] };
  globalThis.getComputedStyle = () => ({ display: 'block', visibility: 'visible' });
}

test('reads the exact prediction object and originating turn', () => {
  page();
  assert.deepEqual(readComposerPrediction('turn-1'), {
    captured: true, source: 'codex-composer-prosemirror', text: 'Check the output',
    sourceTurnId: 'turn-1', displayed: true, composerEmpty: true,
  });
});
test('different chat or source turn returns no prediction text', () => {
  page({ prediction: { text: 'PRIVATE OTHER CHAT', sourceTurnId: 'other' } });
  const result = readComposerPrediction('turn-1');
  assert.equal(result.captured, false);
  assert.equal(JSON.stringify(result).includes('PRIVATE'), false);
});
test('finds the live desktop composerController prop shape', () => {
  page();
  const element = document.querySelectorAll('.ProseMirror[contenteditable="true"]')[0];
  const view = element.__reactFiber$fixture.memoizedState.memoizedState.view;
  delete element.__reactFiber$fixture;
  element.parentElement = { __reactFiber$fixture: {
    memoizedProps: { composerController: { view } },
  } };
  assert.equal(readComposerPrediction('turn-1').captured, true);
});
test('draft, composition, hidden composer and hidden prediction are not captured', () => {
  for (const options of [{ draft: true }, { composing: true }, { visible: false }, { grey: false }]) {
    page(options);
    assert.equal(readComposerPrediction('turn-1').captured, false);
  }
});
test('missing plugin and empty suggestions have explicit unavailable results', () => {
  for (const options of [{ plugin: false }, { prediction: null },
    { prediction: { sourceTurnId: 'turn-1', text: '' } }]) {
    page(options);
    assert.equal(readComposerPrediction('turn-1').captured, false);
  }
});
test('produces the event accepted by the GRIP bridge', () => {
  page();
  const event = predictionEvent(readComposerPrediction('turn-1'), 'thread-1');
  assert.deepEqual(event, { method: 'thread/prediction/updated', grip_capture_source: 'desktop_composer_cdp', params: {
    threadId: 'thread-1', sourceTurnId: 'turn-1', result: { type: 'completed', text: 'Check the output' },
  } });
  assert.throws(() => predictionEvent({ captured: false }, 'thread-1'));
});
test('direct DOM capture preserves displayed text without inventing a source turn', () => {
  page();
  const sample = readVisibleGreyText();
  assert.equal(sample.text, 'Check the output');
  assert.equal(sample.sourceTurnId, null);
  assert.equal(sample.ingestionEligible, false);
  assert.throws(() => predictionEvent(sample, 'thread-1'));
});
test('ambiguous displayed widgets are not silently assigned to a chat', () => {
  page();
  const node = { textContent: 'example', getClientRects: () => [{}] };
  globalThis.document = { querySelectorAll: () => [node, node] };
  assert.equal(readVisibleGreyText().reason, 'ambiguous_visible_predictions');
});
test('desktop context requires the exact visible chat and an authoritative turn flag', () => {
  page();
  const element = document.querySelectorAll('.ProseMirror[contenteditable="true"]')[0];
  const view = element.__reactFiber$fixture.memoizedState.memoizedState.view;
  element.__reactFiber$fixture.memoizedProps = { composerController: { view }, conversationId: 'thread-1',
    turn: { serverInProgress: false } };
  assert.equal(readDesktopContext('thread-1').idle, true);
  assert.equal(readDesktopContext('other').available, false);
  element.__reactFiber$fixture.memoizedProps.turn.serverInProgress = true;
  assert.equal(readDesktopContext('thread-1').idle, false);
  delete element.__reactFiber$fixture.memoizedProps.turn;
  assert.equal(readDesktopContext('thread-1').available, false);
});
test('desktop context preserves drafts and refuses handoff transitions', () => {
  page({ draft: true });
  const element = document.querySelectorAll('.ProseMirror[contenteditable="true"]')[0];
  const view = element.__reactFiber$fixture.memoizedState.memoizedState.view;
  element.__reactFiber$fixture.memoizedProps = { composerController: { view }, conversationId: 'thread-1',
    turn: { serverInProgress: false }, isThreadHandoffInProgress: true };
  const context = readDesktopContext('thread-1');
  assert.equal(context.idle, false);
  assert.equal(context.composerEmpty, false);
});
test('rejects external endpoints, credentials and ambiguous ports', () => {
  assert.equal(localEndpoint('http://127.0.0.1:9222').port, '9222');
  for (const endpoint of ['http://0.0.0.0:9222', 'http://example.com:9222',
    'http://localhost:9222', 'http://user:secret@127.0.0.1:9222', 'http://127.0.0.1',
    'http://127.0.0.1:9222/path']) assert.throws(() => localEndpoint(endpoint));
});
