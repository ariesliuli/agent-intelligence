from agent_core.router import Task, Worker, route

def worker(name, available=True, units=10, quality=0.9, perms=('read',), caps=('python',)):
    return Worker(name, caps, available, units, 1.0, quality, perms)

def task(risk='low', tools=('read',), independent=False):
    return Task('T-001', '只读状态查询', risk, ('python',), tools, independent)

def test_codex_exhausted():
    assert route(task(), [worker('codex', units=0), worker('claude')]).executor == 'claude'

def test_claude_exhausted():
    assert route(task(), [worker('claude', units=0), worker('codex')]).executor == 'codex'

def test_both_available():
    assert route(task(), [worker('claude', quality=0.8), worker('codex')]).executor == 'codex'

def test_both_exhausted():
    assert route(task(), [worker('claude', units=0), worker('codex', units=0)]).status == 'blocked'

def test_permission_denied():
    assert route(task(tools=('reboot',)), [worker('codex')]).status == 'blocked'

def test_high_risk_single():
    assert route(task(risk='high'), [worker('codex')]).status == 'approval_required'

def test_high_risk_two():
    d = route(task(risk='high'), [worker('codex'), worker('claude', quality=0.8)])
    assert (d.executor, d.verifier) == ('codex', 'claude')

def test_unavailable():
    assert route(task(), [worker('codex', available=False), worker('claude')]).executor == 'claude'

def test_missing_capability():
    assert route(task(), [worker('codex', caps=('research',))]).status == 'blocked'

def test_independent_verifier():
    d = route(task(independent=True), [worker('codex'), worker('claude')])
    assert d.status == 'ready' and d.executor != d.verifier
