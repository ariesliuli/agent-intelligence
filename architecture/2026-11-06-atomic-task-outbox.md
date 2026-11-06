# 2026-11-06｜任务与 Outbox 原子提交（Atomic Task–Outbox Commit）

> 状态：**本地 SQLite 原型 8/8 pytest 通过**（Python + pytest，模拟数据）；GitHub 已提交源文件和测试，但未独立拉取远端原样代码运行 CI。尚未连接 OpenClaw、Codex CLI、Claude Code、Node-RED 或真实设备。**不是 exactly-once 保证。**

## ① 今日目标与关联 Hint
承接 11/05 的 Outbox 原型，解决原有 `Store.submit()` 与 `Outbox.enqueue()` 分属两个事务造成的崩溃窗口。关联 HINT-002（Task Contract）、005（Workflow）、013（审计）、023（工具调用验证）；不新增 Hint 编号。核查 `README.md`、`AGENTS.md`、`state/processed.json`、既有 `store.py`、`outbox.py`、11/05 报告；`processed.json` 最高为 HINT-024，历史摘要并非原始报告。

## ② 架构位置和接口
`OpenClaw → Router → AtomicIntentStore（同事务写 Task + Operation + Event）→ Outbox Dispatcher（未实现）→ Tool Adapter（未实现）→ Reconciler（未实现）→ Verifier`

接口：`submit_with_operation(task_id, task_payload, op_id, action, op_payload, idempotency_key, inject_failure=False) -> bool`。首次提交返回 `true`；完全相同重放返回 `false`；冲突抛出 `ValueError("intent_conflict")`。

输入 JSON 示例（全部模拟）：
```json
{"task_id":"t1","task_payload":{"goal":"simulate"},"op_id":"o1","action":"read_status","op_payload":{"device":"sim"},"idempotency_key":"t1:read:v1"}
```
输出逻辑示例：
```json
{"created":true,"task_status":"pending","operation_state":"pending","event":"intent_committed"}
```
以上输出是**接口语义示意**，实际 Python 方法只返回 bool；状态由 SQLite 查询。状态转换仍由既有 `Store` / `Outbox` 负责，本期不改变 `ambiguous` 的禁止重试规则。

## ③ 具体实现、目录与配置
- `framework/agent_core/atomic.py`：在**同一 SQLite 连接**执行 `BEGIN IMMEDIATE`，检查任务 ID 与操作幂等键，插入 task → operation → event，统一 commit；任意异常统一 rollback。
- `framework/tests/test_atomic.py`：8 个 pytest 用例，覆盖正常提交、相同重放、插入中断、任务内容冲突、幂等键冲突、空标识、历史单边任务和单边操作。
- `framework/agent_core/store.py`、`framework/agent_core/outbox.py`：保留旧 API；调用方必须显式改用 `AtomicIntentStore.submit_with_operation`，**旧两个 API 分别调用仍不具备原子性**。
- 环境：Python 3.10+、标准库 `sqlite3`、pytest；SQLite 文件路径需指向同一个本地数据库文件，不能分别给 Store 和 Outbox 两个 DB 文件。

命令：
```bash
cd framework
python -m pytest -q tests/test_atomic.py
```
配置示意：
```yaml
storage:
  backend: sqlite
  db_path: ./runtime/agent.db
  atomic_intent_enabled: true
execution:
  external_writes_enabled: false
  ambiguous_auto_retry: false
```
**YAML 为未来接线示例，当前代码尚未解析它。** Ubuntu 多进程需补 busy timeout、WAL、schema migrations 和故障测试。

## ④ 工程经验（本地模拟验证）
**触发**：任务登记后、外部操作意图登记前，进程崩溃。
**现象**：两个独立事务可能留下孤儿 task；恢复后任务存在但对应操作不存在。
**根因**：Task Store 与 Outbox 的提交边界不同。
**解决**：同一连接、同一事务写入三条记录；任何异常整体回滚。
**证据**：`inject_failure=True` 在写入 task 后主动抛出异常；测试确认 task/operation/event 均为 0，之后可成功重新提交。8/8 本地测试通过。
**适用边界**：仅保证 SQLite 内部写入原子性；不保证设备命令只执行一次、不保证真实断电持久性、也不保证现有所有调用路径已迁移。

## ⑤ 验收与回滚
本期测量：8/8 pytest，模拟故障下无半提交，重复相同意图无新事件，冲突拒绝且不污染原数据。
下一阶段门槛：CI 拉取远端原样代码通过；≥50 组多进程/进程终止/磁盘异常故障注入；零孤儿记录；未知外部副作用自动重试次数 0；操作鉴权与可信回执验证；不同进程并发重放不产生重复副作用。所有门槛均**未验证**。
回滚：保持 `external_writes_enabled=false`；停止 Dispatcher；保留 DB 与 `ambiguous` 记录，不删除、不批量重置。旧 API 只可用于无外部副作用的模拟流程。

## ⑥ 差异、限制与下一步
11/05 版本实现 Outbox 状态与歧义隔离；11/06 新增跨 Task/Outbox/Event 的单事务意图提交及故障注入测试。下一期优先：统一现有 `Store`/`Outbox` schema migration 和调用入口；GitHub CI；跨进程并发测试；可信 reconcile 的授权、证据类型与审计。完成后再接只读模拟器，不直接开放设备写入。

参考（原始技术文档，非本次测试结果）：
- SQLite Transactions: https://www.sqlite.org/lang_transaction.html
- SQLite Atomic Commit: https://www.sqlite.org/atomiccommit.html
- SQLite WAL: https://www.sqlite.org/wal.html
- Python sqlite3: https://docs.python.org/3/library/sqlite3.html
