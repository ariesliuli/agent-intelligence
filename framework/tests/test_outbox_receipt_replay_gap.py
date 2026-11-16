"""Known security gap: receipt_id replay with fresh nonces across operations.

Expected failure is documented until a trusted receipt identity gate exists.
No real remote calls or secrets.
"""
import pytest
from agent_core.outbox import Outbox


def _ambiguous(box, op_id):
    assert box.enqueue(op_id, op_id, "simulated_read", {}, op_id + ":read:v1")
    attempt = box.claim(op_id, "simulator")
    assert box.fail(op_id, "simulator", attempt, "simulated_timeout")


@pytest.mark.xfail(
    strict=True,
    reason="receipt_id uniqueness is not enforced; distinct nonce can replay one receipt",
)
def test_same_receipt_id_different_nonce_must_not_authorize_second_operation(tmp_path):
    box = Outbox(
        tmp_path / "receipt-gap.sqlite3",
        clock=lambda: 100.0,
        reconciliation_verifier=lambda *args: True,  # simulation ONLY
    )
    _ambiguous(box, "op-a")
    _ambiguous(box, "op-b")
    first = {"op_id": "op-a", "outcome": "pending", "nonce": "nonce-a", "receipt_id": "receipt-1"}
    second = {"op_id": "op-b", "outcome": "pending", "nonce": "nonce-b", "receipt_id": "receipt-1"}
    assert box.reconcile("op-a", "pending", first) is True
    with pytest.raises(PermissionError, match="replayed_receipt"):
        box.reconcile("op-b", "pending", second)
    assert box.get("op-b")["state"] == "ambiguous"
