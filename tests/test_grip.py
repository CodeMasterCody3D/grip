from datetime import datetime, timezone, timedelta
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location("grip",Path(__file__).parents[1]/"grip.py")
grip=importlib.util.module_from_spec(spec); spec.loader.exec_module(grip)

def state():
    return {"status":"active","deadline":(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat(),
            "tasks":[{"content":"one measured packet","status":"pending"}],"idle_grace_seconds":0,
            "maximum_wakes":5,"session_id":"test","session_directory":"/test"}

def messages(finish="stop", role="assistant", complete=True):
    info={"id":"m1","role":role,"finish":finish,"time":{"created":1,"completed":2 if complete else None}}
    return [{"info":info,"parts":[{"type":"text","text":"done"}]}]

class Eligibility(unittest.TestCase):
    def test_explicit_until_stopped_schedule(self):
        s=state();s['deadline']=None
        self.assertTrue(grip.eligible(s,{'type':'idle'},messages()))
        self.assertFalse(grip.deadline_reached(s,margin=7200))
        s['status']='paused'
        self.assertFalse(grip.eligible(s,{'type':'idle'},messages()))

    def test_until_stopped_prompt_requires_grip(self):
        s=state();s.update(deadline=None,workspace='/fixture',state_path='/fixture/state.json',compute_target='assigned only')
        text=grip.prompt(s)
        self.assertIn('Continue the current project and apply the GRIP skill',text)
        self.assertIn('until user stops or pauses',text)
    def test_final_idle_positive(self): self.assertTrue(grip.eligible(state(),{"type":"idle"},messages()))
    def test_busy_negative(self): self.assertFalse(grip.eligible(state(),{"type":"busy"},messages()))
    def test_tool_call_finished_is_not_turn_finished(self): self.assertFalse(grip.eligible(state(),{"type":"idle"},messages("tool-calls")))
    def test_incomplete_negative(self): self.assertFalse(grip.eligible(state(),{"type":"idle"},messages(complete=False)))
    def test_stop_user_negative(self):
        m=messages(); m.insert(0,{"info":{"id":"u","role":"user","time":{"created":0}},"parts":[{"type":"text","text":"stop GRIP"}]})
        self.assertFalse(grip.eligible(state(),{"type":"idle"},m))
    def test_paused_and_deadline(self):
        s=state(); s["status"]="paused"; self.assertFalse(grip.eligible(s,{"type":"idle"},messages()))
        s["status"]="active"; s["deadline"]="2000-01-01T00:00:00+00:00"; self.assertFalse(grip.eligible(s,{"type":"idle"},messages()))
    def test_active_tool_blocks_false_idle(self):
        m=messages(); m[0]["parts"].append({"type":"tool","state":{"status":"running"}})
        self.assertFalse(grip.eligible(state(),{"type":"idle"},m))

class Wake(unittest.TestCase):
    def test_prompt_is_profile_driven(self):
        s=state(); s.update(workspace="/fixture/project",state_path="/fixture/state.json",compute_target="fixture compute",
                            continuation_instructions="fixture-only scope")
        text=grip.prompt(s)
        self.assertIn("fixture-only scope",text); self.assertNotIn("dodecahedron",text); self.assertNotIn("GNU-AI",text)
    def test_positive_wake_uses_pinned_model_and_receipt(self):
        s=state(); s.update(workspace="/fixture/project",state_path="/fixture/state.json",compute_target="fixture compute",
                            provider_id="provider",model_id="model",project_id="fixture")
        calls=[]
        class Fake:
            def __init__(self,s): pass
            def snapshot(self): return {"type":"idle"},messages()
            def request(self,path,body): calls.append((path,body))
        with tempfile.TemporaryDirectory() as temp,patch.object(grip,"Client",Fake),patch.object(grip,"checkpoint",return_value={}),patch.object(grip,"backup",return_value="commit"),patch.object(grip,"area",return_value=Path(temp)):
            result=grip.tick(s)
            self.assertEqual(result["stage"],"api_accepted")
            self.assertEqual(calls[0][1]["model"],{"providerID":"provider","modelID":"model"})
            self.assertEqual(grip.load(Path(temp)/"LAST_WAKE.json")["stage"],"api_accepted")
    def test_freshness_race_suppresses(self):
        class Fake:
            n=0
            def __init__(self,s): pass
            def snapshot(self):
                self.n+=1; return ({"type":"idle"},messages()) if self.n==1 else ({"type":"busy"},messages())
            def request(self,*a): raise AssertionError("must not dispatch")
        with patch.object(grip,"Client",Fake): self.assertEqual(grip.tick(state(),True)["reason"],"freshness race suppressed")
    def test_deduplicates_same_final_turn(self):
        s=state(); s["last_dispatched_fingerprint"]="m1:2"
        class Fake:
            def __init__(self,s): pass
            def snapshot(self): return {"type":"idle"},messages()
        with patch.object(grip,"Client",Fake): self.assertEqual(grip.tick(s,True)["stage"],"suppressed")
    def test_dry_run_has_no_network_write_or_backup(self):
        class Fake:
            def __init__(self,s): pass
            def snapshot(self): return {"type":"idle"},messages()
            def request(self,*a): raise AssertionError("dry run wrote")
        with patch.object(grip,"Client",Fake),patch.object(grip,"checkpoint",side_effect=AssertionError("backup")):
            self.assertEqual(grip.tick(state(),True)["stage"],"would_dispatch")

    def test_ambiguous_dispatch_survives_crash_and_is_not_replayed(self):
        s=state(); s.update(workspace='/fixture',compute_target='fixture',provider_id='fixture',model_id='fixture',project_id='fixture')
        calls=[]
        class Fake:
            def __init__(self, state): pass
            def snapshot(self): return {'type':'idle'},messages()
            def request(self,*args): calls.append(args); raise RuntimeError('accepted but response lost')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'state.json';s['state_path']=str(path);grip.atomic(path,s)
            with patch.object(grip,'Client',Fake),patch.object(grip,'checkpoint',return_value={}):
                with self.assertRaisesRegex(RuntimeError,'response lost'):grip.tick(s)
                restarted=grip.load(path)
                self.assertEqual(restarted['dispatch_intent']['status'],'pending')
                self.assertEqual(grip.tick(restarted)['stage'],'needs_investigation')
            self.assertEqual(len(calls),1)

class ProgressWatch(unittest.TestCase):
    def configured(self):
        s=state();s.update(workspace='/fixture',project_id='fixture',state_path='/fixture/state.json',compute_target='assigned only')
        s['progress_watch']={'enabled':True,'activated_at':0,'no_progress_seconds':180,'vm_idle_seconds':300,'escalate_seconds':60,'cooldown_seconds':180}
        s['progress_watch_state']={'source_signature':'source','compute_signature':'compute','last_material_at':0}
        return s
    def observation(self,vm=True):
        return {'source_signature':'source','compute_signature':'compute','vm':{'now':1000,'busy':False,'job_lease_alive':False,'idle_since':0} if vm else None}
    def test_busy_chat_does_not_hide_stall(self):
        s=self.configured();result=grip.progress_watch.assess(s,self.observation(),messages(complete=False),now=1000)
        self.assertEqual(result['action'],'send_note')
    def test_live_lease_protected_even_at_zero_gpu_utilization(self):
        o=self.observation();o['vm'].update(job_lease_alive=True,gpu_util=0,job_run_id='actual-job')
        result=grip.progress_watch.assess(self.configured(),o,messages(complete=False),now=1000)
        self.assertEqual(result['action'],'protected_job')
    def test_live_pid_alone_does_not_hide_stalled_model_progress(self):
        s=self.configured();o=self.observation()
        o['vm'].update(job_lease_alive=True,job_run_id='job',job_progress={'step':1},worker_log={'bytes':100})
        s['progress_watch_state'].update(job_signature=grip.progress_watch.digest({'run':'job','progress':{'step':1},'log_bytes':100}),last_job_progress_at=0)
        self.assertEqual(grip.progress_watch.assess(s,o,messages(complete=False),now=1000)['action'],'send_note')
        s['progress_watch_state']['pending']={'sent_at':800};s['dispatch_active']='wake1'
        self.assertEqual(grip.progress_watch.assess(s,o,messages(complete=False),now=1000)['action'],'job_attention_pending')
        o['vm']['job_progress']['step']=2
        self.assertEqual(grip.progress_watch.assess(s,o,messages(complete=False),now=1000)['action'],'protected_job')
    def test_active_tool_protected(self):
        m=messages(complete=False);m[0]['parts'].append({'type':'tool','state':{'status':'running'}})
        self.assertEqual(grip.progress_watch.assess(self.configured(),self.observation(),m,now=1000)['action'],'protected_tool')
    def test_code_change_resets_material_progress(self):
        o=self.observation(False);o['source_signature']='changed'
        s=self.configured();result=grip.progress_watch.assess(s,o,messages(complete=False),now=1000)
        self.assertEqual(result['action'],'observing');self.assertEqual(s['progress_watch_state']['last_material_at'],1000)
    def test_vm_idle_budget_not_reset_by_endless_edits(self):
        o=self.observation();o['source_signature']='changed'
        self.assertEqual(grip.progress_watch.assess(self.configured(),o,messages(complete=False),now=1000)['action'],'send_note')
    def test_only_owned_stale_turn_escalates(self):
        s=self.configured();s['progress_watch_state']['pending']={'sent_at':800};s['dispatch_active']='wake1'
        self.assertEqual(grip.progress_watch.assess(s,self.observation(),messages(complete=False),now=1000)['action'],'recover_owned_stall')
        s['dispatch_active']=None
        self.assertEqual(grip.progress_watch.assess(s,self.observation(),messages(complete=False),now=1000)['action'],'note_pending')
    def test_unknown_vm_does_not_allow_abort_escalation(self):
        s=self.configured();s['progress_watch_state']['pending']={'sent_at':800};s['dispatch_active']='wake1'
        self.assertEqual(grip.progress_watch.assess(s,self.observation(False),messages(complete=False),now=1000)['action'],'note_pending')
    def test_real_progress_acknowledges_note(self):
        s=self.configured();s['progress_watch_state']['pending']={'sent_at':800}
        o=self.observation(False);o['compute_signature']='real-step-changed'
        self.assertEqual(grip.progress_watch.assess(s,o,messages(complete=False),now=1000)['action'],'progress_resumed')
        self.assertNotIn('pending',s['progress_watch_state'])
    def test_note_uses_no_reply_not_parallel_generation(self):
        s=self.configured();calls=[]
        class Fake:
            def request(self,path,body):calls.append((path,body))
        with tempfile.TemporaryDirectory() as temp,patch.object(grip,'area',return_value=Path(temp)):
            grip.progress_note(s,Fake(),{'reason':'test'})
        self.assertTrue(calls[0][1]['noReply']);self.assertIn('apply GRIP',calls[0][1]['parts'][0]['text'])
    def test_stopped_user_blocks_watchdog(self):
        s=self.configured();m=messages(complete=False)
        m.append({'info':{'id':'u2','role':'user','time':{'created':3}},'parts':[{'type':'text','text':'stop now'}]})
        class Fake:
            def __init__(self,s):pass
            def snapshot(self):return {'type':'busy'},m
            def request(self,*a):raise AssertionError('Stop should not send progress prompt')
        with patch.object(grip,'Client',Fake):grip.tick(s)
        self.assertEqual(s['status'],'paused')
    def test_heartbeat_only_changes_are_not_compute_progress(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);run=root/'build/runs/run';run.mkdir(parents=True)
            s={'workspace':str(root),'progress_watch':{'progress_globs':['build/runs/*/progress.json']}}
            grip.atomic(run/'progress.json',{'status':'running','step':1,'heartbeat':10})
            first=grip.progress_watch.observe(s,root,now=1000)
            grip.atomic(run/'progress.json',{'status':'running','step':1,'heartbeat':999})
            second=grip.progress_watch.observe(s,root,now=1000)
            self.assertEqual(first['compute_signature'],second['compute_signature'])
            grip.atomic(run/'progress.json',{'status':'running','step':2})
            self.assertNotEqual(second['compute_signature'],grip.progress_watch.observe(s,root,now=1000)['compute_signature'])
    def test_expected_human_abort_is_not_fatal_scheduler_error(self):
        s=state();s['dispatched_at_ms']=1
        m=messages();m[0]['info']['error']={'name':'MessageAbortedError','message':'Aborted'}
        m[0]['info']['time'].update(created=4,completed=5)
        m.append({'info':{'id':'u2','role':'user','time':{'created':3}},'parts':[{'type':'text','text':'Please change this'}]})
        class Fake:
            def __init__(self,s):pass
            def snapshot(self):return {'type':'idle'},m
        with patch.object(grip,'Client',Fake):result=grip.tick(s)
        self.assertEqual(result['stage'],'human_handoff');self.assertEqual(s['status'],'active')

    def test_owned_stall_recovery_banks_aborts_then_resumes(self):
        s=self.configured();s.update(dispatch_active='wake1',provider_id='p',model_id='m',wake_count=1)
        s['progress_watch_state']['pending']={'sent_at':800}
        m=messages(complete=False);m.append({'info':{'id':'u','role':'user','time':{'created':0}},'parts':[{'type':'text','text':grip.MARKER}]})
        calls=[]
        class Fake:
            aborted=False
            def snapshot(self):
                if self.aborted:
                    m[0]['info']['error']={'name':'MessageAbortedError'}
                    return {'type':'idle'},m
                return {'type':'busy'},m
            def request(self,path,body):
                calls.append(path)
                if path.endswith('/abort'):self.aborted=True
        with tempfile.TemporaryDirectory() as temp,patch.object(grip,'area',return_value=Path(temp)),patch.object(grip,'checkpoint') as bank,patch.object(grip.progress_watch,'observe',return_value=self.observation()),patch.object(grip.time,'time',return_value=1000):
            result=grip.progress_intervention(s,Fake(),{'type':'busy'},m)
        self.assertEqual(result['stage'],'progress_recovery_accepted');bank.assert_called_once()
        self.assertEqual(calls,['/session/test/abort','/session/test/prompt_async'])
        self.assertEqual(s['last_agent_error_id'],'m1')

    def test_fresh_human_blocks_owned_recovery(self):
        s=self.configured();s['dispatch_active']='wake1';s['progress_watch_state']['pending']={'sent_at':800}
        m=messages(complete=False);m.append({'info':{'id':'u','role':'user','time':{'created':3}},'parts':[{'type':'text','text':'change the plan'}]})
        class Fake:
            def snapshot(self):return {'type':'busy'},m
            def request(self,*a):raise AssertionError('Must not recover over human')
        with patch.object(grip.progress_watch,'observe',return_value=self.observation()),patch.object(grip.time,'time',return_value=1000):
            result=grip.progress_intervention(s,Fake(),{'type':'busy'},m)
        self.assertEqual(result['action'],'human_turn_protected')

    def test_queued_note_resumes_after_final_without_abort(self):
        s=self.configured();s.update(provider_id='p',model_id='m',wake_count=1)
        s['progress_watch_state']['pending']={'sent_at':800}
        m=messages();m.append({'info':{'id':'u','role':'user','time':{'created':3}},'parts':[{'type':'text','text':grip.MARKER}]})
        calls=[]
        class Fake:
            def snapshot(self):return {'type':'idle'},m
            def request(self,path,body):calls.append(path)
        with tempfile.TemporaryDirectory() as temp,patch.object(grip,'area',return_value=Path(temp)),patch.object(grip.progress_watch,'observe',return_value=self.observation()),patch.object(grip.time,'time',return_value=1000):
            result=grip.progress_intervention(s,Fake(),{'type':'idle'},m)
        self.assertEqual(result['stage'],'progress_recovery_accepted')
        self.assertEqual(calls,['/session/test/prompt_async'])

class Vault(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name); self.repo=self.base/"proxy"; self.repo.mkdir()
        self.work=self.base/"work"; self.work.mkdir()
        self.s={"workspace":str(self.work),"project_id":"p","source_roots":["src"],"metadata_globs":[]}
        self.mock=patch.object(grip,"HOME",self.repo); self.mock.start(); self.addCleanup(self.mock.stop)
    def test_path_escape(self):
        with self.assertRaises(ValueError): grip.owned(self.work,"../foreign")
    def test_credential_refused(self):
        (self.work/"src").mkdir(); (self.work/"src/a.json").write_bytes(b'{"apiKey":"'+b"A"*32+b'"}')
        with self.assertRaises(ValueError): grip.vault(self.s)
    def make_iteration(self):
        f=self.work/"a.py"; f.write_text("old\n"); before=grip.vault(self.s,["a.py"])
        f.write_text("new\n"); after=grip.vault(self.s,["a.py"])
        folder=grip.area(self.s)/"iterations/i0001"
        grip.atomic(folder/"ITERATION.json",{"before":before,"after":after,"owned_files":["a.py"]})
        return f
    def test_restores_only_owned_and_keeps_candidate(self):
        f=self.make_iteration(); foreign=self.work/"foreign"; foreign.write_text("mine")
        result=grip.rollback(self.s,"i0001")
        self.assertEqual(f.read_text(),"old\n"); self.assertEqual(foreign.read_text(),"mine"); self.assertTrue(result["candidate_preserved"])
    def test_concurrent_change_refuses_restore(self):
        f=self.make_iteration(); f.write_text("user edit\n")
        with self.assertRaises(ValueError): grip.rollback(self.s,"i0001")
        self.assertEqual(f.read_text(),"user edit\n")
    def test_corrupt_vault_refuses(self):
        f=self.make_iteration(); record=grip.load(grip.area(self.s)/"iterations/i0001/ITERATION.json")
        identity=record["before"]["a.py"]["sha256"]
        (self.repo/"code_vault"/identity[:2]/identity).write_text("corrupt")
        with self.assertRaises(RuntimeError): grip.rollback(self.s,"i0001")
        self.assertEqual(f.read_text(),"new\n")
    def finish_args(self, identifier, best=None, contract=None):
        evidence=self.work/"report.json"; evidence.write_text('{"status":"completed","score":1}')
        return SimpleNamespace(iteration=identifier,verdict="better" if best else "failed",reason="measured result",
                               evidence="report.json",best=best,metric_contract=contract,family=None)
    def create_running(self, identifier, change="same causal change"):
        f=self.work/"a.py"; f.write_text("candidate\n")
        folder=grip.area(self.s)/"iterations"/identifier
        grip.atomic(folder/"ITERATION.json",{"id":identifier,"status":"running","family":"method",
                    "what_changes":change,"owned_files":["a.py"],"before":grip.vault(self.s,["a.py"])})
        self.s["active_iteration"]=identifier
    def test_best_contract_does_not_replace_selected_parent(self):
        self.s["best"]={"scope":"selected parent"}; self.create_running("i0001")
        with patch.object(grip,"backup",return_value="commit"):
            grip.finish(self.s,self.finish_args("i0001","report.json","vector-task-v1"))
        self.assertEqual(self.s["best"],{"scope":"selected parent"})
        self.assertIn("method:vector-task-v1",self.s["best_by_contract"])
    def test_repeated_identical_failure_is_one_distinct_attempt(self):
        with patch.object(grip,"backup",return_value="commit"):
            for n in range(3):
                identifier=f"i{n+1:04d}"; self.create_running(identifier)
                grip.finish(self.s,self.finish_args(identifier))
        self.assertEqual(self.s["families"]["method"]["distinct_attempt_count"],1)
        self.assertFalse(self.s["families"]["method"]["can_park_after_failure"])
    def test_promotion_without_metric_contract_refused(self):
        self.create_running("i0001")
        with self.assertRaises(ValueError): grip.finish(self.s,self.finish_args("i0001","report.json"))

if __name__=="__main__": unittest.main()
