"""SQLite 签名回执并发、锁冲突和重启持久化；仅合成数据。"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import json
import sqlite3
import threading

import pytest

from agent_core.outbox import Outbox

KEY = b"synthetic-test-key-not-for-production!!"


def prepare(path):
    store = Outbox(path, clock=lambda: 100.0)
    assert store.enqueue("op1", "task1", "device_write", {"sim": 1}, "task1:write:v1")
    attempt = store.claim("op1", "worker")
    assert store.fail("op1", "worker", attempt, "simulated_timeout")
    return store


def envelope(store, receipt_id="r1"):
    with sqlite3.connect(store.path) as db:
        payload = db.execute("SELECT payload FROM operations WHERE op_id='op1'").fetchone()[0]
    body = {
        "issuer": "simulator", "receipt_id": receipt_id,
        "op_id": "op1", "outcome": "pending",
        "issued_at": 90, "expires_at": 110,
        "payload_digest": "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    }
    mac = hmac.new(KEY, json.dumps(body, sort_keys=True, ensure_ascii=False,
                                   separators=(",", ":"), allow_nan=False).encode(),
                   hashlib.sha256).hexdigest()
    return {"alg": "HS256", "body": body, "mac": mac}


def snapshot(store):
    with sqlite3.connect(store.path) as db:
        return (
            db.execute("SELECT state FROM operations WHERE op_id='op1'").fetchone()[0],
            db.execute("SELECT COUNT(*) FROM reconciliation_receipts").fetchone()[0],
        )


def test_concurrent_same_receipt_at_most_once(tmp_path):
    store = prepare(tmp_path / "concurrent.db")
    signed = envelope(store)
    workers = 8
    barrier = threading.Barrier(workers)

    def reconcile(_):
        local = Outbox(store.path, clock=lambda: 100.0)
        barrier.wait(timeout=10)
        return local.reconcile_signed("op1", "pending", signed, keys={"simulator": KEY})

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(reconcile, range(workers)))
    assert results.count(True) == 1
    assert results.count(False) == workers - 1
    assert snapshot(store) == ("pending", 1)


def test_restart_preserves_receipt_consumption(tmp_path):
    path = tmp_path / "restart.db"
    store = prepare(path)
    signed = envelope(store)
    assert store.reconcile_signed("op1", "pending", signed, keys={"simulator": KEY})
    restarted = Outbox(path, clock=lambda: 100.0)
    assert snapshot(restarted) == ("pending", 1)
    assert restarted.reconcile_signed("op1", "pending", signed, keys={"simulator": KEY}) is False
    assert snapshot(restarted) == ("pending", 1)


def test_sqlite_lock_timeout_does_not_consume_receipt(tmp_path):
    store = prepare(tmp_path / "locked.db")
    signed = envelope(store)
    locker = sqlite3.connect(store.path, timeout=1, isolation_level=None)
    try:
        locker.execute("BEGIN IMMEDIATE")
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            store.reconcile_signed("op1", "pending", signed, keys={"simulator": KEY})
    finally:
        locker.rollback()
        locker.close()
    assert snapshot(store) == ("ambiguous", 0)
    assert store.reconcile_signed("op1", "pending", signed, keys={"simulator": KEY})
    assert snapshot(store) == ("pending", 1)
