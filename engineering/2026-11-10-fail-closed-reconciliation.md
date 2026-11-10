# 2026-11-10｜歧义结果核对默认拒绝（Fail-Closed Ambiguous Reconciliation）

> 状态：**源码与回归测试已提交；完整 pytest/CI 未验证通过。** 这是模拟框架的边界加固，不是生产级身份认证或设备 exactly-once 保证。关联 HINT-002、005、013、023，以及宿主第一性原理与因果直觉协议；不新增 Hint。

## ① 今日建设目标及关联 Hint

11/07 已发现 `Outbox.reconcile(op_id, outcome, evidence)` 只要收到任意非空文本就能把 `ambiguous` 变回 `pending`，进而允许第二个执行器重试。11/09 建立 CI 入口，但旧测试仍把该漏洞视为合法行为。本次优先修复这一**明确的安全边界缺口**，而不是增加新的模型路由功能。

第一性原理：外部调用超时后，**本地没有收到响应**与**远端确定未产生副作用**不是同一个事实。只要不能证明未执行，就不得重试有副作用操作。

## ② 框架位置与上下游接口

```text
OpenClaw（尚未接入）
  → IntentFacade（允许 read_status/simulate_noop）
  → AtomicIntentStore（任务+操作+事件同一事务）
  → Outbox（pending → inflight → succeeded / ambiguous）
  → 外部执行器（尚未接入）
                         ↓
             可信核对器（接口预留，生产实现尚缺）
                         ↓
                ambiguous → pending/succeeded/failed
```

改动文件：`framework/agent_core/outbox.py` 和 `framework/tests/test_outbox.py`。未改变 SQLite schema；未连接设备；不新增外部权限。

## ③ 具体实现细节与契约

`Outbox(path, clock=None, reconciliation_verifier=None)` 新增可注入验证器；默认 `None`，即**禁止所有核对状态变更**。调用 `reconcile` 时要求：

1. `outcome` 为 `succeeded/pending/failed`；`evidence` 为对象。
2. `evidence.op_id` 和 `evidence.outcome` 必须绑定当前操作及目标状态。
3. 必须存在 `reconciliation_verifier`，且返回值严格为布尔 `True`。
4. 仅在原状态为 `ambiguous` 时执行 SQLite 更新；其他状态返回 `False`。

**接口示例（纯模拟，不代表可信签名）：**

```json
{
  "op_id": "op-001",
  "outcome": "pending",
  "evidence": {
    "op_id": "op-001",
    "outcome": "pending",
    "receipt": "simulated_no_effect"
  }
}
```

状态转移：`pending → inflight → ambiguous`；无可信验证器则保持 `ambiguous`，禁止 claim；验证器批准后才能 `ambiguous → pending`。输入非法抛 `ValueError`；缺验证器、绑定错误、拒绝验证抛 `PermissionError`。**没有自动重试核对请求**。

**必须明确：** 本次实现仅提供 fail-closed 的验证器挂载点；验证器本身尚无真实认证实现。生产版必须进一步验证凭据/签名、issuer、有效期、nonce 防重放、操作原始参数与远端状态，并对并发核对执行事务化的一次性消费。注入 `lambda: True` 不构成可信认证。

可供 Codex/Claude Code 继续实现的接口示例：

```python
def verifier(op_id: str, outcome: str, evidence: dict) -> bool:
    # 必须独立查证远端副作用与操作身份；不能信任模型自述。
    # 本次仅定义接口，不实现真实认证。
    raise NotImplementedError
```

## ④ 失败模式与可复用经验

**待验证经验：把「收到任意解释」当作「可以安全重试」会制造重复副作用。**

触发：网络超时、MQTT 回执丢失、HTTP POST 成功但响应断线、Codex/Claude 执行器崩溃。环境：Python 3.10+、SQLite Outbox 模拟器。现象：旧版只要给出 `'remote confirms no effect'` 字符串就可让 `ambiguous` 回到 `pending`。根因：核对接口只检查文本非空，不验证来源、绑定或实际远端结果。修复：默认拒绝、强制结构化绑定、引入独立 verifier、更新安全回归断言。证据：仓库旧版源码和本次差异可核查；**未完成 CI 运行，不能宣称实际测试通过**。边界：该改动只封闭这一公开方法的默认路径，不能阻止拥有数据库写权限的进程直接修改 SQLite。

适用：Node-RED HTTP/MQTT、LoRaWAN 设备配置、技术支持批量操作、GitHub 写入和任何有副作用的 API。只读、真正幂等的接口可采用不同策略，但须有明确协议保证。

## ⑤ 验证步骤与可量化验收标准

本地执行：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install 'pytest==8.3.5'
cd framework
python -m pytest -q tests/
```

本次尝试从运行环境 clone GitHub 仓库以运行完整 pytest，但 DNS 无法解析 `github.com`，**因此没有实际执行测试**。GitHub 提交成功不等于测试通过。

验收标准（**目标，不是实绩**）：

1. 无 verifier 时，任意结构化证据核对 `ambiguous`：接受数 **0**。
2. `op_id/outcome` 绑定不符或 verifier 拒绝：接受数 **0**，状态保持 `ambiguous`。
3. 显式模拟 verifier 确认无副作用时，允许一次 `ambiguous → pending`，且后续 claim 的 attempt 递增。
4. Python 3.10/3.12 CI：两组全部通过、失败 0；待核查。
5. 真实生产前：重放同一证明的接受数 0、伪造证明接受数 0、跨任务证明接受数 0；**尚未实现**。
6. 真实设备写入次数 0，仓库新增密钥/客户资料/内部地址数 0。

## ⑥ 相对上一版、剩余问题、下一步与回滚

11/09 只有 CI 工作流，仍保留无鉴权核对；11/10 修改了默认行为和测试预期。此前依赖自由文本核对的调用会**故意失败**，需显式迁移到可信核对器，不能悄悄兼容旧路径。

下一步优先顺序：① GitHub Actions 确认本次 pytest 结果；② 实现持久化 nonce/一次性消费与可信远端回执校验；③ 核对器与 `IntentFacade` 集成，限制旧 Store/Outbox 直接调用；④ SQLite 进程权限隔离与并发故障注入。完整认证前只允许模拟操作。

**回滚**：保留当前默认拒绝，必要时将调用方切换为人工核对/只读；不要恢复旧版无鉴权 `reconcile`。如必须回滚源码，应继续封禁外部执行器，避免重启重复操作。

## 来源与限制

- 仓库实际代码：`framework/agent_core/outbox.py`、`framework/tests/test_outbox.py`。
- Python sqlite3 事务说明：https://docs.python.org/3/library/sqlite3.html
- pytest 文档：https://docs.pytest.org/en/stable/
- GitHub Actions：https://docs.github.com/en/actions
- 本次工程发现源于已知代码缺陷；没有声称这些文档提供了具体的认证方案，也没有伪造外部部署案例。
