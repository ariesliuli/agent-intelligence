"""离线 SQLite 进程强制退出测试；只使用合成签名和临时数据库。"""
import hashlib
import hmac
import json
import os
import sqlite3
import subprocess
import sys

from agent_core.outbox import Outbox

KEY = b"synthetic-test-key-not-for-production!!"


def _prepare(path):
    store = Outbox(path, clock=lambda: 100.0)
    assert store.enqueue("op1", "task1", "device_write", {"sim": 1}, "task1:write:v1")
    attempt = store.claim("op1", "worker")
    assert store.fail("op1", "worker", attempt, "simulated_timeout")
    return store


def _signed(store):
    with sqlite3.connect(store.path) as db:
        payload = db.execute("SELECT payload FROM operations WHERE op_id='op1'").fetchone()[0]
    body = {
        "issuer": "simulator", "receipt_id": "r1", "op_id": "op1",
        "outcome": "pending", "issued_at": 90, "expires_at": 110,
        "payload_digest": "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    }
    mac = hmac.new(KEY, json.dumps(body, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode("utf-8"),
                   hashlib.sha256).hexdigest()
    return {"alg": "HS256", "body": body, "mac": mac}


def _snapshot(path):
    with sqlite3.connect(path) as db:
        return (
            db.execute("SELECT state FROM operations WHERE op_id='op1'").fetchone()[0],
            db.execute("SELECT COUNT(*) FROM reconciliation_receipts").fetchone()[0],
        )


def _child(path, mode, envelope):
    # New Python interpreter, not a shared SQLite connection or a thread.
    script = """
import json, os, sqlite3, sys
from agent_core.outbox import Outbox
from agent_core.receipt_gate import consume_verified_receipt
from agent_core.signed_receipt import verify_signed_receipt
store = Outbox(sys.argv[1], clock=lambda: 100.0)
mode = sys.argv[2]
envelope = json.loads(sys.argv[3])
keys = {"simulator": b"synthetic-test-key-not-for-production!!"}
if mode == "before_commit":
    # Exit after receipt INSERT, before operation UPDATE/COMMIT.
    with store._tx() as db:
        receipt = verify_signed_receipt(
            envelope, keys=keys, op_id="op1", outcome="pending",
            payload_digest=envelope["body"]["payload_digest"], now=100.0)
        consume_verified_receipt(db, receipt, "op1", "pending", 100.0)
        os._exit(23)
elif mode == "after_commit":
    assert store.reconcile_signed("op1", "pending", envelope, keys=keys)
    os._exit(24)
else:
    raise ValueError("unknown_mode")
"""
    return subprocess.run(
        [sys.executable, "-c", script, str(path), mode, json.dumps(envelope)],
        capture_output=True, text=True, timeout=15, check=False,
    )


def test_process_exit_before_commit_rolls_back_receipt_and_state(tmp_path):
    path = tmp_path / "before.db"
    store = _prepare(path)
    envelope = _signed(store)
    child = _child(path, "before_commit", envelope)
    assert child.returncode == 23, child.stderr
    assert _snapshot(path) == ("ambiguous", 0)
    restarted = Outbox(path, clock=lambda: 100.0)
    assert restarted.reconcile_signed("op1", "pending", envelope, keys={"simulator": KEY})
    assert _snapshot(path) == ("pending", 1)


def test_process_exit_after_commit_preserves_receipt_and_state(tmp_path):
    path = tmp_path / "after.db"
    store = _prepare(path)
    envelope = _signed(store)
    child = _child(path, "after_commit", envelope)
    assert child.returncode == 24, child.stderr
    restarted = Outbox(path, clock=lambda: 100.0)
    assert _snapshot(path) == ("pending", 1)
    assert restarted.reconcile_signed("op1", "pending", envelope, keys={"simulator": KEY}) is False
    assert _snapshot(path) == ("pending", 1)
