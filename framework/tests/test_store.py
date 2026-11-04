import pytest
from agent_core.store import Store

@pytest.fixture
def env(tmp_path):
    t=[100.]
    return Store(tmp_path/'test.db',clock=lambda:t[0]),t

def test_idempotent(env):
    s,_=env;assert s.submit('a',{'x':1});assert not s.submit('a',{'x':1})
def test_conflict(env):
    s,_=env;s.submit('a',{'x':1})
    with pytest.raises(ValueError):s.submit('a',{'x':2})
def test_claim(env):
    s,_=env;s.submit('a',{});assert s.claim('a','w')==1
def test_double_claim(env):
    s,_=env;s.submit('a',{});s.claim('a','w');assert s.claim('a','w2') is None
def test_reclaim(env):
    s,t=env;s.submit('a',{});s.claim('a','w',10);t[0]+=11;assert s.claim('a','w2',10)==2
def test_fencing(env):
    s,t=env;s.submit('a',{});s.claim('a','w',10);t[0]+=11;s.claim('a','w2',10)
    assert not s.write('a','w',1,'result',{});assert s.write('a','w2',2,'result',{})
def test_checkpoint(env):
    s,_=env;s.submit('a',{});s.claim('a','w');assert s.write('a','w',1,'checkpoint',{'step':1})
def test_expired_write(env):
    s,t=env;s.submit('a',{});s.claim('a','w',10);t[0]+=11;assert not s.write('a','w',1,'checkpoint',{})
def test_attempt_limit(env):
    s,t=env;s.submit('a',{});s.claim('a','w',10,1);t[0]+=11
    assert s.claim('a','w2',10,1) is None;assert s.get('a')['status']=='failed'
def test_missing(env):
    s,_=env;assert s.claim('missing','w') is None
def test_invalid(env):
    s,_=env
    with pytest.raises(ValueError):s.claim('a','',0)
def test_terminal(env):
    s,t=env;s.submit('a',{});s.claim('a','w',10);s.write('a','w',1,'result',{});t[0]+=11
    assert s.claim('a','w2') is None
