# 2026-11-07｜跨模块契约与安全缺口验证（Cross-Module Contract & Safety Gap Verification）

> 状态：**新增可执行集成测试源码；未在远端 CI 或本地运行本次新增测试**。仅 SQLite 模拟，不接真实设备。**GitHub 提交不等于测试通过**。

## ① 今日建设目标及关联 Hint
承接 11/06 原子提交，检查 `Store`、`Outbox`、`AtomicIntentStore` 三者是否共享数据库 schema 与执行语义。关联 HINT-002（任务契约）、005（编排）、013（审计）、023（工具验证）；`state/processed.json` 最高登记 HINT-024。已读取 README、AGENTS、processed、11/06 报告和三个 Python 模块，未把历史 Hint 摘要当成原文。本次**不增加 Hint**。

## ② 框架位置与上下游接口
`OpenClaw（未接） → Router（未接） → AtomicIntentStore.submit_with_operation → SQLite(tasks,operations,events) → Store/Outbox → Dispatcher（未接） → Adapter（未接） → Reconciler（未鉴权） → Verifier（未接）`

输入（模拟）：
```json
{"task_id":"t","task_payload":{"goal":"sim"},"op_id":"op","action":"read_status","op_payload":{"target":"sim"},"idempotency_key":"t:read:v1"}
```
实际接口返回 `bool`，不是 JSON；下列为计划中的统一执行器输出契约：
```json
{"task_id":"t","operation_id":"op","attempt":1,"state":"succeeded","evidence":{"type":"simulated_ack","verified":false}}
```
配置建议（**未接入配置加载器**）：
```yaml
storage: {backend: sqlite, db_path: "./runtime/agent.db"}
execution: {external_writes_enabled: false, ambiguous_auto_retry: false}
reconcile: {require_authenticated_evidence: true, enabled: false}
```

## ③ 可直接交给 Codex/Claude Code 的实现
新增 `framework/tests/test_integration_contract.py`，pytest 测试四个契约：
1. Atomic 创建的 task/op 能被旧 Store/Outbox 读取、领取并在模拟场景完成；
2. 超时转 `ambiguous` 后第二执行器不能自动领取；
3. 旧 `Store.submit()` 单独提交会留下无操作记录，随后 Atomic 拒绝该半状态；
4. `reconcile` 拒绝空证据，却**接受任意非空字符串**：当前没有鉴权，属于明确安全缺口，测试用于记录当前行为，**不是安全性合格测试**。

目录与运行：
```text
framework/
  agent_core/{store.py,outbox.py,atomic.py}
  tests/{test_store.py,test_outbox.py,test_atomic.py,test_integration_contract.py}
architecture/2026-11-07-cross-module-contract.md
```
```bash
cd framework
python -m pytest -q tests/test_integration_contract.py
python -m pytest -q tests/
```
依赖：Python 3.10+、pytest、sqlite3 标准库；需先安装 pytest。若导入失败，确认工作目录为 `framework`。

## ④ 具体经验：待验证经验（Pending Verification）
**触发条件**：先调用旧 `Store.submit()`，进程在 `Outbox.enqueue()` 前退出。
**环境**：单文件 SQLite，多模块使用同一路径。
**现象（代码推导，尚未运行新增测试）**：只存在 task，不存在 operation；`AtomicIntentStore` 检测到半状态后抛 `intent_conflict`。
**根因**：旧入口仍允许分离事务，新的原子 API 并未强制替换旧调用路径。
**解决步骤**：先在测试中复现；接入编排层时只开放原子意图提交；旧 submit/enqueue 标为内部或只读模拟接口；建立迁移检查，扫描业务调用处。
**证据**：源码中 Store/Outbox 独立事务、Atomic 冲突分支可直接检查；新增测试尚未运行。
**适用边界**：仅数据库记录一致性；外部设备执行结果未知仍不得自动重试。

## ⑤ 验证与量化验收
本期交付的是**测试代码**，不宣称通过。CI 下一步执行全部既有测试 + 4 个新测试；目标：新测试 4/4、全套 100%、零孤儿操作、`ambiguous` 自动领取 0 次。补充 ≥50 次独立进程中止与多进程竞争测试；暂未完成。真正启用写操作之前：`reconcile` 必须验证主体、操作 ID、证据来源与不可重放 token；未认证证据接受次数必须为 0（当前代码**不满足**）。

## ⑥ 相对上一版差异、剩余问题与回滚
11/06 只验证单类 Atomic 写入；11/07 新增跨三个现有模块的契约测试，并明确揭示两个阻塞：旧入口可绕开原子性、`reconcile` 未鉴权。下一步优先建立统一的 Facade 及有版本的 schema migration，然后将 `reconcile` 替换为可信证据接口，并加入 GitHub Actions CI。
回滚：不修改生产模块，删除新增测试文件即可撤销本次代码增量；`external_writes_enabled=false` 持续保持。不得以通过本次模拟测试为理由开启真实设备写入。

参考原始文档（不作为本次测试已通过的证据）：
- SQLite transactions: https://www.sqlite.org/lang_transaction.html
- Python sqlite3: https://docs.python.org/3/library/sqlite3.html
- pytest: https://docs.pytest.org/en/stable/
