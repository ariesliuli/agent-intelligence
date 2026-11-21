"""离线签名回执与 Outbox 同事务模拟；非生产设备事实证明。"""
import hashlib
import hmac
import json
import sqlite3
import pytest
from agent_core.outbox import Outbox

KEY = b"synthetic-test-key-not-for-production!!"

def setup(tmp_path):
    s = Outbox(tmp_path / "atomic.db", clock=lambda: 100.0)
    assert s.enqueue("op1", "task1", "device_write", {"sim": 1}, "task1:write:v1")
    attempt = s.claim("op1", "simulator")
    assert s.fail("op1", "simulator", attempt, "timeout")
    return s

def signed(s, *, op="op1", rid="r1", outcome="pending", digest=None):
    with sqlite3.connect(s.path) as db:
        payload = db.execute("SELECT payload FROM operations WHERE op_id=?", (op,)).fetchone()[0]
    body = {"issuer":"simulator", "receipt_id":rid, "op_id":op,
            "outcome":outcome, "issued_at":90, "expires_at":110,
            "payload_digest":digest or "sha256:"+hashlib.sha256(payload.encode()).hexdigest()}
    mac = hmac.new(KEY, json.dumps(body,sort_keys=True,ensure_ascii=False,
                    separators=(",",":"),allow_nan=False).encode(),hashlib.sha256).hexdigest()
    return {"alg":"HS256","body":body,"mac":mac}

def counts(s):
    with sqlite3.connect(s.path) as db:
        return (db.execute("SELECT count(*) FROM reconciliation_receipts").fetchone()[0],
                db.execute("SELECT state FROM operations WHERE op_id='op1'").fetchone()[0])

def test_valid_signed_reconciliation_atomic(tmp_path):
    s=setup(tmp_path)
    assert s.reconcile_signed("op1","pending",signed(s),keys={"simulator":KEY})
    assert counts(s)==(1,"pending")
    assert s.claim("op1","worker2")==2

def test_unsigned_mutation_rejected_without_consumption(tmp_path):
    s=setup(tmp_path); e=signed(s); e["body"]["receipt_id"]="tampered"
    with pytest.raises(PermissionError,match="invalid_signature"):
        s.reconcile_signed("op1","pending",e,keys={"simulator":KEY})
    assert counts(s)==(0,"ambiguous")

def test_wrong_payload_digest_rejected(tmp_path):
    s=setup(tmp_path); e=signed(s,digest="sha256:wrong")
    with pytest.raises(PermissionError,match="payload_binding_mismatch"):
        s.reconcile_signed("op1","pending",e,keys={"simulator":KEY})
    assert counts(s)==(0,"ambiguous")

def test_invalid_keyring_rejected(tmp_path):
    s=setup(tmp_path)
    with pytest.raises(PermissionError,match="invalid_keyring"):
        s.reconcile_signed("op1","pending",signed(s),keys=None)
    assert counts(s)==(0,"ambiguous")

def test_duplicate_receipt_across_operations_rejected(tmp_path):
    s=setup(tmp_path); e=signed(s)
    assert s.reconcile_signed("op1","pending",e,keys={"simulator":KEY})
    assert s.enqueue("op2","task2","device_write",{"sim":2},"task2:write:v1")
    a=s.claim("op2","simulator"); assert s.fail("op2","simulator",a,"timeout")
    with pytest.raises(PermissionError,match="replayed_receipt"):
        s.reconcile_signed("op2","pending",signed(s,op="op2"),keys={"simulator":KEY})
    assert s.get("op2")["state"]=="ambiguous"

def test_transaction_rollback_if_state_update_fails(tmp_path):
    s=setup(tmp_path)
    with sqlite3.connect(s.path) as db:
        db.execute("""CREATE TRIGGER reject_reconcile BEFORE UPDATE OF state ON operations
                      WHEN NEW.state='pending' BEGIN SELECT RAISE(ABORT,'simulated crash'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        s.reconcile_signed("op1","pending",signed(s),keys={"simulator":KEY})
    assert counts(s)==(0,"ambiguous")
    with sqlite3.connect(s.path) as db:
        db.execute("DROP TRIGGER reject_reconcile")
    assert s.reconcile_signed("op1","pending",signed(s),keys={"simulator":KEY})
    assert counts(s)==(1,"pending")

def test_no_reconcile_before_ambiguous(tmp_path):
    s=Outbox(tmp_path/"pending.db",clock=lambda:100.0)
    s.enqueue("op1","task1","device_write",{"sim":1},"task1:write:v1")
    assert s.reconcile_signed("op1","pending",signed(s),keys={"simulator":KEY}) is False
    assert counts(s)==(0,"pending")
