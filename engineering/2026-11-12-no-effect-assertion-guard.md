# 2026-11-12｜调用方“无副作用”断言封堵（Caller-Asserted No-Effect Guard）

> 状态：**已提交源码与回归测试，尚未运行完整 pytest/CI；生产核对认证仍未实现。** 不新增 Hint。公开仓库仅包含合成示例。

## ① 今日建设目标与关联 Hint

核查 `AGENTS.md`、`README.md`、`state/processed.json`、HINT-025 与 11/10、11/11 工程报告及 `framework/agent_core/outbox.py`、`framework/tests/test_outbox.py`。登记最高编号 HINT-025，HINT-001～023 原文归档不完整，不能以摘要冒充原文。本次不重复 fail-closed `reconcile()` 的工作，而是修复其**旁路**：`Outbox.fail(..., known_no_effect=True)` 可由执行器直接将 `inflight` 变回 `pending`，不经过核对器。

关联 HINT-002（任务契约）、HINT-005（恢复）、HINT-013（审计）、HINT-023（工具顺序）及 `architecture/HOST-FIRST-PRINCIPLES.md`。根因是**把调用方自述布尔值当作外部无副作用证明**，与 11/10 的 `reconcile()` 默认拒绝原则冲突。

## ② 框架位置与上下游接口

```text
OpenClaw（尚未接入）
  → Router（模拟）
  → IntentFacade / AtomicIntentStore
  → SQLite Outbox
     ├─ claim(op_id, owner, ttl) → inflight
     ├─ finish(op_id, owner, attempt, result) → succeeded
     ├─ fail(op_id, owner, attempt, error, known_no_effect=False)
     │    → ambiguous（统一默认；拒绝调用方声称无副作用）
     ├─ expire(op_id) → ambiguous
     └─ reconcile(op_id, outcome, evidence)
          → 需独立 verifier（接口存在，认证尚未实现）
  → Codex CLI / Claude Code / Node-RED（尚未接入）
```

接口输入示例（合成）：

```json
{"op_id":"op-sim-1","owner":"codex","attempt":1,"error":"timeout","known_no_effect":true}
```

预期输出：`PermissionError("unverified_no_effect_claim")`，数据库状态不变；调用方必须改为 `known_no_effect=False`（或省略），把不确定结果转为 `ambiguous`，等待独立核对。

## ③ 具体实现与配置

变更文件：

- `framework/agent_core/outbox.py`：保留 `known_no_effect` 参数以暴露旧调用者，但仅允许严格 `False`。其他值（包括 `True`、整数 `1`、字符串、`None`、字典）直接抛 `PermissionError`，不得进入 `pending`。正常 `fail()` 一律转 `ambiguous`。
- `framework/tests/test_outbox.py`：把旧的“调用方声称无副作用即可重试”测试改为**必须拒绝**，新增非布尔值、过期租约不能绕过拒绝的回归用例。

核心逻辑：

```python
def fail(self, op_id, owner, attempt, error, known_no_effect=False):
    if known_no_effect is not False:
        raise PermissionError('unverified_no_effect_claim')
    now = self.clock()
    state = 'ambiguous'
    # 后续 SQLite BEGIN IMMEDIATE 与 owner/attempt/lease 条件更新沿用原实现
```

状态机：

```text
pending → inflight → succeeded
                   → ambiguous → [独立核对成功] → pending / succeeded / failed
                   ↛ pending（仅靠调用方 bool，禁止）
```

**失败与恢复**：旧调用者显式传 `True` 会收到 `PermissionError`，需记录错误并调用默认 `fail()`；如果租约已经过期则 `expire()` 将其变为 `ambiguous`。不要捕获异常后直接 `enqueue()` 新的操作 ID 以绕开去重。**配置**：仅 Python 标准库 `sqlite3`，测试需 pytest；无网络、真实设备或新凭证。保持生产外部写入关闭。

## ④ 具体经验（源码静态可验证，运行待验证）

**触发**：Codex/Claude Code、Node-RED 或 HTTP/MQTT 调用返回超时，执行器传入 `known_no_effect=True`。

**环境**：Python SQLite Outbox 原型；未连接外部执行器。

**现象**：原 `fail()` 实现的 `state='pending' if known_no_effect else 'ambiguous'` 使调用方可以绕过 11/10 新增的 `reconcile()` 可信验证挂载点，直接再次 claim。

**根因**：权限/证据校验仅保护一条状态转移路径，而非所有可达路径；自述 `True` 不等于远端无副作用。

**修复**：移除调用方布尔值赋予重试权限的能力，保留 fail-closed 兼容参数，补充回归。

**证据等级**：`observed_source`（源码静态可确认）；测试与实际部署效果 `not_verified`。**适用边界**：保护此公开方法；不防止拥有 SQLite 写权限的进程直接改库，也不构成 exactly-once 执行保证。

**可迁移规律**：安全门禁要审查**所有状态转移入口**，不能只加固一个 API。HTTP POST、MQTT 命令、设备配置、GitHub 写入均应把“响应未知”与“确定未执行”分开。

## ⑤ 验证步骤与量化验收

```bash
cd framework
python -m compileall -q agent_core tests
python -m pytest -q tests/test_outbox.py
python -m pytest -q tests/
```

建议 Python 3.10/3.12 双版本执行。目标（**尚未实测**）：

| 测试项 | 验收目标 |
|---|---|
| `known_no_effect=True` 直接重试 | 0 次允许 |
| 非严格布尔 `False` 断言 | 100% 拒绝 |
| 旧 owner / 过期 attempt 提交 | 0 次允许 |
| 正常失败状态 | 100% 进入 `ambiguous` |
| 未验证 `reconcile` | 0 次状态改变 |
| 完整 pytest | 两 Python 版本失败 0 |
| 真实设备写入 | 0 |

增加建议的后续测试：多进程竞争、`known_no_effect` 类型混淆、重放证据、重启恢复、恶意绕过 `enqueue`，并记录测试版本与输出。

## ⑥ 与上一版差异、剩余问题及下一步

- **11/10**：封闭 `reconcile()` 的自由文本证据路径。
- **11/11**：修复 pytest 收集语法错误并增加边界回归。
- **11/12**：封闭 `fail(known_no_effect=True)` 的旁路；所有未知副作用都进入 `ambiguous`。

剩余：可信远端回执、nonce 一次性消费、事务内验证、进程权限隔离、真实执行器接入、CI 结果核验。**下一步优先验证完整测试，再设计可信核对协议**，不能仅通过 `lambda: True` 模拟 verifier 就开放设备写操作。

**回滚**：遇到兼容性故障，调用方停止外部副作用操作并人工核对；不要恢复允许自述 `known_no_effect=True` 的旧实现。可将外部执行器保持只读/模拟模式。

## 参考来源

- 本仓库 `framework/agent_core/outbox.py`、`framework/tests/test_outbox.py` 及 11/10、11/11 工程报告（提交记录可审计）。
- Python sqlite3 事务文档：https://docs.python.org/3/library/sqlite3.html
- Python 异常与布尔语义：https://docs.python.org/3/library/stdtypes.html#boolean-type-bool
- pytest 官方文档：https://docs.pytest.org/en/stable/

本次没有引用外部生产案例，也没有声称完成运行测试。
