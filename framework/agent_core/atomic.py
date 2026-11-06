"""任务与 Outbox 意图原子提交。Python 3.10+，仅 SQLite。"""
import json, sqlite3, time

class AtomicIntentStore:
    def __init__(self, path, clock=None):
        self.path=str(path); self.clock=clock or time.time
        with sqlite3.connect(self.path) as db:
            db.executescript("""CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,payload TEXT NOT NULL,status TEXT NOT NULL,attempt INTEGER NOT NULL DEFAULT 0,owner TEXT,lease REAL,checkpoint TEXT,result TEXT);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,task_id TEXT,event TEXT,at REAL);
CREATE TABLE IF NOT EXISTS operations(op_id TEXT PRIMARY KEY,task_id TEXT NOT NULL,action TEXT NOT NULL,payload TEXT NOT NULL,idempotency_key TEXT NOT NULL UNIQUE,state TEXT NOT NULL,attempt INTEGER DEFAULT 0,owner TEXT,lease_until REAL,result TEXT,last_error TEXT,created_at REAL,updated_at REAL);""")
    def submit_with_operation(self, task_id, task_payload, op_id, action, op_payload, idempotency_key, inject_failure=False):
        if not all(isinstance(v,str) and v for v in (task_id,op_id,action,idempotency_key)):
            raise ValueError('invalid_identity')
        task_raw=json.dumps(task_payload,sort_keys=True,ensure_ascii=False)
        op_raw=json.dumps(op_payload,sort_keys=True,ensure_ascii=False)
        now=self.clock()
        with sqlite3.connect(self.path,timeout=10,isolation_level=None) as db:
            try:
                db.execute('BEGIN IMMEDIATE')
                task=db.execute('SELECT payload FROM tasks WHERE id=?',(task_id,)).fetchone()
                op=db.execute('SELECT op_id,task_id,action,payload,idempotency_key FROM operations WHERE op_id=? OR idempotency_key=?',(op_id,idempotency_key)).fetchone()
                expected=(op_id,task_id,action,op_raw,idempotency_key)
                if task or op:
                    if task is None or op is None or task[0]!=task_raw or op!=expected:
                        raise ValueError('intent_conflict')
                    db.commit()
                    return False
                db.execute("INSERT INTO tasks(id,payload,status) VALUES(?,?,'pending')",(task_id,task_raw))
                if inject_failure: raise RuntimeError('injected_crash_before_outbox')
                db.execute("INSERT INTO operations(op_id,task_id,action,payload,idempotency_key,state,created_at,updated_at) VALUES(?,?,?,?,?,'pending',?,?)",(op_id,task_id,action,op_raw,idempotency_key,now,now))
                db.execute('INSERT INTO events(task_id,event,at) VALUES(?,?,?)',(task_id,'intent_committed',now))
                db.commit()
                return True
            except BaseException:
                db.rollback()
                raise
    def counts(self):
        with sqlite3.connect(self.path) as db:
            return tuple(db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in ('tasks','operations','events'))
