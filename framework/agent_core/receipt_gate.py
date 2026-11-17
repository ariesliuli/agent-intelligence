"""离线回执身份门禁原型；仅接受独立验签后产生的对象，尚未接入 Outbox。"""
from dataclasses import dataclass
import sqlite3
import time

@dataclass(frozen=True)
class VerifiedReceipt:
    issuer: str
    receipt_id: str
    op_id: str
    outcome: str
    issued_at: float
    expires_at: float
    payload_digest: str

def validate_receipt(receipt: VerifiedReceipt, op_id: str, outcome: str, now: float, skew: float = 5.0) -> None:
    if type(receipt) is not VerifiedReceipt:
        raise PermissionError("authenticated_receipt_required")
    if not all(isinstance(x, str) and x.strip() and len(x) <= 256 for x in (
        receipt.issuer, receipt.receipt_id, receipt.op_id, receipt.outcome, receipt.payload_digest
    )):
        raise PermissionError("invalid_receipt_identity")
    if receipt.op_id != op_id or receipt.outcome != outcome or outcome not in ("pending", "succeeded", "failed"):
        raise PermissionError("receipt_binding_mismatch")
    if not all(isinstance(x, (int, float)) and not isinstance(x, bool) and abs(x) < 1e15 for x in (
        receipt.issued_at, receipt.expires_at, now, skew
    )):
        raise PermissionError("invalid_receipt_time")
    if skew < 0 or receipt.expires_at <= receipt.issued_at or now > receipt.expires_at or receipt.issued_at > now + skew:
        raise PermissionError("receipt_expired_or_future")

def create_receipt_table(db: sqlite3.Connection) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS reconciliation_receipts(
        issuer TEXT NOT NULL, receipt_id TEXT NOT NULL, op_id TEXT NOT NULL,
        outcome TEXT NOT NULL, consumed_at REAL NOT NULL,
        PRIMARY KEY(issuer, receipt_id))""")

def consume_verified_receipt(db: sqlite3.Connection, receipt: VerifiedReceipt, op_id: str, outcome: str, now: float) -> None:
    """调用者须先独立验签，并在 BEGIN IMMEDIATE 事务内调用；不负责 commit。"""
    validate_receipt(receipt, op_id, outcome, now)
    try:
        db.execute("INSERT INTO reconciliation_receipts VALUES(?,?,?,?,?)",
                   (receipt.issuer, receipt.receipt_id, receipt.op_id, receipt.outcome, now))
    except sqlite3.IntegrityError as exc:
        raise PermissionError("replayed_receipt") from exc
