"""确定性、权限优先的 Agent 路由器；不连接外部模型。"""
from dataclasses import dataclass, asdict
import json

@dataclass(frozen=True)
class Task:
    task_id: str
    objective: str
    risk: str
    required_capabilities: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    verify_independently: bool = False

@dataclass(frozen=True)
class Worker:
    name: str
    capabilities: tuple[str, ...]
    available: bool
    remaining_units: int
    estimated_cost: float
    quality_score: float
    tool_permissions: tuple[str, ...]

@dataclass(frozen=True)
class Decision:
    status: str
    executor: str | None
    verifier: str | None
    reason: str

def route(task: Task, workers: list[Worker]) -> Decision:
    if not task.task_id or not task.objective:
        return Decision('blocked', None, None, 'invalid_task_contract')
    if task.risk not in ('low', 'medium', 'high'):
        return Decision('blocked', None, None, 'invalid_risk')
    eligible = [w for w in workers if w.available and w.remaining_units > 0
                and set(task.required_capabilities).issubset(w.capabilities)
                and set(task.allowed_tools).issubset(w.tool_permissions)]
    if not eligible:
        return Decision('blocked', None, None, 'no_eligible_worker')
    eligible.sort(key=lambda w: (-w.quality_score, w.estimated_cost, w.name))
    primary = eligible[0]
    if task.verify_independently or task.risk == 'high':
        others = [w for w in eligible if w.name != primary.name]
        if not others:
            return Decision('approval_required', None, None, 'independent_verifier_unavailable')
        return Decision('ready', primary.name, others[0].name, 'separate_verifier')
    return Decision('ready', primary.name, None, 'policy_match')

def to_json(decision: Decision) -> str:
    return json.dumps(asdict(decision), ensure_ascii=False, sort_keys=True)
