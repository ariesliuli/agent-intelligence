"""并发核对与事务回滚的离线回归测试；不连接设备或网络。"""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import sqlite3

import pytest
from agent_core.outbox import Outbox


def ambiguous(db_path, verifier):
    box = Outbox(db_path, clock=lambda: 100.0, reconciliation_verifier=verifier)
    box.enqueue("op1", "task1", "simulated_read", {}, "task1:simulated_read:v1")
    attempt = box.claim("op1", "worker")
    assert box.fail("op1", "worker", attempt, "simulated_timeout")
    return box


def test_concurrent_reconcile_same_nonce_only_one_wins(tmp_path):
    path = tmp_path / "outbox.db"
    verifier = lambda op, outcome, evidence: True  # 仅限模拟测试，绝不可用于生产
    box = ambiguous(path, verifier)
    barrier = Barrier(2)

    def worker():
        local = Outbox(path, clock=lambda: 100.0, reconciliation_verifier=verifier)
        barrier.wait(timeout=5)
        return local.reconcile("op1", "pending", {
            "op_id": "op1", "outcome": "pending", "nonce": "race-1"
        })

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: worker(), range(2)))
    assert sorted(results) == [False, True]
    assert box.get("op1")["state"] == "pending"
    with sqlite3.connect(path) as db:
        assert db.execute(
            "SELECT COUNT(*) FROM reconciliation_nonces WHERE nonce='race-1'"
        ).fetchone()[0] == 1


def test_nonce_insert_rolls_back_when_state_update_aborts(tmp_path):
    path = tmp_path / "outbox.db"
    box = ambiguous(path, lambda *args: True)  # 仅模拟
    with sqlite3.connect(path) as db:
        db.execute("""
            CREATE TRIGGER block_reconcile
            BEFORE UPDATE OF state ON operations
            WHEN NEW.state='pending' AND OLD.state='ambiguous'
            BEGIN SELECT RAISE(ABORT, 'injected_failure'); END
        """)
    evidence = {"op_id": "op1", "outcome": "pending", "nonce": "rollback-1"}
    with pytest.raises(sqlite3.IntegrityError, match="injected_failure"):
        box.reconcile("op1", "pending", evidence)
    assert box.get("op1")["state"] == "ambiguous"
    with sqlite3.connect(path) as db:
        assert db.execute(
            "SELECT COUNT(*) FROM reconciliation_nonces WHERE nonce='rollback-1'"
        ).fetchone()[0] == 0
        db.execute("DROP TRIGGER block_reconcile")
    assert box.reconcile("op1", "pending", evidence) is True
