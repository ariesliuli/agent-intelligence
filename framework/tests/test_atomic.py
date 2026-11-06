import sqlite3
import pytest
from agent_core.atomic import AtomicIntentStore

@pytest.fixture
def store(tmp_path):
    return AtomicIntentStore(tmp_path/'test.db',clock=lambda:100.0)

def submit(s,**kw):
    return s.submit_with_operation('t1',{'goal':'simulate'},'o1','read_status',{'device':'sim'},'t1:read:v1',**kw)

def test_atomic_commit(store):
    assert submit(store) is True
    assert store.counts()==(1,1,1)

def test_duplicate_noop(store):
    submit(store)
    assert submit(store) is False
    assert store.counts()==(1,1,1)

def test_failure_rolls_back_everything(store):
    with pytest.raises(RuntimeError): submit(store,inject_failure=True)
    assert store.counts()==(0,0,0)
    assert submit(store) is True

def test_conflicting_task(store):
    submit(store)
    with pytest.raises(ValueError,match='intent_conflict'):
        store.submit_with_operation('t1',{'goal':'different'},'o1','read_status',{'device':'sim'},'t1:read:v1')
    assert store.counts()==(1,1,1)

def test_conflicting_key(store):
    submit(store)
    with pytest.raises(ValueError,match='intent_conflict'):
        store.submit_with_operation('t2',{},'o2','read_status',{},'t1:read:v1')
    assert store.counts()==(1,1,1)

def test_invalid_identity(store):
    with pytest.raises(ValueError,match='invalid_identity'):
        store.submit_with_operation('',{},'o1','read',{},'key')
    assert store.counts()==(0,0,0)

def test_preexisting_task_no_operation_blocks(store):
    with sqlite3.connect(store.path) as db:
        db.execute("INSERT INTO tasks(id,payload,status) VALUES('t1','{}','pending')")
    with pytest.raises(ValueError,match='intent_conflict'): submit(store)
    assert store.counts()==(1,0,0)

def test_preexisting_operation_no_task_blocks(store):
    with sqlite3.connect(store.path) as db:
        db.execute("INSERT INTO operations(op_id,task_id,action,payload,idempotency_key,state,created_at,updated_at) VALUES('o1','t1','read_status','{}','t1:read:v1','pending',0,0)")
    with pytest.raises(ValueError,match='intent_conflict'): submit(store)
    assert store.counts()==(0,1,0)
