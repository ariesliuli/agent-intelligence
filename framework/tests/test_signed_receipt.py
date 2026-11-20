"""纯合成数据：签名认证边界测试，不代表真实设备可信回执。"""
import hashlib
import hmac
import json
import pytest
from agent_core.signed_receipt import verify_signed_receipt

KEY = b"synthetic-test-key-not-for-production!!"
def envelope(body=None):
    b = dict(issuer="simulator", receipt_id="r-1", op_id="op-1", outcome="pending",
             issued_at=90, expires_at=110, payload_digest="sha256:synthetic")
    if body: b.update(body)
    mac = hmac.new(KEY, json.dumps(b, sort_keys=True, ensure_ascii=False,
                  separators=(",", ":"), allow_nan=False).encode(), hashlib.sha256).hexdigest()
    return {"body": b, "alg": "HS256", "mac": mac}

def verify(e, **kwargs):
    return verify_signed_receipt(e, keys={"simulator": KEY}, op_id="op-1",
                                 outcome="pending", payload_digest="sha256:synthetic", now=100, **kwargs)

def test_valid_synthetic_signature():
    assert verify(envelope()).receipt_id == "r-1"

@pytest.mark.parametrize("change", [
    {"op_id":"op-2"}, {"outcome":"succeeded"},
    {"expires_at":99}, {"issued_at":107}, {"payload_digest":"sha256:other"}
])
def test_signed_but_wrong_binding_rejected(change):
    with pytest.raises(PermissionError):
        verify(envelope(change))

def test_new_receipt_id_with_valid_signature_is_distinct_valid_receipt():
    # Authentication binds the receipt ID into the signature; it does not pin it to r-1.
    assert verify(envelope({"receipt_id": "r-2"})).receipt_id == "r-2"

def test_unsigned_mutation_rejected():
    e=envelope(); e["body"]["receipt_id"]="r-2"
    with pytest.raises(PermissionError, match="invalid_signature"):
        verify(e)

def test_unknown_issuer_rejected():
    with pytest.raises(PermissionError, match="unknown_issuer"):
        verify(envelope({"issuer":"unknown"}))

def test_algorithm_downgrade_rejected():
    e=envelope(); e["alg"]="none"
    with pytest.raises(PermissionError, match="unsupported_receipt_format"):
        verify(e)

def test_payload_context_rejected():
    with pytest.raises(PermissionError, match="payload_binding_mismatch"):
        verify_signed_receipt(envelope(), keys={"simulator": KEY}, op_id="op-1",
            outcome="pending", payload_digest="sha256:different", now=100)

@pytest.mark.parametrize("bad_digest", [None, 17, False, [], {"x": 1}])
def test_signed_malformed_digest_fails_closed(bad_digest):
    # A valid MAC over malformed data must not escape as TypeError.
    with pytest.raises(PermissionError, match="invalid_payload_digest"):
        verify(envelope({"payload_digest": bad_digest}))

def test_invalid_keyring_fails_closed():
    with pytest.raises(PermissionError, match="invalid_keyring"):
        verify_signed_receipt(envelope(), keys=None, op_id="op-1",
            outcome="pending", payload_digest="sha256:synthetic", now=100)

@pytest.mark.parametrize("bad_identity", [None, 0, [], {"x": 1}])
def test_signed_malformed_operation_identity_fails_closed(bad_identity):
    with pytest.raises(PermissionError):
        verify(envelope({"op_id": bad_identity}))
