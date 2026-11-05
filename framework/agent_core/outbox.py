"""SQLite outbox prototype: unknown outcomes require reconciliation."""
import json, sqlite3, time
from contextlib import contextmanager

class Outbox:
    def __init__(self, path, clock=None):
        self.path=str(path)
        self.clock=clock or time.time
        with sqlite3.connect(self.path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS operations(
              op_id TEXT PRIMARY KEY,task_id TEXT,action TEXT,payload TEXT,
              idempotency_key TEXT UNIQUE,state TEXT,attempt INTEGER DEFAULT 0,
              owner TEXT,lease_until REAL,result TEXT,last_error TEXT,
              created_at REAL,updated_at REAL)""")
    @contextmanager
    def _tx(self):
        db=sqlite3.connect(self.path,timeout=10,isolation_level=None)
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()
    def enqueue(self,op_id,task_id,action,payload,idempotency_key):
        if not all(isinstance(x,str) and x for x in (op_id,task_id,action,idempotency_key)):
            raise ValueError('invalid_identity')
        raw=json.dumps(payload,sort_keys=True,ensure_ascii=False)
        now=self.clock()
        with self._tx() as db:
            row=db.execute('SELECT task_id,action,payload,idempotency_key FROM operations WHERE op_id=? OR idempotency_key=?',(op_id,idempotency_key)).fetchone()
            if row:
                if row!=(task_id,action,raw,idempotency_key): raise ValueError('operation_conflict')
                return False
            db.execute("INSERT INTO operations(op_id,task_id,action,payload,idempotency_key,state,created_at,updated_at) VALUES(?,?,?,?,?,'pending',?,?)",(op_id,task_id,action,raw,idempotency_key,now,now))
            return True
    def claim(self,op_id,owner,ttl=30):
        if not owner or ttl<=0: raise ValueError('invalid_lease')
        now=self.clock()
        with self._tx() as db:
            row=db.execute('SELECT state,attempt FROM operations WHERE op_id=?',(op_id,)).fetchone()
            if not row or row[0]!='pending': return None
            n=row[1]+1
            db.execute("UPDATE operations SET state='inflight',attempt=?,owner=?,lease_until=?,updated_at=? WHERE op_id=?",(n,owner,now+ttl,now,op_id))
            return n
    def finish(self,op_id,owner,attempt,result):
        now=self.clock()
        with self._tx() as db:
            return db.execute("UPDATE operations SET state='succeeded',result=?,owner=NULL,lease_until=NULL,updated_at=? WHERE op_id=? AND state='inflight' AND owner=? AND attempt=? AND lease_until>?",(json.dumps(result),now,op_id,owner,attempt,now)).rowcount==1
    def fail(self,op_id,owner,attempt,error,known_no_effect=False):
        now=self.clock()
        state='pending' if known_no_effect else 'ambiguous'
        with self._tx() as db:
            return db.execute("UPDATE operations SET state=?,last_error=?,owner=NULL,lease_until=NULL,updated_at=? WHERE op_id=? AND state='inflight' AND owner=? AND attempt=? AND lease_until>?",(state,str(error),now,op_id,owner,attempt,now)).rowcount==1
    def expire(self,op_id):
        now=self.clock()
        with self._tx() as db:
            return db.execute("UPDATE operations SET state='ambiguous',owner=NULL,lease_until=NULL,last_error='lease_expired',updated_at=? WHERE op_id=? AND state='inflight' AND lease_until<=?",(now,op_id,now)).rowcount==1
    def reconcile(self,op_id,outcome,evidence):
        if outcome not in ('succeeded','pending','failed') or not evidence: raise ValueError('invalid_reconciliation')
        now=self.clock()
        with self._tx() as db:
            return db.execute("UPDATE operations SET state=?,result=?,updated_at=? WHERE op_id=? AND state='ambiguous'",(outcome,json.dumps({'evidence':evidence}),now,op_id)).rowcount==1
    def get(self,op_id):
        with sqlite3.connect(self.path) as db:
            db.row_factory=sqlite3.Row
            row=db.execute('SELECT * FROM operations WHERE op_id=?',(op_id,)).fetchone()
            return dict(row) if row else None
