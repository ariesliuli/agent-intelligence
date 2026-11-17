"""只验证本地身份/事务门禁；不模拟真实签名认证。"""
import sqlite3
import pytest
from agent_core.receipt_gate import VerifiedReceipt, create_receipt_table, consume_verified_receipt

def receipt(**changes):
    data = dict(issuer="test-issuer", receipt_id="r1", op_id="op-a", outcome="pending",
                issued_at=90.0, expires_at=110.0, payload_digest="sha256:test")
    data.update(changes)
    return VerifiedReceipt(**data)

def test_replay_across_nonce_and_operations(tmp_path):
    with sqlite3.connect(tmp_path / "a.db") as db:
        create_receipt_table(db)
        db.execute("BEGIN IMMEDIATE")
        consume_verified_receipt(db, receipt(), "op-a", "pending", 100)
        db.commit()
        with pytest.raises(PermissionError, match="replayed_receipt"):
            consume_verified_receipt(db, receipt(op_id="op-b"), "op-b", "pending", 100)
        assert db.execute("SELECT COUNT(*) FROM reconciliation_receipts").fetchone()[0] == 1

@pytest.mark.parametrize("bad,op,outcome,now", [
    ({"expires_at":99}, "op-a", "pending", 100),
    ({"issued_at":107}, "op-a", "pending", 100),
    ({"op_id":"other"}, "op-a", "pending", 100),
    ({"outcome":"succeeded"}, "op-a", "pending", 100),
    ({"receipt_id":""}, "op-a", "pending", 100),
    ({"expires_at":float("nan")}, "op-a", "pending", 100),
])
def test_invalid_receipts_fail_closed(tmp_path,bad,op,outcome,now):
    with sqlite3.connect(tmp_path / "a.db") as db:
        create_receipt_table(db)
        with pytest.raises(PermissionError):
            consume_verified_receipt(db, receipt(**bad), op, outcome, now)
        assert db.execute("SELECT COUNT(*) FROM reconciliation_receipts").fetchone()[0] == 0

def test_issuer_namespace_and_rollback(tmp_path):
    with sqlite3.connect(tmp_path / "a.db") as db:
        create_receipt_table(db)
        with pytest.raises(RuntimeError):
            with db:
                consume_verified_receipt(db, receipt(), "op-a", "pending", 100)
                raise RuntimeError("injected_failure")
        assert db.execute("SELECT COUNT(*) FROM reconciliation_receipts").fetchone()[0] == 0
        with db:
            consume_verified_receipt(db, receipt(), "op-a", "pending", 100)
            consume_verified_receipt(db, receipt(issuer="another"), "op-a", "pending", 100)
        assert db.execute("SELECT COUNT(*) FROM reconciliation_receipts").fetchone()[0] == 2
