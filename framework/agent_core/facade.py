"""Fail-closed SQLite simulation entrypoint. No real device writes."""
import sqlite3
from .atomic import AtomicIntentStore

class IntentFacade:
    def __init__(self, db_path, *, external_writes_enabled=False, clock=None):
        if external_writes_enabled:
            raise ValueError("external_writes_not_supported")
        self.path = str(db_path)
        self.atomic = AtomicIntentStore(self.path, clock=clock)

    def submit(self, request):
        if not isinstance(request, dict):
            raise ValueError("invalid_request")
        required = {"task_id", "task_payload", "op_id", "action", "op_payload", "idempotency_key"}
        if set(request) != required:
            raise ValueError("invalid_fields")
        if request["action"] not in ("read_status", "simulate_noop"):
            raise PermissionError("action_not_allowlisted")
        if not isinstance(request["task_payload"], dict) or not isinstance(request["op_payload"], dict):
            raise ValueError("invalid_payload")
        return self.atomic.submit_with_operation(**request)

    def integrity(self):
        with sqlite3.connect(self.path) as db:
            orphans = db.execute("SELECT COUNT(*) FROM operations o LEFT JOIN tasks t ON t.id=o.task_id WHERE t.id IS NULL").fetchone()[0]
            missing = db.execute("SELECT COUNT(*) FROM tasks t LEFT JOIN operations o ON o.task_id=t.id WHERE o.op_id IS NULL").fetchone()[0]
            return {"orphan_operations": orphans, "tasks_without_operations": missing}
