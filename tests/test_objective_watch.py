"""Objective closure and unified hooks/fallback, fake sessions only."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import completion
import event_hooks
import grip
import mission
import objective_watch
from test_mission import active, goal_report, satisfy_goal
from test_grip import messages


class ObjectiveGuard(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.s=active()
        self.s.update(workspace=str(self.root),state_path=str(self.root/'state.json'),
                      compute_target='fake fixture only',provider_id='fixture',model_id='fixture',
                      project_id='fixture',idle_grace_seconds=0)

    def all_done(self):
        for t in self.s['tasks']:t.update(status='completed',evidence=['fixture result'])
        mission.refresh(self.s)

    def review(self,result='satisfied',report=None):
        report=goal_report(self.s) if report is None else report
        grip.atomic(self.root/'goal.json',report)
        return objective_watch.review(self.s,result=result,note='Reviewed actual fixture scope',
                     evidence=grip.evidence_receipt(self.s,'goal.json'),report=report)

    def test_milestone_done_leaves_full_objective_review(self):
        self.all_done()
        self.assertEqual(self.s['status'],'active')
        self.assertEqual(mission.next_task(self.s)['id'],'grip:objective-review')
        self.assertTrue(all(t['status']=='completed' for t in self.s['tasks']))

    def test_eleven_questions_are_delivered_with_scope_and_boundaries(self):
        text=grip.prompt(self.s)
        self.assertEqual(len(objective_watch.QUESTIONS),11)
        for i,q in enumerate(objective_watch.QUESTIONS,1):self.assertIn(str(i)+'. '+q,text)
        for word in ('milestone','Stop','scope','no endless improvement','never restart','beyond current authorization'):
            self.assertIn(word.lower(),text.lower())

    def test_unfinished_review_does_not_reopen_done_work(self):
        self.all_done();before=copy.deepcopy(self.s['tasks'])
        self.review('unfinished');mission.refresh(self.s)
        self.assertEqual(self.s['tasks'],before)
        self.assertEqual(mission.next_task(self.s)['id'],'grip:objective-review')
        mission.add_task(self.s,{'id':'necessary','content':'Close actual gap','done_when':'Live receipt',
                         'status':'pending','depends_on':[]},now='now',expected=self.s['plan_revision'])
        self.assertEqual(mission.next_task(self.s)['id'],'necessary')

    def test_blocked_goal_suppresses_even_ready_tasks_and_mode1_recovery(self):
        self.review('blocked');self.s['operating_mode']=1
        mission.refresh(self.s)
        self.assertEqual(self.s['status'],'blocked')
        self.assertIsNone(mission.next_task(self.s))
        with patch.object(grip,'Client',side_effect=AssertionError('blocked')):
            self.assertEqual(grip.tick(self.s)['reason'],'blocked')
        self.review('unfinished');mission.refresh(self.s)
        self.assertEqual(self.s['status'],'active')

    def test_blocked_task_is_not_rescued_by_empty_objective_review(self):
        mission.update_task(self.s,'consumer','blocked','Dependency unavailable',now='now',expected=self.s['plan_revision'])
        self.assertIsNone(mission.next_task(self.s))
        self.assertEqual(self.s['status'],'blocked')

    def test_verified_goal_suppresses_without_network_or_endless_work(self):
        self.all_done();self.review();mission.refresh(self.s)
        with patch.object(grip,'Client',side_effect=AssertionError('complete')):
            for _ in range(3):self.assertEqual(grip.tick(self.s)['reason'],'complete')

    def test_narrow_scope_and_stale_signature_cannot_close_project(self):
        self.all_done()
        objective_watch.configure(self.s,objective='Finish whole authorized project',done_when='All selected integration works',scope='project',note='User selected this scope')
        valid=goal_report(self.s)
        for field,value in [('objective','Finish one test'),('scope','milestone'),('done_when','One check'),
                            ('signature','old-source'),('passed',1),('checks',{'fake':1}),('questions_reviewed',[1])]:
            report={**valid,field:value};before=copy.deepcopy(self.s)
            with self.subTest(field=field),self.assertRaises(ValueError):self.review(report=report)
            self.assertEqual(self.s,before)

    def test_task_and_iteration_and_missing_spec_block_satisfaction(self):
        with self.assertRaisesRegex(ValueError,'Unfinished'):self.review()
        self.all_done();self.s['active_iteration']='i-fixture'
        with self.assertRaisesRegex(ValueError,'iteration'):self.review()
        self.s['active_iteration']=None;self.s['operating_mode']=1
        with self.assertRaisesRegex(ValueError,'Spec audit'):self.review()

    def test_real_source_change_invalidates_verified_goal_without_reopening_tasks(self):
        self.all_done();(self.root/'source.py').write_text('before\n')
        self.s['operating_mode']=1
        self.s['completion']={'phase':'verified','source_paths':['source.py'],'requirements':[]}
        self.s['completion']['source_fingerprint']=completion.fingerprint(self.s)
        self.review();mission.refresh(self.s)
        self.assertEqual(self.s['status'],'complete')
        old=copy.deepcopy(self.s['objective_guard'])
        (self.root/'source.py').write_text('changed\n')
        mission.refresh(self.s)
        self.assertEqual(self.s['objective_guard']['status'],'unreviewed')
        self.assertEqual(self.s['status'],'active')
        self.assertTrue(all(t['status']=='completed' for t in self.s['tasks']))
        self.assertIn(old,self.s['objective_history'])

    def test_review_after_source_drift_is_refused_without_partial_state_mutation(self):
        self.all_done();(self.root/'source.py').write_text('before\n')
        self.s['operating_mode']=1
        self.s['completion']={'phase':'verified','source_paths':['source.py'],'requirements':[]}
        self.s['completion']['source_fingerprint']=completion.fingerprint(self.s)
        report=goal_report(self.s)
        (self.root/'source.py').write_text('changed\n')
        before=copy.deepcopy(self.s)
        with self.assertRaisesRegex(ValueError,'Spec audit'):self.review(report=report)
        self.assertEqual(self.s,before)

    def test_repeat_activation_does_not_silently_migrate_legacy_completion(self):
        from test_mission import manifest
        self.all_done();self.s.pop('objective_guard');mission.refresh(self.s)
        before=copy.deepcopy(self.s)
        mission.activate(self.s,manifest(),now='repeat legacy')
        self.assertEqual(self.s,before)
        self.assertEqual(self.s['status'],'complete')

    def test_repeat_activation_cannot_narrow_guard_scope(self):
        from test_mission import manifest
        plan=manifest();plan['project_objective']='Narrower task'
        before=copy.deepcopy(self.s)
        with self.assertRaisesRegex(ValueError,'authorized objective'):
            mission.activate(self.s,plan,now='narrow')
        self.assertEqual(self.s,before)

    def test_modified_or_deleted_objective_proof_invalidates_closure(self):
        self.all_done();self.review();mission.refresh(self.s)
        (self.root/'goal.json').unlink();mission.refresh(self.s)
        self.assertEqual(self.s['objective_guard']['status'],'unreviewed')

    def test_task_definition_change_invalidates_and_keeps_completion_history(self):
        self.all_done();self.review();mission.refresh(self.s)
        self.s['tasks'][0]['done_when']='A newly authorized additional condition'
        mission.refresh(self.s)
        self.assertEqual(self.s['objective_guard']['status'],'unreviewed')

    def test_pause_survives_reconfiguration_and_unfinished_review(self):
        self.s['status']='paused';self.review('unfinished');mission.refresh(self.s)
        self.assertEqual(self.s['status'],'paused')

    def test_hook_bursts_and_fallback_share_one_dispatch_and_freshness_gate(self):
        self.all_done();calls=[]
        owner=self
        class Fake:
            def __init__(self,s):pass
            def snapshot(self):return {'type':'idle'},messages()
            def request(self,path,body):calls.append((path,body));return {'id':'fixture-receipt'}
        with patch.object(grip,'Client',Fake),patch.object(grip,'checkpoint'),patch.object(grip,'backup'),patch.object(grip,'area',return_value=self.root):
            for kind in ('tool_end','idle','idle'):
                event_hooks.record(self.s,session_id='fixture',kind=kind,call_id='tool' if kind=='tool_end' else None)
                grip.tick(self.s)
            grip.tick(self.s)  # polling fallback for the same final turn
        self.assertEqual(len(calls),1)
        self.assertIn('ELEVEN-QUESTION',calls[0][1]['parts'][0]['text'])

    def test_unfinished_goal_still_honors_plan_stop_busy_tool_and_new_human(self):
        self.all_done()
        for case in ('plan','stop','tool','busy','new-human'):
            m=messages();status={'type':'idle'}
            if case=='plan':m[0]['info']['agent']='plan'
            if case=='stop':m.insert(0,{'info':{'role':'user','id':'u','time':{'created':0}},'parts':[{'type':'text','text':'stop now'}]})
            if case=='tool':m[0]['parts'].append({'type':'tool','state':{'status':'running'}})
            if case=='busy':status={'type':'busy'}
            if case=='new-human':m.append({'info':{'role':'user','id':'u','time':{'created':3}},'parts':[]})
            with self.subTest(case=case):self.assertFalse(grip.eligible(self.s,status,m))

    def test_cli_invalid_reviews_stale_revisions_and_changed_source_are_transactional(self):
        self.all_done();path=self.root/'state.json';grip.atomic(path,self.s)
        def cli(*args):
            return subprocess.run([sys.executable,str(grip.HOME/'grip.py'),'--state',str(path),*args],
                                  capture_output=True,text=True,timeout=10)
        for args in [('goal','--objective','x','--done-when','y','--scope','project','--note','authority','--revision','0'),
                     ('goal-review','--result','satisfied','--note','missing','--evidence','absent.json','--revision','1')]:
            before=path.read_bytes();self.assertNotEqual(cli(*args).returncode,0);self.assertEqual(path.read_bytes(),before)
        grip.atomic(self.root/'bad.json',{'passed':True,'checks':{'narrow':True}})
        before=path.read_bytes()
        self.assertNotEqual(cli('goal-review','--result','satisfied','--note','narrow','--evidence','bad.json','--revision','1').returncode,0)
        self.assertEqual(path.read_bytes(),before)
        self.assertEqual(cli('goal','--objective','Full selected goal','--done-when','Verified entire goal','--scope','project','--note','User authorized','--revision','1').returncode,0)
        s=grip.load(path);grip.atomic(self.root/'good.json',goal_report(s))
        self.assertEqual(cli('goal-review','--result','satisfied','--note','full review','--evidence','good.json','--revision','2').returncode,0)
        self.assertEqual(grip.load(path)['status'],'complete')


if __name__=='__main__':unittest.main()
