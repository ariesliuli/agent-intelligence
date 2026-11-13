"""SQLite outbox prototype: unknown outcomes require reconciliation."""
import json, sqlite3, time
from contextlib import contextmanager

class Outbox:
    def __init__(self, path, clock=None, reconciliation_verifier=None):
        self.path=str(path)
        self.clock=clock or time.time
        self.reconciliation_verifier=reconciliation_verifier
        with sqlite3.connect(self.path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS operations(
              op_id TEXT PRIMARY KEY,task_id TEXT,action TEXT,payload TEXT,
              idempotency_key TEXT UNIQUE,state TEXT,attempt INTEGER DEFAULT 0,
              owner TEXT,lease_until REAL,result TEXT,last_error TEXT,
              created_at REAL,updated_at REAL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS reconciliation_nonces(
              nonce TEXT PRIMARY KEY,op_id TEXT NOT NULL,outcome TEXT NOT NULL,
              consumed_at REAL NOT NULL)""")
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
        # A caller-supplied boolean is not proof that a remote side effect did not occur.
        # Preserve the argument for compatibility but fail closed; use independent
        # reconciliation for any ambiguous operation before permitting a retry.
        if known_no_effect is not False:
            raise PermissionError('unverified_no_effect_claim')
        now=self.clock()
        state='ambiguous'
        with self._tx() as db:
            return db.execute("UPDATE operations SET state=?,last_error=?,owner=NULL,lease_until=NULL,updated_at=? WHERE op_id=? AND state='inflight' AND owner=? AND attempt=? AND lease_until>?",(state,str(error),now,op_id,owner,attempt,now)).rowcount==1
    def expire(self,op_id):
        now=self.clock()
        with self._tx() as db:
            return db.execute("UPDATE operations SET state='ambiguous',owner=NULL,lease_until=NULL,last_error='lease_expired',updated_at=? WHERE op_id=? AND state='inflight' AND lease_until<=?",(now,op_id,now)).rowcount==1
    def reconcile(self,op_id,outcome,evidence):
        # The verifier is an injected trusted adapter, not a model-generated assertion.
        if outcome not in ('succeeded','pending','failed') or not isinstance(evidence,dict):
            raise ValueError('invalid_reconciliation')
        if self.reconciliation_verifier is None:
            raise PermissionError('reconciliation_verifier_required')
        if evidence.get('op_id') != op_id or evidence.get('outcome') != outcome:
            raise PermissionError('reconciliation_binding_mismatch')
        nonce=evidence.get('nonce')
        if not isinstance(nonce,str) or not nonce.strip() or len(nonce)>256:
            raise PermissionError('reconciliation_nonce_required')
        now=self.clock()
        # Serialize verification, nonce consumption, and state transition in ONE
        # SQLite write transaction. Concurrent requests cannot both consume a nonce.
        with self._tx() as db:
            row=db.execute("SELECT state FROM operations WHERE op_id=?",(op_id,)).fetchone()
            if not row or row[0]!='ambiguous':
                return False
            if db.execute("SELECT 1 FROM reconciliation_nonces WHERE nonce=?",(nonce,)).fetchone():
                raise PermissionError('replayed_reconciliation')
            # This hook must independently authenticate the remote result and its
            # op/outcome/nonce binding. Never wire a permissive lambda in production.
            if self.reconciliation_verifier(op_id,outcome,evidence) is not True:
                raise PermissionError('unverified_reconciliation')
            db.execute("INSERT INTO reconciliation_nonces(nonce,op_id,outcome,consumed_at) VALUES(?,?,?,?)",
                       (nonce,op_id,outcome,now))
            changed=db.execute("UPDATE operations SET state=?,result=?,updated_at=? WHERE op_id=? AND state='ambiguous'",
                               (outcome,json.dumps({'evidence':evidence}),now,op_id)).rowcount
            if changed!=1:
                raise RuntimeError('reconciliation_state_race')
            return True
    def get(self,op_id):
        with sqlite3.connect(self.path) as db:
            db.row_factory=sqlite3.Row
            row=db.execute('SELECT * FROM operations WHERE op_id=?',(op_id,)).fetchone()
            return dict(row) if row else None
