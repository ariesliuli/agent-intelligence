import pytest
from agent_core.outbox import Outbox

@pytest.fixture
def env(tmp_path):
    now=[100.0]
    return Outbox(tmp_path/'outbox.db',lambda:now[0]),now

def enqueue(s):
    return s.enqueue('op1','task1','read_status',{'device':'simulated'},'task1:read_status:v1')

def test_enqueue(env):
    s,_=env; assert enqueue(s); assert s.get('op1')['state']=='pending'
def test_duplicate(env):
    s,_=env; enqueue(s); assert not enqueue(s)
def test_conflict(env):
    s,_=env; enqueue(s)
    with pytest.raises(ValueError): s.enqueue('op2','task2','other',{},'task1:read_status:v1')
def test_claim(env):
    s,_=env; enqueue(s); assert s.claim('op1','codex')==1
def test_no_double_claim(env):
    s,_=env; enqueue(s); s.claim('op1','codex'); assert s.claim('op1','claude') is None
def test_finish(env):
    s,_=env; enqueue(s); a=s.claim('op1','codex'); assert s.finish('op1','codex',a,{'ok':True}); assert s.get('op1')['state']=='succeeded'
def test_stale_owner(env):
    s,_=env; enqueue(s); a=s.claim('op1','codex'); assert not s.finish('op1','claude',a,{})
def test_expired_to_ambiguous(env):
    s,t=env; enqueue(s); a=s.claim('op1','codex',10); t[0]+=11
    assert s.expire('op1'); assert s.get('op1')['state']=='ambiguous'
    assert s.claim('op1','claude') is None
    assert not s.finish('op1','codex',a,{})
def test_unknown_error_ambiguous(env):
    s,_=env; enqueue(s); a=s.claim('op1','codex'); assert s.fail('op1','codex',a,'timeout'); assert s.get('op1')['state']=='ambiguous'
def test_caller_no_effect_claim_cannot_retry(env):
    s,_=env
    enqueue(s)
    a=s.claim('op1','codex')
    with pytest.raises(PermissionError, match='unverified_no_effect_claim'):
        s.fail('op1','codex',a,'timeout',True)
    assert s.get('op1')['state']=='inflight'
    assert s.fail('op1','codex',a,'timeout')
    assert s.get('op1')['state']=='ambiguous'
    assert s.claim('op1','claude') is None

@pytest.mark.parametrize('claim', [1, 'true', None, {'trusted': True}])
def test_non_boolean_no_effect_claim_rejected(env, claim):
    s,_=env
    enqueue(s)
    a=s.claim('op1','codex')
    with pytest.raises(PermissionError, match='unverified_no_effect_claim'):
        s.fail('op1','codex',a,'timeout',claim)
    assert s.get('op1')['state']=='inflight'

def test_failed_lease_cannot_override_ambiguous(env):
    s,t=env
    enqueue(s)
    a=s.claim('op1','codex',ttl=5)
    t[0]+=6
    assert s.expire('op1')
    with pytest.raises(PermissionError, match='unverified_no_effect_claim'):
        s.fail('op1','codex',a,'timeout',True)
    assert s.get('op1')['state']=='ambiguous'
    assert s.claim('op1','claude') is None
def test_reconcile_success(env):
    s,_=env; enqueue(s); a=s.claim('op1','codex'); s.fail('op1','codex',a,'timeout')
    with pytest.raises(PermissionError, match='reconciliation_verifier_required'):
        s.reconcile('op1','succeeded',{'op_id':'op1','outcome':'succeeded','receipt':'untrusted'})
def test_reconcile_retry(env):
    s,_=env; enqueue(s); a=s.claim('op1','codex'); s.fail('op1','codex',a,'timeout')
    with pytest.raises(PermissionError, match='reconciliation_verifier_required'):
        s.reconcile('op1','pending',{'op_id':'op1','outcome':'pending','receipt':'untrusted'})
    assert s.claim('op1','claude') is None
def test_no_reconcile_without_evidence(env):
    s,_=env; enqueue(s)
    with pytest.raises(ValueError): s.reconcile('op1','pending','')
def test_bad_lease(env):
    s,_=env; enqueue(s)
    with pytest.raises(ValueError): s.claim('op1','',0)
def test_cannot_reconcile_pending(env):
    s,_=env
    enqueue(s)
    with pytest.raises(PermissionError, match='reconciliation_verifier_required'):
        s.reconcile('op1','succeeded',{'op_id':'op1','outcome':'succeeded'})

