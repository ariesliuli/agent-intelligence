"""SQLite 任务状态机：租约、fencing token、检查点、幂等提交。"""
import sqlite3, json, time
from contextlib import contextmanager

class Store:
    def __init__(self, path, clock=None):
        self.path=str(path); self.clock=clock or time.time
        with sqlite3.connect(self.path) as d:
            d.executescript("""CREATE TABLE IF NOT EXISTS tasks(
              id TEXT PRIMARY KEY,payload TEXT NOT NULL,status TEXT NOT NULL,
              attempt INTEGER NOT NULL DEFAULT 0,owner TEXT,lease REAL,
              checkpoint TEXT,result TEXT);
              CREATE TABLE IF NOT EXISTS events(
              id INTEGER PRIMARY KEY AUTOINCREMENT,task_id TEXT,event TEXT,at REAL);""")
    @contextmanager
    def tx(self):
        d=sqlite3.connect(self.path,timeout=5,isolation_level=None)
        try:
            d.execute('BEGIN IMMEDIATE')
            yield d
            d.commit()
        except BaseException:
            d.rollback(); raise
        finally: d.close()
    def event(self,d,id,name):
        d.execute('INSERT INTO events(task_id,event,at) VALUES(?,?,?)',(id,name,self.clock()))
    def submit(self,id,payload):
        raw=json.dumps(payload,sort_keys=True,ensure_ascii=False)
        with self.tx() as d:
            row=d.execute('SELECT payload FROM tasks WHERE id=?',(id,)).fetchone()
            if row:
                if row[0]!=raw: raise ValueError('task_id_conflict')
                return False
            d.execute("INSERT INTO tasks(id,payload,status) VALUES(?,?,'pending')",(id,raw))
            self.event(d,id,'submitted')
            return True
    def claim(self,id,owner,ttl=60,max_attempts=3):
        if not owner or ttl<=0 or max_attempts<1: raise ValueError('invalid_lease')
        with self.tx() as d:
            row=d.execute('SELECT status,attempt,lease FROM tasks WHERE id=?',(id,)).fetchone()
            if not row:return None
            status,n,lease=row
            if not(status=='pending' or (status=='running' and lease is not None and lease<=self.clock())):return None
            if n>=max_attempts:
                d.execute("UPDATE tasks SET status='failed',owner=NULL,lease=NULL WHERE id=?",(id,))
                self.event(d,id,'attempts_exhausted')
                return None
            d.execute("UPDATE tasks SET status='running',attempt=?,owner=?,lease=? WHERE id=?",
                      (n+1,owner,self.clock()+ttl,id))
            self.event(d,id,'claimed')
            return n+1
    def write(self,id,owner,attempt,kind,value):
        if kind not in ('checkpoint','result'):raise ValueError('invalid_write')
        raw=json.dumps(value,sort_keys=True,ensure_ascii=False)
        with self.tx() as d:
            if kind=='result':
                sql="UPDATE tasks SET result=?,status='succeeded',owner=NULL,lease=NULL WHERE id=? AND status='running' AND owner=? AND attempt=? AND lease>?"
            else:
                sql="UPDATE tasks SET checkpoint=? WHERE id=? AND status='running' AND owner=? AND attempt=? AND lease>?"
            ok=d.execute(sql,(raw,id,owner,attempt,self.clock())).rowcount==1
            if ok:self.event(d,id,kind)
            return ok
    def get(self,id):
        with sqlite3.connect(self.path) as d:
            d.row_factory=sqlite3.Row
            r=d.execute('SELECT * FROM tasks WHERE id=?',(id,)).fetchone()
            return dict(r) if r else None
