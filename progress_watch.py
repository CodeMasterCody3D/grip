"""Progress observations only:tool calls and heartbeat rewrites are not progress."""
import hashlib
import json
from pathlib import Path
import time

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest()

def observe(state,home,now=None):
    now=time.time() if now is None else now
    config=state.get('progress_watch',{})
    root=Path(state['workspace'])
    paths=[Path(home)/'grip.py',Path(home)/'progress_watch.py',Path(home)/'tests/test_grip.py']
    paths += [root/Path(p).expanduser() for p in config.get('source_paths',[])]
    if state.get('active_iteration'):
        record=Path(state.get('backup_directory',home)).expanduser()/'projects'/state['project_id']/'iterations'/state['active_iteration']/'ITERATION.json'
        if record.exists():paths += [root/p for p in json.loads(record.read_text()).get('owned_files',[])]
    sources={}
    for path in paths:
        if path.is_file() and path.stat().st_size<=4*1024*1024:
            sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    runs={}
    for pattern in config.get('progress_globs',[]):
        for path in root.glob(pattern):
            try:
                data=json.loads(path.read_text())
                runs[str(path.relative_to(root))]={k:data.get(k) for k in config.get('progress_fields',('status','step','total_steps','loss','worker_returncode'))}
            except (OSError,ValueError):continue
    vm=None
    try:
        value=json.loads(Path(config['vm_snapshot']).read_text())
        if value.get('schema')==config.get('snapshot_schema','grip_progress_beacon_v1') and 0<=now-value['now']<=config.get('snapshot_max_age',150):vm=value
    except (OSError,ValueError,KeyError):pass
    return {'source_signature':digest(sources),'compute_signature':digest(runs),'vm':vm}

def active_tools(messages):
    return any(p.get('type')=='tool' and p.get('state',{}).get('status') in ('running','pending')
               for m in messages if m['info'].get('role')=='assistant' and not m['info'].get('time',{}).get('completed')
               for p in m.get('parts',[]))

def assess(state,observation,messages,now=None):
    now=time.time() if now is None else now
    config=state['progress_watch'];memory=state.setdefault('progress_watch_state',{})
    activated=config['activated_at'];last=memory.setdefault('last_material_at',activated)
    for kind in ('source','compute'):
        key=kind+'_signature';current=observation[key]
        if key not in memory:memory[key]=current
        elif memory[key]!=current:
            memory[key]=current;memory['last_material_at']=now;memory['last_'+kind+'_at']=now
    vm=observation.get('vm')
    if vm and (vm.get('job_lease_alive') or vm.get('busy')):
        job_signature=digest({'run':vm.get('job_run_id'),'progress':vm.get('job_progress'),
                              'log_bytes':vm.get('worker_log',{}).get('bytes')})
        if memory.get('job_signature')!=job_signature:
            memory['job_signature']=job_signature;memory['last_job_progress_at']=now
        job_age=now-memory.setdefault('last_job_progress_at',now)
        if vm.get('job_lease_alive') and job_age>=config.get('job_stall_seconds',600):
            pending=memory.get('pending')
            assistants=[m['info'] for m in messages if m['info'].get('role')=='assistant']
            latest=max(assistants,key=lambda i:i['time']['created']) if assistants else None
            if pending and latest and latest.get('finish')=='stop' and latest.get('time',{}).get('completed') and not active_tools(messages):
                return {'action':'resume_after_note','reason':'Inspect stalled live job;do not duplicate/kill worker'}
            if pending:return {'action':'job_attention_pending','job_no_progress_seconds':job_age}
            if now-memory.get('last_notice_at',0)>=config.get('cooldown_seconds',180):
                return {'action':'send_note','reason':f'Worker is alive but step/log progress is unchanged for {int(job_age)} seconds;inspect run health,do not start a duplicate or kill it blindly'}
        memory['last_material_at']=now;memory.pop('pending',None)
        return {'action':'protected_job','vm_job':vm.get('job_run_id'),'reason':'Actual live lease/job or GPU activity'}
    if active_tools(messages):return {'action':'protected_tool','reason':'An actual tool invocation is still running'}
    pending=memory.get('pending')
    if pending and memory['last_material_at']>pending['sent_at']:
        memory.pop('pending',None);return {'action':'progress_resumed'}
    assistants=[m['info'] for m in messages if m['info'].get('role')=='assistant']
    latest=max(assistants,key=lambda i:i['time']['created']) if assistants else None
    if pending:
        if latest and latest.get('finish')=='stop' and latest.get('time',{}).get('completed'):
            return {'action':'resume_after_note','parent':latest['id']}
        age=now-pending['sent_at']
        if age>=config.get('escalate_seconds',60) and state.get('dispatch_active') and vm:
            return {'action':'recover_owned_stall','pending_seconds':age}
        return {'action':'note_pending','pending_seconds':age}
    since=now-memory['last_material_at']
    idle=0 if vm is None or vm.get('idle_since') is None else now-max(activated,vm['idle_since'])
    due=since>=config.get('no_progress_seconds',180) or idle>=config.get('vm_idle_seconds',300)
    if not due or now-memory.get('last_notice_at',0)<config.get('cooldown_seconds',180):return {'action':'observing','no_progress_seconds':since,'vm_idle_seconds':idle}
    return {'action':'send_note','no_progress_seconds':since,'vm_idle_seconds':idle,'vm_observation_fresh':vm is not None,
            'reason':'No code/checkpoint/run progress or VM preparation exceeded idle budget;chat busy flags do not suppress this check'}