def test_verified_reconciliation_can_retry(env):
    s,t=env
    s.reconciliation_verifier=lambda op,out,e: (op=='op1' and out=='pending' and e.get('receipt')=='simulated_no_effect')
    enqueue(s); a=s.claim('op1','codex'); s.fail('op1','codex',a,'timeout')
    assert s.reconcile('op1','pending',{'op_id':'op1','outcome':'pending','receipt':'simulated_no_effect','nonce':'n-retry-1'})
    assert s.claim('op1','claude')==2

def test_wrong_binding_and_rejected_verifier(env):
    s,_=env; s.reconciliation_verifier=lambda *args: False
    enqueue(s); a=s.claim('op1','codex'); s.fail('op1','codex',a,'timeout')
    with pytest.raises(PermissionError,match='binding'):
        s.reconcile('op1','pending',{'op_id':'op2','outcome':'pending'})
    with pytest.raises(PermissionError,match='unverified'):
        s.reconcile('op1','pending',{'op_id':'op1','outcome':'pending','nonce':'n-truthy-1'})
    assert s.get('op1')['state']=='ambiguous'

def test_verifier_truthy_non_bool_rejected(env):
    s,_=env
    s.reconciliation_verifier=lambda *args: 1
    enqueue(s); a=s.claim('op1','codex'); s.fail('op1','codex',a,'timeout')
    with pytest.raises(PermissionError,match='unverified'):
        s.reconcile('op1','pending',{'op_id':'op1','outcome':'pending'})
    assert s.get('op1')['state']=='ambiguous'

def test_reconcile_only_ambiguous_state(env):
    s,_=env
    calls=[]
    s.reconciliation_verifier=lambda *args: calls.append(args) or True
    enqueue(s)
    assert s.reconcile('op1','succeeded',{'op_id':'op1','outcome':'succeeded','nonce':'n-not-ambiguous'}) is False
    assert s.get('op1')['state']=='pending'
    assert len(calls)==0

def test_expired_lease_not_finished_after_reconciliation(env):
    s,t=env
    s.reconciliation_verifier=lambda *args: True
    enqueue(s); attempt=s.claim('op1','codex',ttl=5)
    t[0]+=6
    assert s.expire('op1')
    assert s.reconcile('op1','pending',{'op_id':'op1','outcome':'pending','nonce':'n-expired-1'})
    assert not s.finish('op1','codex',attempt,{'ok':True})
    assert s.claim('op1','claude')==2

def test_reconcile_requires_nonce(env):
    s,_=env
    s.reconciliation_verifier=lambda *args: True
    enqueue(s); a=s.claim('op1','codex'); s.fail('op1','codex',a,'timeout')
    with pytest.raises(PermissionError,match='nonce_required'):
        s.reconcile('op1','pending',{'op_id':'op1','outcome':'pending'})
    assert s.get('op1')['state']=='ambiguous'

def test_nonce_replay_rejected_across_operations(env):
    s,_=env
    s.reconciliation_verifier=lambda *args: True
    enqueue(s); a=s.claim('op1','codex'); s.fail('op1','codex',a,'timeout')
    assert s.reconcile('op1','pending',{'op_id':'op1','outcome':'pending','nonce':'unique-1'})
    assert s.enqueue('op2','task2','read_status',{},'task2:read_status:v1')
    a2=s.claim('op2','claude'); s.fail('op2','claude',a2,'timeout')
    with pytest.raises(PermissionError,match='replayed_reconciliation'):
        s.reconcile('op2','pending',{'op_id':'op2','outcome':'pending','nonce':'unique-1'})
    assert s.get('op2')['state']=='ambiguous'

def test_verifier_rejection_does_not_consume_nonce(env):
    s,_=env
    s.reconciliation_verifier=lambda *args: False
    enqueue(s); a=s.claim('op1','codex'); s.fail('op1','codex',a,'timeout')
    evidence={'op_id':'op1','outcome':'pending','nonce':'n-reject-1'}
    with pytest.raises(PermissionError,match='unverified'):
        s.reconcile('op1','pending',evidence)
    s.reconciliation_verifier=lambda *args: True
    assert s.reconcile('op1','pending',evidence)

def test_nonce_persists_across_restart(env):
    s,_=env
    s.reconciliation_verifier=lambda *args: True
    enqueue(s); a=s.claim('op1','codex'); s.fail('op1','codex',a,'timeout')
    assert s.reconcile('op1','pending',{'op_id':'op1','outcome':'pending','nonce':'n-persist-1'})
    restarted=Outbox(s.path,clock=s.clock,reconciliation_verifier=lambda *args: True)
    restarted.enqueue('op2','task2','read_status',{},'task2:read_status:v1')
    a2=restarted.claim('op2','claude'); restarted.fail('op2','claude',a2,'timeout')
    with pytest.raises(PermissionError,match='replayed'):
        restarted.reconcile('op2','pending',{'op_id':'op2','outcome':'pending','nonce':'n-persist-1'})
