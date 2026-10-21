"""Source-bound unittest evidence; no inference, project jobs or remote pushes."""
import hashlib
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
names = ["grip.py", "mission.py", "objective_watch.py", "tests/test_objective_watch.py", "progress_watch.py", "completion.py", "event_hooks.py",
         "plugins/grip-events.mjs", "stream_events.py", "v2_control.py", "tests/test_v2_control.py", "tests/test_stream_events.py", "tests/test_grip.py", "tests/test_mission.py",
          "tests/test_completion.py", "tests/test_events.py", "tests/test_hook_bridge.mjs", "tests/test_portability.py", "tests/verify_activation.py"]
def hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in names}
out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=False)
before = hashes()
started = time.time()
suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_*.py")
with (out / "tests.log").open("w") as log:
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
node = subprocess.run(['node','--test',str(ROOT/'tests/test_hook_bridge.mjs')],
                      capture_output=True,text=True,timeout=20)
(out/'hook-tests.log').write_text(node.stdout+node.stderr)
def tap_count(name):
    match=re.search(r'^# '+name+r' (\d+)$',node.stdout,re.M)
    return int(match.group(1)) if match else None
after = hashes()
report = {"schema": 1, "name": "grip-portability", "python": platform.python_version(),
          "tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "skips": len(result.skipped),
          "duration_s": time.time() - started, "source_sha256": before,
          "js_tests":tap_count('tests'),"js_failures":tap_count('fail'),"js_skips":tap_count('skipped'),
          "source_drift": [name for name in before if before[name] != after[name]],
          "scope": "Unit/CLI + real tmux watcher against fake HTTP chat server; no real AI wake, project compute or GitHub pushes"}
report["passed"] = (result.wasSuccessful() and not report["source_drift"] and not result.skipped
                    and node.returncode==0 and bool(report['js_tests']) and report['js_failures']==0 and report['js_skips']==0)
(out / "run_card.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({key: value for key, value in report.items() if key != "source_sha256"}))
if not report["passed"]:
    print((out / "tests.log").read_text())
print("========== DONE ==========", flush=True)
raise SystemExit(0 if report["passed"] else 1)
