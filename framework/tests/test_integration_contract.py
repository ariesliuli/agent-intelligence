"""跨模块契约测试：仅模拟 SQLite，无外部设备。运行：cd framework && python -m pytest -q tests/test_integration_contract.py"""
import sqlite3
import pytest
from agent_core.store import Store
from agent_core.outbox import Outbox
from agent_core.atomic import AtomicIntentStore

@pytest.fixture
def parts(tmp_path):
    path=tmp_path/"integration.db"
    clock=lambda:100.0
    return path, Store(path,clock), Outbox(path,clock), AtomicIntentStore(path,clock)

def test_atomic_entrypoint_visible_to_both_existing_modules(parts):
    path,store,outbox,atomic=parts
    assert atomic.submit_with_operation("t",{"goal":"sim"},"op","read_status",{"target":"sim"},"t:read:v1")
    assert store.get("t")["status"]=="pending"
    assert outbox.get("op")["state"]=="pending"
    assert store.claim("t","worker-a",ttl=30)==1
    assert outbox.claim("op","worker-a",ttl=30)==1
    assert outbox.finish("op","worker-a",1,{"ok":True})
    assert store.write("t","worker-a",1,"result",{"ok":True})
    assert store.get("t")["status"]=="succeeded"

def test_ambiguous_never_auto_claimed(parts):
    path,store,outbox,atomic=parts
    atomic.submit_with_operation("t",{},"op","device_write",{},"t:write:v1")
    assert outbox.claim("op","worker-a",ttl=1)==1
    with sqlite3.connect(path) as db:
        db.execute("UPDATE operations SET lease_until=99 WHERE op_id='op'")
    assert outbox.expire("op")
    assert outbox.get("op")["state"]=="ambiguous"
    assert outbox.claim("op","worker-b",ttl=30) is None

def test_old_two_call_path_exposes_orphan_task(parts):
    path,store,outbox,atomic=parts
    assert store.submit("t",{"goal":"sim"})
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM operations").fetchone()[0]==0
    with pytest.raises(ValueError,match="intent_conflict"):
        atomic.submit_with_operation("t",{"goal":"sim"},"op","read_status",{},"t:read:v1")

def test_reconcile_requires_evidence_but_not_authentication_yet(parts):
    _,_,outbox,atomic=parts
    atomic.submit_with_operation("t",{},"op","device_write",{},"t:write:v1")
    assert outbox.claim("op","worker-a",ttl=1)==1
    assert outbox.fail("op","worker-a",1,"timeout")
    with pytest.raises(ValueError,match="invalid_reconciliation"):
        outbox.reconcile("op","pending","")
    assert outbox.get("op")["state"]=="ambiguous"
    # Demonstrates security gap: arbitrary nonempty evidence currently accepted.
    assert outbox.reconcile("op","pending","unverified-string")
