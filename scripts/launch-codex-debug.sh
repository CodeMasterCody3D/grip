#!/usr/bin/env bash
# Start Codex with a local renderer debugger. Never stop an existing app.
set -euo pipefail
GRIP_APP_BIN="${GRIP_APP_BIN:-/usr/lib/chatgpt/ChatGPT}"
GRIP_DEBUG_PORT="${GRIP_DEBUG_PORT:-9222}"
if [[ "${1:-}" == "--dry-run" ]]; then
  printf 'Will launch: %q --remote-debugging-address=127.0.0.1 --remote-debugging-port=%q\n' "$GRIP_APP_BIN" "$GRIP_DEBUG_PORT"
  exit 0
fi
if [[ $# -ne 0 ]]; then
  printf '%s\n' 'This launcher accepts only --dry-run; set GRIP_DEBUG_PORT to choose a port.' >&2
  exit 2
fi
python3 - "$GRIP_APP_BIN" "$GRIP_DEBUG_PORT" <<'PY'
from pathlib import Path
import os, socket, sys
app = Path(sys.argv[1]).resolve(strict=True)
if not app.is_file() or not os.access(app, os.X_OK):
    raise SystemExit('Codex executable is unavailable')
try:
    port = int(sys.argv[2])
    if not 1024 <= port <= 65535: raise ValueError()
except ValueError:
    raise SystemExit('GRIP_DEBUG_PORT must be between 1024 and 65535')
for folder in Path('/proc').iterdir():
    if not folder.name.isdecimal(): continue
    try:
        if (folder / 'exe').resolve() != app: continue
        argv = (folder / 'cmdline').read_bytes().split(b'\0')
        if not any(a.startswith(b'--type=') for a in argv):
            raise SystemExit('Codex is still running. When ready, quit it normally, then run this launcher again. No chats were stopped.')
    except (OSError, RuntimeError):
        continue
with socket.socket() as probe:
    probe.settimeout(0.2)
    if probe.connect_ex(('127.0.0.1', port)) == 0:
        raise SystemExit('The debug port is already in use. Choose another GRIP_DEBUG_PORT.')
PY
exec "$GRIP_APP_BIN" --remote-debugging-address=127.0.0.1 --remote-debugging-port="$GRIP_DEBUG_PORT"
