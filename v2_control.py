"""Adapter for the installed native OpenCode API; legacy profiles stay legacy.

Routes/schema were discovered from the running server's OpenAPI. Queued prompts
never switch the user's agent/model or interrupt the human's active turn.
"""
import urllib.error


def cancel_pending(client):
    """Cancel only the inbox item returned by THIS wake; never interrupt a user."""
    state = client.state
    identifier = (state.get('dispatch_receipt') or {}).get('id')
    if not identifier:
        return {'cancelled': False, 'reason': 'no_owned_inbox_receipt'}
    if not isinstance(identifier, str) or '/' in identifier:
        raise ValueError('Invalid owned inbox receipt')
    try:
        client.http('/api/session/'+state['session_id']+'/inbox/'+identifier, method='DELETE')
        result = {'cancelled': True, 'inbox_id': identifier}
    except urllib.error.HTTPError as error:
        if error.code not in (404, 409): raise
        result = {'cancelled': False, 'reason': 'already_delivered_or_absent', 'inbox_id': identifier}
    state.setdefault('cancelled_wakes', []).append(result)
    state.pop('dispatch_receipt', None)
    return result


def message(row):
    kind = row.get('type')
    parts = row.get('content', [])
    if kind == 'user' and isinstance(row.get('text'), str):
        parts = [{'type': 'text', 'text': row['text']}]
    return {'info': {'id': row['id'], 'role': kind if kind in ('user', 'assistant') else 'system',
                     'agent': row.get('agent'), 'finish': row.get('finish'), 'time': row['time'],
                     **({'error': row['error']} if row.get('error') else {})},
            'parts': parts}


def request(client, path, body):
    state = client.state
    sid = state['session_id']
    base = '/api/session/' + sid
    if path == '/session/' + sid:
        data = client.http(base)['data']
        return {**data, 'directory': data['location']['directory']}
    if path == '/session/status':
        active = client.http('/api/session/active')['data']
        return {key: {'type': 'busy'}
                for key, value in active.items()}
    if path.startswith('/session/' + sid + '/message?'):
        rows = client.http(base + '/message?limit=32&order=desc')['data']
        # A long tool-heavy turn can exclude its last real user message from the
        # page. Fetch just that user, not the complete transcript.
        users = client.http(base + '/message?limit=1&order=desc&type=user')['data']
        if users and all(r['id'] != users[0]['id'] for r in rows): rows.append(users[0])
        # Native idle/agent/model bookkeeping can follow a completed assistant.
        # It is not a new user assignment and must not hide final-turn evidence.
        return [message(row) for row in rows if row.get('type') in ('user','assistant')]
    if path == '/session/' + sid + '/prompt_async':
        if body.get('noReply'):
            raise ValueError('Native noReply watchdog injection is not implemented; no prompt was sent')
        current = client.http(base)['data']
        model = current['model']
        if current['agent'] != 'build' or model['providerID'] != state['provider_id'] or model['id'] != state['model_id']:
            raise ValueError('Current native session agent/model changed; refuse to override the user')
        text = '\n'.join(p['text'] for p in body.get('parts', []) if p.get('type') == 'text')
        if not text.strip(): raise ValueError('No continuation text')
        # Native queue delivery does not interrupt an intervening user turn.
        return client.http(base + '/prompt', {'text': text, 'delivery': 'queue'})['data']
    if path == '/session/' + sid + '/abort':
        raise ValueError('Never interrupt the native main session from a stale ownership guess; user Stop remains authoritative')
    raise ValueError('Unsupported native control operation; no guessed compatibility route: ' + path)
