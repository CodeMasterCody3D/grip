"""Portable checkouts and user-owned storage; never real model or GitHub jobs."""
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import event_hooks
import grip


class PortablePaths(unittest.TestCase):
    def test_wake_controller_command_quotes_checkout_and_state_with_spaces(self):
        state={'tasks':[], 'workspace':'selected workspace', 'state_path':'selected state/state.json',
               'compute_target':'selected compute'}
        with patch.object(grip,'HOME',Path('relocated checkout')):
            text=grip.prompt(state)
        command=text.split('Controller CLI: ',1)[1].split('. Latest explicit policy:',1)[0]
        self.assertEqual(shlex.split(command),[sys.executable,'relocated checkout/grip.py',
                                              '--state','selected state/state.json'])

    def test_cache_uses_current_home_xdg_and_explicit_override(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True), \
                patch.object(Path, 'home', return_value=Path(tmp)):
            self.assertEqual(event_hooks.cache_root(), Path(tmp) / '.cache/grip')
            os.environ['XDG_CACHE_HOME'] = str(Path(tmp) / 'user cache')
            self.assertEqual(event_hooks.cache_root(), Path(tmp) / 'user cache/grip')
            os.environ['GRIP_CACHE_DIR'] = str(Path(tmp) / 'chosen cache')
            self.assertEqual(event_hooks.socket_path(Path(tmp)/'mission.json').parent, Path(tmp) / 'chosen cache/events')

    def test_separate_private_storage_preserves_code_and_project_locations(self):
        with tempfile.TemporaryDirectory(prefix='grip relocated ') as tmp:
            root = Path(tmp)
            code = root/'software'; code.mkdir()
            work = root/'workspace'; work.mkdir()
            private = root/'private backup'; private.mkdir()
            state = {'workspace':str(work), 'backup_directory':str(private), 'project_id':'arbitrary-project'}
            source = work/'example.py'; source.write_text('before\n')
            with patch.object(grip, 'HOME', code):
                before = grip.vault(state, ['example.py'])
                source.write_text('after\n')
                after = grip.vault(state, ['example.py'])
                grip.atomic(grip.area(state)/'iterations/i0001/ITERATION.json',
                            {'before':before, 'after':after, 'owned_files':['example.py']})
                grip.rollback(state, 'i0001')
            self.assertEqual(source.read_text(), 'before\n')
            self.assertTrue((private/'code_vault').is_dir())
            self.assertEqual(list(code.iterdir()), [])
            for identifier in ('../other', '/absolute', 'nested/name', ''):
                with self.assertRaises(ValueError): grip.area({**state, 'project_id':identifier})

    def test_skill_install_has_explicit_target_and_refuses_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); target=root/'custom agent/SKILL.md'
            with patch.dict(os.environ, {'GRIP_SKILL_PATH':str(target)}):
                self.assertEqual(grip.installed_skill_path(), target)
                result = grip.install_skill()
                self.assertEqual(Path(result['installed']), target)
                self.assertFalse(result['activation_started'])
                target.unlink(); original=root/'human'; original.write_text('preserve')
                target.symlink_to(original)
                with self.assertRaisesRegex(ValueError, 'Symlinked'): grip.install_skill()
                self.assertEqual(original.read_text(), 'preserve')

    def test_progress_layout_fields_and_beacon_schema_are_selected_by_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); progress=root/'custom jobs/build/state.json'
            grip.atomic(progress, {'finished_units':1, 'heartbeat':1})
            beacon=root/'beacon.json'
            grip.atomic(beacon, {'schema':'project-selected-schema', 'now':100})
            state={'workspace':str(root), 'progress_watch':{}}
            untouched=grip.progress_watch.observe(state,root,now=101)
            state['progress_watch']={'progress_globs':['custom jobs/*/state.json'],
                'progress_fields':['finished_units'], 'vm_snapshot':str(beacon),
                'snapshot_schema':'project-selected-schema'}
            first=grip.progress_watch.observe(state,root,now=101)
            self.assertNotEqual(first['compute_signature'], untouched['compute_signature'])
            self.assertIsNotNone(first['vm'])
            grip.atomic(progress, {'finished_units':1, 'heartbeat':99})
            self.assertEqual(first['compute_signature'], grip.progress_watch.observe(state,root,now=101)['compute_signature'])
            grip.atomic(progress, {'finished_units':2, 'heartbeat':99})
            self.assertNotEqual(first['compute_signature'], grip.progress_watch.observe(state,root,now=101)['compute_signature'])
            self.assertIsNone(grip.progress_watch.observe(state,root,now=1000)['vm'])

    def test_cli_configures_only_explicit_watchdog_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'state.json'
            grip.atomic(path, {'workspace':tmp})
            result=subprocess.run([sys.executable,str(grip.HOME/'grip.py'),'--state',str(path),
                'watchdog','--snapshot',str(Path(tmp)/'beacon.json'),
                '--source-path','chosen-source','--progress-glob','jobs/*/state.json',
                '--progress-field','finished_units','--snapshot-schema','custom-schema'],
                capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            config=json.loads(result.stdout)
            self.assertEqual(config['source_paths'],['chosen-source'])
            self.assertEqual(config['progress_globs'],['jobs/*/state.json'])
            self.assertEqual(config['progress_fields'],['finished_units'])
            self.assertEqual(config['snapshot_schema'],'custom-schema')

    def test_shipping_code_skill_and_docs_have_no_personal_home_addresses(self):
        paths=list(grip.HOME.glob('*.py'))+list((grip.HOME/'plugins').glob('*.mjs'))
        paths+=list(grip.HOME.glob('*.md'))+[grip.HOME/'skills/grip/SKILL.md']
        pattern=re.compile(r'/(?:home|Users)/[A-Za-z0-9_.-]+(?:/|\b)|192\.168\.\d+\.\d+')
        for path in paths:
            with self.subTest(path=path.name): self.assertIsNone(pattern.search(path.read_text()))


class PortableBackup(unittest.TestCase):
    def test_backup_uses_selected_private_checkout_and_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); private=root/'private'; private.mkdir()
            state={'workspace':str(root),'backup_directory':str(private),'github_repo':'fixture/private',
                   'project_id':'fixture','backup_branch':'snapshots','minimum_free_bytes':0}
            calls=[]
            def fake(args, cwd=None, **kwargs):
                calls.append(args)
                self.assertEqual(Path(cwd), private)
                values={('git','rev-parse','--show-toplevel'):str(private),
                    ('git','branch','--show-current'):'snapshots',
                    ('git','remote','get-url','origin'):'https://github.com/fixture/private.git',
                    ('git','rev-parse','HEAD'):'test-commit',
                    ('git','ls-remote','origin','refs/heads/snapshots'):'test-commit refs/heads/snapshots'}
                if args[0]=='gh': return 'true'
                return values.get(tuple(args),'')
            with patch.object(grip,'command',side_effect=fake):
                self.assertEqual(grip.backup(state,'fixture'),'test-commit')
            self.assertIn(['git','push','origin','snapshots'],calls)
            self.assertTrue((private/'projects/fixture/MISSION.json').is_file())

    def test_public_backup_is_refused_before_git_add_or_push(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);calls=[]
            def fake(args, **kwargs):
                calls.append(args)
                return str(root) if args[0]=='git' else 'false'
            with patch.object(grip,'command',side_effect=fake):
                with self.assertRaisesRegex(RuntimeError,'must be private'):
                    grip.backup({'backup_directory':tmp,'github_repo':'fixture/public','minimum_free_bytes':0},'refuse')
            self.assertFalse(any('add' in args or 'push' in args for args in calls))

    def test_parent_repository_cannot_accidentally_be_used_for_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); sub=root/'nested';sub.mkdir()
            with patch.object(grip,'command',return_value=str(root)):
                with self.assertRaisesRegex(ValueError,'repository root'):
                    grip.backup({'backup_directory':str(sub)},'refuse')
