# 2026-11-08｜统一意图入口与失败封闭（Unified Intent Facade & Fail-Closed Boundary）

> 状态：已新增 Facade 源码与四项 pytest 测试；远端 CI 未验证。本模块**仅 SQLite 模拟**，不支持真实设备写入。关联 HINT-002/005/013/023；最高登记 HINT-024，不新增 Hint。

## ① 建设目标及关联 Hint
承接 11/07 跨模块契约检查：旧 `Store.submit` 可绕过 Atomic 提交，`Outbox.reconcile` 尚未鉴权。今天先建立供未来 OpenClaw/Router 使用的**统一模拟提交入口**，并以拒绝未知字段、拒绝非白名单操作、拒绝启用外部写入为最小安全边界。此前独立旧 API 仍然存在，故**不能声称已封堵所有绕过路径**。

## ② 架构位置与上下游
`OpenClaw [未接] → Router [未接] → IntentFacade.submit → AtomicIntentStore → SQLite(tasks,operations,events) → Outbox [未接执行器] → Reconciler [未鉴权]`。
Facade 不接受模型直接决定的设备写操作；上游必须先生成严格契约请求，未来权限层另行审批。
输入：
```json
{"task_id":"t1","task_payload":{"goal":"simulation"},"op_id":"o1","action":"read_status","op_payload":{"target":"sim"},"idempotency_key":"t1:read:v1"}
```
输出：`True` 新提交；`False` 完全相同的重复意图；`ValueError` 格式或身份冲突；`PermissionError` 动作不允许。不是 JSON 输出，未来 Adapter 契约需要单独版本化。
配置意图（当前构造函数只实现 external_writes_enabled，**没有 YAML 解析器**）：
```yaml
storage: {backend: sqlite, db_path: "./runtime/agent.db"}
execution:
  external_writes_enabled: false
  allowed_simulation_actions: [read_status, simulate_noop]
reconcile: {enabled: false, require_authenticated_evidence: true}
```

## ③ 具体实现
新增：
```text
framework/agent_core/facade.py
framework/tests/test_facade.py
engineering/2026-11-08-unified-intent-facade.md
```
Python 3.10+、SQLite 标准库、pytest。直接使用现有 `AtomicIntentStore.submit_with_operation`，不复制数据库事务逻辑。检查请求必须恰好有六个字段，payload 必须是 dict，动作限模拟白名单。检查孤儿 operation 与无 operation 的 task（只做诊断，不能自动修复）。

执行：
```bash
cd framework
python -m pytest -q tests/test_facade.py
python -m pytest -q tests/
```
后续将 OpenClaw/CLI 适配器改为只能调用 Facade；旧 `Store.submit` 与 `Outbox.enqueue` 需逐调用点迁移并建立 CI 静态检查，不能仅靠 Python 类封装宣称安全隔离。

## ④ 具体经验（待验证经验）
触发：Agent 把 `device_reboot` 作为 `action` 交给入口。环境：单进程 SQLite 模拟，尚无设备。现象（预期，测试尚待 CI）：Facade 抛 `PermissionError(action_not_allowlisted)`，记录数量保持 (0,0,0)。根因：原子事务解决数据库一致性，却不等于动作授权。解决：在提交前白名单检查，且构造时拒绝 `external_writes_enabled=True`。验证：新增 pytest 用例，尚未宣称通过。边界：直接导入旧 Store/Outbox 的代码仍可绕过，Python 进程内非强制沙箱；生产环境必须通过进程权限/模块访问控制和统一调度入口加固。

## ⑤ 验证、指标及回滚
目标：新测试 4/4、全套 pytest 100%；非白名单操作写入 0；相同意图重复生成记录 0；孤儿 operation 0；外部真实设备写入 0。额外验收：对既有旧入口做全仓调用扫描，确认生产编排调用数 0；多进程冲突与 SIGKILL 故障注入 ≥50 次；可信核对未认证请求接受 0。上述额外验收**尚未完成**。
回滚：删除新增 facade.py 与 test_facade.py，其他模块未修改；保持所有真实设备写入关闭。

## ⑥ 相对上一版差异、剩余问题与下一步
11/07 只新增暴露缺口的测试；11/08 新增最小可调用 Facade 与拒绝测试。仍未完成：迁移旧调用、统一 schema migration、可信核对鉴权、CI、跨进程测试、OpenClaw/CLI/Node-RED 适配。下一步先让 GitHub Actions 跑全套测试，随后实现旧入口调用扫描与可信核对的签名证据验证。不得把本次模拟边界解释为完整生产安全隔离。

参考：SQLite transaction https://www.sqlite.org/lang_transaction.html ；Python sqlite3 https://docs.python.org/3/library/sqlite3.html ；pytest https://docs.pytest.org/en/stable/
