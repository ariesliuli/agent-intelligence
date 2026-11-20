"""离线 HMAC 回执认证适配器（模拟信任域）；不接入 Outbox，也不执行远端 IO。"""
import hashlib
import hmac
import json
from typing import Mapping
from agent_core.receipt_gate import VerifiedReceipt, validate_receipt

_FIELDS = ("issuer", "receipt_id", "op_id", "outcome", "issued_at", "expires_at", "payload_digest")
def _canonical(body):
    return json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")

def verify_signed_receipt(envelope: Mapping, *, keys: Mapping[str, bytes], op_id: str,
                          outcome: str, payload_digest: str, now: float) -> VerifiedReceipt:
    """输入 envelope={body:{...},alg:'HS256',mac:'hex'}；仅用于受控模拟/共享密钥信任域。"""
    if not isinstance(envelope, dict) or set(envelope) != {"body", "alg", "mac"}:
        raise PermissionError("invalid_envelope")
    body = envelope["body"]
    if not isinstance(body, dict) or set(body) != set(_FIELDS) or envelope["alg"] != "HS256":
        raise PermissionError("unsupported_receipt_format")
    issuer = body.get("issuer")
    if not isinstance(keys, Mapping):
        raise PermissionError("invalid_keyring")
    key = keys.get(issuer) if isinstance(issuer, str) else None
    if not isinstance(key, bytes) or len(key) < 32:
        raise PermissionError("unknown_issuer")
    mac = envelope["mac"]
    if not isinstance(mac, str) or len(mac) != 64 or any(c not in "0123456789abcdef" for c in mac):
        raise PermissionError("invalid_mac")
    try:
        expected = hmac.new(key, _canonical(body), hashlib.sha256).hexdigest()
    except (TypeError, ValueError, OverflowError) as exc:
        raise PermissionError("invalid_body") from exc
    if not hmac.compare_digest(expected, mac):
        raise PermissionError("invalid_signature")
    # Reject malformed signed fields before calling compare_digest (which requires strings).
    if not isinstance(body["payload_digest"], str) or not isinstance(payload_digest, str):
        raise PermissionError("invalid_payload_digest")
    if not hmac.compare_digest(body["payload_digest"], payload_digest):
        raise PermissionError("payload_binding_mismatch")
    try:
        receipt = VerifiedReceipt(**body)
        validate_receipt(receipt, op_id, outcome, now)
    except (TypeError, ValueError) as exc:
        raise PermissionError("invalid_receipt") from exc
    return receipt
