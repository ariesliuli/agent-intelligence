# 2026-11-05｜事务发件箱与歧义状态隔离（Transactional Outbox & Ambiguous Outcome Isolation）

> **状态**：已提交 SQLite Outbox 原型及 15 项 pytest 测试；本地等价实现运行 `15 passed in 0.19s`。**尚未独立拉取并运行 GitHub 原样代码，未验证 CI，也未连接真实 CLI、设备或网络服务。** 这不是 exactly-once（恰好一次）交付保证。

## ① 建设目标与关联 Hint
承接 11/04 的 SQLite Task Lifecycle。关联 HINT-002（任务契约）、005（确定性工作流）、013（审计）、023（状态化工具调用验证）。解决“任务租约超时后数据库拒绝旧执行器，但外部设备可能已经执行了动作”的重复副作用风险。不创建新 Hint；`state/processed.json` 继续仅用于新 Hint 去重。

## ② 架构位置与接口
`OpenClaw → Router → Task Store → Outbox → Dispatcher（待接） → Tool Adapter（待接） → Reconciler（待接） → Verifier`

Outbox 接口：`enqueue(op_id,task_id,action,payload,idempotency_key)`、`claim(op_id,owner,ttl)`、`finish(op_id,owner,attempt,result)`、`fail(...,known_no_effect)`、`expire(op_id)`、`reconcile(op_id,outcome,evidence)`、`get(op_id)`。

示例输入（**仅模拟**）：
```json
{"op_id":"op-001","task_id":"task-001","action":"read_status","payload":{"device":"simulated"},"idempotency_key":"task-001:read_status:v1"}
```
输出（超时且无法确定外部执行结果）：
```json
{"state":"ambiguous","retry_allowed":false,"reconciliation_required":true}
```
状态机：`pending → inflight → succeeded`；已确认“无副作用”的失败可回到 `pending`；网络超时/租约过期 → `ambiguous`；只有可信外部回执或人工复核才能 `ambiguous → succeeded|pending|failed`。终态不可重新领取。

## ③ 实现细节
源码：[`framework/agent_core/outbox.py`](../framework/agent_core/outbox.py)。测试：[`framework/tests/test_outbox.py`](../framework/tests/test_outbox.py)。

Python 3.10+，SQLite 标准库，pytest。用 `BEGIN IMMEDIATE` 串行化同库写入；`op_id` 和 `idempotency_key` 唯一，重复键且内容不同抛出 `operation_conflict`。每次领取递增 `attempt`，结果提交同时检查 `owner + attempt + lease`。**租约过期不是“外部未执行”的证据**，故标记 `ambiguous` 而非自动重试。

运行：
```bash
cd framework
python -m pytest -q tests/test_outbox.py
```

部署前必须补齐：将任务状态更新与 Outbox 插入放入**同一 SQLite 事务**，否则当前 `Store.submit` 和 `Outbox.enqueue` 之间仍存在崩溃窗口；真实适配器需优先采用外部服务支持的幂等键与状态查询。若设备不支持幂等键，未知结果必须停机待核对，绝不承诺 exactly-once。当前 `reconcile` 未实现调用者鉴权，**仅限受信任的本地测试代码**，不可作为对外 API。还缺审计签名、重试上限、并发/断电测试、WAL 与数据迁移。

## ④ 具体经验（模拟验证）
**触发条件**：执行器已发出外部命令但网络超时，或租约到期。

**现象**：原任务状态机可以阻止旧执行器写回数据库，却无法知道外部动作是否成功。

**根因**：数据库事务和外部设备操作不共享原子提交边界；超时只代表调用方未收到确认。

**解决**：操作先登记 Outbox；`inflight` 超时进入 `ambiguous`，禁止自动重复；通过外部状态或回执核对后才允许重新执行。对于不支持查询/幂等的设备，应由人工判断。

**验证**：本地 15 项 pytest 通过，覆盖唯一键、重复冲突、并发领取的基本拒绝、旧 owner、超时歧义、已确认无副作用的重试和人工核对。**尚未进行真实外部副作用测试。**

## ⑤ 验收标准与回滚
本阶段：15/15 本地单进程模拟测试通过。下阶段上线门槛：同事务任务+Outbox 写入；50 组断点故障注入；未知结果自动重试次数 = 0；100% 冲突操作被拒绝；人工/回执核对操作必须有权限与证据；独立 CI 通过。对设备重启、配置修改等高风险动作必须另有授权门禁。

回滚：关闭 Dispatcher，保留 Outbox 数据，人工核对 `ambiguous` 记录；不得清空表或将未知结果批量重置为 `pending`。

## ⑥ 与昨日差异、剩余问题、下一步
昨日只防止**旧执行器污染数据库**；今日新增“外部副作用结果未知时禁止盲目重试”的 Outbox 记录和状态转换。下一期优先实现 Store 与 Outbox 同库同事务写入、可信核对接口、失败注入与 GitHub CI；再考虑接入 Codex/Claude 和 Node-RED 只读模拟器。

**参考**：
- SQLite Transactions: https://www.sqlite.org/lang_transaction.html
- SQLite WAL: https://www.sqlite.org/wal.html
- Microsoft Transactional Outbox Pattern: https://learn.microsoft.com/en-us/azure/architecture/databases/guide/transactional-outbox-cosmos
- 既有工程：[`2026-11-04 SQLite Task Lifecycle`](2026-11-04-sqlite-task-lifecycle.md)

**证据分级**：本地模拟测试 = 已验证（限定当前本地版本）；生产部署/跨进程可靠性/外部设备幂等 = 未验证；下一阶段指标 = 目标而非测量结果。
