"""多进程 SQLite Outbox 核对竞争：离线模拟，无网络、无真实设备。"""
import multiprocessing as mp
import sqlite3

import pytest
from agent_core.outbox import Outbox


def _verifier(op_id, outcome, evidence):
    # 只用于模拟数据库竞争；不是生产可信验证器。
    return True


def _worker(db_path, ready, start, results, nonce):
    try:
        box = Outbox(db_path, clock=lambda: 100.0, reconciliation_verifier=_verifier)
        ready.put("ready")
        if not start.wait(timeout=15):
            results.put(("error", "start_timeout"))
            return
        ok = box.reconcile("op1", "pending", {
            "op_id": "op1", "outcome": "pending", "nonce": nonce
        })
        results.put(("ok", ok))
    except Exception as exc:
        results.put(("error", type(exc).__name__ + ":" + str(exc)))


def _ambiguous(db_path):
    box = Outbox(db_path, clock=lambda: 100.0, reconciliation_verifier=_verifier)
    assert box.enqueue("op1", "task1", "simulated_read", {}, "task1:read:v1")
    attempt = box.claim("op1", "worker")
    assert attempt == 1
    assert box.fail("op1", "worker", attempt, "simulated_timeout")
    return box


@pytest.mark.parametrize("round_no", range(20))
def test_two_spawned_processes_cannot_both_reconcile(tmp_path, round_no):
    """跨进程真实 SQLite 文件锁；20 次独立数据库重复，避免仅线程级验证。"""
    path = str(tmp_path / f"race-{round_no}.sqlite3")
    box = _ambiguous(path)
    ctx = mp.get_context("spawn")
    ready = ctx.Queue()
    results = ctx.Queue()
    start = ctx.Event()
    processes = [
        ctx.Process(target=_worker, args=(path, ready, start, results, f"nonce-{round_no}"))
        for _ in range(2)
    ]
    try:
        for p in processes:
            p.start()
        assert [ready.get(timeout=15) for _ in processes] == ["ready", "ready"]
        start.set()
        outcomes = [results.get(timeout=20) for _ in processes]
        assert sorted(outcomes, key=str) == [("ok", False), ("ok", True)]
        assert box.get("op1")["state"] == "pending"
        with sqlite3.connect(path) as db:
            assert db.execute(
                "SELECT COUNT(*) FROM reconciliation_nonces WHERE nonce=?",
                (f"nonce-{round_no}",)
            ).fetchone()[0] == 1
    finally:
        start.set()
        for p in processes:
            p.join(timeout=5)
            if p.is_alive():
                p.terminate()
                p.join(timeout=5)
        assert all(p.exitcode == 0 for p in processes)
