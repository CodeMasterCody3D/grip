"""Explicit authorized objective closure and the eleven-question idle review."""
import copy
import hashlib
import json
from pathlib import Path

import completion

QUESTIONS = (
    'Have you finished the FULL user-authorized objective, not just this milestone?',
    'If not, what exact work or verified blocker remains?',
    'How can you finish without unnecessary user questions? Recover existing code, records and decisions first.',
    'What concrete fix or bounded action will address the actual cause?',
    'Can the approach improve? Test positive and mirror/failure cases, preserve the best.',
    'Does this follow the latest user intent and the recorded authorized objective?',
    'Does it negate a requested feature, discard work or exceed permission/compute boundaries?',
    'If stuck, would source-linked research resolve it within existing authorization?',
    'Would advice help? Use only the project-authorized advisory route if one exists; no new workers/spending by implication.',
    'What actual outputs, exit codes and saved evidence support the claims?',
    'What necessary in-scope gap still blocks the objective? Do not invent unrelated improvements or loop forever.',
)


def signature(state):
    gate = state.get('completion', {})
    value={'tasks':[{k:t.get(k) for k in ('id','content','done_when','depends_on','status','evidence')} for t in state.get('tasks',[])],
           'source':completion.fingerprint(state) if gate else None,
           'gate':{k:gate.get(k) for k in ('phase','requirements','audit','challenge')},
           'objective':{k:state.get('objective_guard',{}).get(k) for k in ('objective','done_when','scope')}}
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def configure(state,*,objective,done_when,scope,note):
    if scope not in ('project','milestone') or any(not isinstance(v,str) or not v.strip() for v in (objective,done_when,note)):
        raise ValueError('Explicit authorized objective, finish condition, scope and authority note required')
    old=state.get('objective_guard')
    if old:state.setdefault('objective_history',[]).append(copy.deepcopy(old))
    state['objective_guard']={'objective':objective,'done_when':done_when,'scope':scope,'authority_note':note,'status':'unreviewed'}


def sync(state):
    completion.sync(state)
    goal=state.get('objective_guard')
    if not goal or goal['status']!='verified':return
    receipt=goal.get('evidence',{})
    root=Path(state.get('workspace','.')).resolve()
    path=(root/receipt.get('path','')).resolve()
    valid_evidence=(path.is_relative_to(root) and path!=root and path.is_file() and
                    hashlib.sha256(path.read_bytes()).hexdigest()==receipt.get('sha256'))
    if goal.get('signature')!=signature(state) or not valid_evidence:
        state.setdefault('objective_history',[]).append(copy.deepcopy(goal))
        goal.update(status='unreviewed',note='Objective inputs or saved proof changed; review again, never restart completed tasks')
        goal.pop('evidence',None)


def allowed_complete(state):
    sync(state)
    return not state.get('objective_guard') or state['objective_guard']['status']=='verified'


def next_action(state):
    sync(state);goal=state.get('objective_guard')
    if not goal or goal['status'] in ('verified','blocked'):return None
    if any(t.get('status')!='completed' for t in state.get('tasks',[])):return None
    return {'id':'grip:objective-review','status':'pending','governance':True,
        'content':'Review the FULL recorded authorized objective using all eleven gates. A milestone is not project completion. Add genuinely necessary in-scope tasks, or record a verified blocker; do not repeat completed work.',
        'done_when':'Explicit objective-review with exact objective/scope and saved completion evidence, or concrete unfinished/blocked finding'}


def review(state,*,result,note,evidence,report):
    candidate=copy.deepcopy(state)
    sync(candidate)
    goal=candidate.get('objective_guard')
    if not goal or result not in ('satisfied','unfinished','blocked') or not isinstance(note,str) or not note.strip():raise ValueError('Known objective and reason required')
    if not isinstance(report,dict) or not evidence:raise ValueError('Saved objective-review evidence required')
    if result=='satisfied':
        if candidate.get('active_iteration'):raise ValueError('Finish/bank the active iteration before closing its objective')
        if not candidate.get('tasks') or any(t['status']!='completed' for t in candidate['tasks']):raise ValueError('Unfinished tasks cannot satisfy objective')
        if (completion.selected(candidate) and not candidate.get('completion')) or (candidate.get('completion') and candidate['completion']['phase']!='verified'):
            raise ValueError('Spec audit and separate challenge must pass first')
        if any(report.get(k)!=goal[k] for k in ('objective','done_when','scope')):raise ValueError('Narrow/different objective evidence cannot close this goal')
        if report.get('signature')!=signature(candidate):raise ValueError('Objective proof must match the current source/task/review signature')
        if report.get('questions_reviewed')!=list(range(1,12)):raise ValueError('Review all eleven questions before objective closure')
        checks=report.get('checks')
        if report.get('passed') is not True or not isinstance(checks,dict) or not checks or any(v is not True for v in checks.values()):
            raise ValueError('Objective completion needs literal all-true evidence')
    candidate.setdefault('objective_history',[]).append(copy.deepcopy(goal))
    goal.update(status='verified' if result=='satisfied' else result,note=note,evidence=evidence,signature=signature(candidate))
    state.clear();state.update(candidate)
    return state['objective_guard']


def prompt(state):
    goal=state.get('objective_guard')
    return ('\n[GRIP ELEVEN-QUESTION IDLE REVIEW]\n'+
        '\n'.join(str(i)+'. '+q for i,q in enumerate(QUESTIONS,1))+
        '\nAuthorized objective record: '+json.dumps(goal,ensure_ascii=False)+
        '\nWhen present, this explicit goal is the latest closure scope; older mission wording remains historical, not permission to resume prior model work. '+
        '\nUse the recorded goal, not a narrower goal you invent. If unfinished, execute/resume a bounded authorized action and record any necessary gap. '+
        'If truly blocked, record the blocker rather than repeatedly waking. If fully verified, close the objective explicitly; no endless improvement loop. '+
        'This review never grants tools, research, council, agents, model runs or spending beyond current authorization.\n')
