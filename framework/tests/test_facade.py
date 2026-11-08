import pytest
from agent_core.facade import IntentFacade

def request(**updates):
    d = dict(task_id="t1", task_payload={"goal":"simulation"}, op_id="o1", action="read_status", op_payload={"target":"sim"}, idempotency_key="t1:read:v1")
    d.update(updates)
    return d

def test_atomic_and_idempotent(tmp_path):
    f = IntentFacade(tmp_path/"test.db")
    assert f.submit(request()) is True
    assert f.submit(request()) is False
    assert f.atomic.counts() == (1, 1, 1)
    assert f.integrity() == {"orphan_operations":0,"tasks_without_operations":0}

def test_conflict(tmp_path):
    f = IntentFacade(tmp_path/"test.db")
    f.submit(request())
    with pytest.raises(ValueError, match="intent_conflict"):
        f.submit(request(op_payload={"target":"other"}))
    assert f.atomic.counts() == (1,1,1)

def test_fail_closed(tmp_path):
    with pytest.raises(ValueError, match="external_writes_not_supported"):
        IntentFacade(tmp_path/"test.db", external_writes_enabled=True)
    f = IntentFacade(tmp_path/"test.db")
    with pytest.raises(PermissionError, match="action_not_allowlisted"):
        f.submit(request(action="device_reboot"))
    assert f.atomic.counts() == (0,0,0)

def test_schema_rejection(tmp_path):
    f = IntentFacade(tmp_path/"test.db")
    with pytest.raises(ValueError, match="invalid_fields"):
        f.submit(dict(request(), unexpected="x"))
    with pytest.raises(ValueError, match="invalid_payload"):
        f.submit(request(op_payload="string"))
    assert f.atomic.counts() == (0,0,0)
