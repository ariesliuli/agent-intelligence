# 2026-11-13｜核对证据一次性消费与事务门禁（Atomic Reconciliation Nonce Gate）

> 状态：**源码和测试已提交；pytest/CI 尚未实测；远端可信认证尚未实现。** 本报告为工程建设，不新增 Hint，不声称生产部署。

## ① 今日建设目标与关联 Hint

读取了 `AGENTS.md`、`README.md`、`state/processed.json`、11/12 工程报告以及 `framework/agent_core/outbox.py`、`framework/tests/test_outbox.py`。当前登记最高 HINT-025，HINT-001～023 原文不完整，不能声称已逐篇审核。前序 11/10 封闭自由文本核对，11/11 修复测试收集，11/12 封闭调用方无副作用断言。本次专注尚未解决的**并发核对和证据重放**，避免重复前述工作。

关联 HINT-002（任务契约）、005（故障恢复）、013/023（独立审计、工具顺序），以及 `architecture/HOST-FIRST-PRINCIPLES.md` 与 `architecture/HOST-CAUSAL-INTUITION.md`。因果假设：仅校验 verifier 返回值而不持久化消费凭证，不能防止不同操作或重启后复用同一证据。

## ② 架构位置与上下游契约

```text
OpenClaw（未接入）→ Router（原型）→ IntentFacade → SQLite Outbox
  → claim / finish / fail / expire
  → reconcile(op_id, outcome, evidence)
       → SQLite BEGIN IMMEDIATE
       → 检查 ambiguous 状态与 nonce 未消费
       → 可信 verifier（接口预留，生产实现缺失）
       → INSERT nonce + UPDATE operation（同一事务）
  → Codex CLI / Claude Code / Node-RED（未接入）
```

输入（**仅模拟**）：

```json
{"op_id":"op-sim-1","outcome":"pending","evidence":{"op_id":"op-sim-1","outcome":"pending","nonce":"nonce-sim-unique-1","receipt":"simulated_no_effect"}}
```

预期：缺少 nonce → `PermissionError('reconciliation_nonce_required')`；已消费 nonce → `PermissionError('replayed_reconciliation')`；独立 verifier 拒绝 → `PermissionError('unverified_reconciliation')`；非 ambiguous → `False`；通过则 `True` 并更新状态。nonce 是**重放标识**，不是认证凭证；调用方不能凭任意 nonce 获得授权。

## ③ 实现细节与可执行任务

代码修改：

- `framework/agent_core/outbox.py`：初始化时新增 `reconciliation_nonces(nonce PRIMARY KEY, op_id, outcome, consumed_at)`；`reconcile()` 要求非空、最长 256 字符的 nonce；在 `BEGIN IMMEDIATE` 事务中串行检查状态/nonce、调用 verifier、插入 nonce、更新操作。verifier 返回值必须是严格 `True`。失败触发回滚。
- `framework/tests/test_outbox.py`：修订原有成功核对测试，新增缺失 nonce、跨操作重放、verifier 拒绝后不消费、重启后重放拒绝的回归测试；非 ambiguous 不应调用 verifier。

目录与依赖：

```text
framework/
  agent_core/outbox.py
  tests/test_outbox.py
  pyproject.toml（现有工程配置，以仓库实际内容为准）
engineering/2026-11-13-atomic-reconciliation-nonce.md
```

仅依赖 Python 标准库 sqlite3/json/time 和测试工具 pytest；未新增外部服务、真实凭证或设备写入。

**实现局限**：数据库级唯一性和原子状态变更不等于端到端 exactly-once。当前 verifier 仍是可注入 Python 回调，必须由宿主限制注入权限；如果用 `lambda *args: True` 接入生产，就没有可信认证。当前没有校验 nonce 的发行方签名、时效、远端事务身份或可信设备状态；`finish()` 仍是执行器回报成功的独立路径，未来需要执行回执审计。SQLite 单写者锁会限制吞吐；verifier 在事务内不得执行长时间远端网络调用，生产应采用**事务外取远端证据、事务内快速本地验签/验证**的两阶段模式，并记录证据快照。

## ④ 具体经验：待验证经验（Pending Validation）

**触发**：多执行器在超时后同时提交核对，或重启后复用旧核对凭证。

**环境**：Python SQLite Outbox 原型；仅合成测试。

**现象（静态源码分析）**：旧版 verifier 在事务外执行，且没有持久 nonce 表，缺少一次性消费记录；不同操作可重复提交同一凭证。

**根因假设**：验证与状态变更没有同一原子边界；缺少跨进程持久化重放索引。

**处理**：`BEGIN IMMEDIATE` 内先验证状态和 nonce，后插入唯一 nonce 并更新操作；异常回滚。测试重启与跨操作重放。

**证据**：旧/新源码差异可审计，运行结果 `not_verified`；不声称真实攻击已发生。

**边界**：防止通过此 `reconcile()` API 重放同一 nonce；不阻止直接改写 SQLite、伪造可信 verifier 或使用不同 nonce 伪造相同远端证据。后者须通过签名/receipt_id 唯一性与远端状态验证解决。

**回滚**：停止生产写入，保持 `ambiguous` 人工核对；不可回滚到接受无 nonce 或自由文本的旧门禁。7/30/90 天检查误拒绝、锁等待、重放事件与核对延迟。

## ⑤ 验证与量化验收

```bash
cd framework
python -m compileall -q agent_core tests
python -m pytest -q tests/test_outbox.py
python -m pytest -q tests/
```

目标（**尚未实测**）：

| 验收项 | 目标 |
|---|---|
| 无 nonce 核对 | 100% 拒绝 |
| 跨操作同 nonce 重放 | 100% 拒绝 |
| 重启后已消费 nonce | 100% 拒绝 |
| verifier 返回 `1` 或 `False` | 100% 拒绝 |
| verifier 失败后的 nonce | 不消费，状态不变 |
| 非 ambiguous 状态 | 不触发 verifier，不修改 |
| Python 3.10 / 3.12 全部测试 | 失败 0，待 CI 证实 |
| 真实设备写入 | 0 |

**下一步测试**：用 `multiprocessing` 两进程共享数据库同时核对同一 nonce；故障注入在 INSERT 后 UPDATE 前抛异常，验证事务回滚；测试 WAL/锁超时；模拟不同 nonce 指向同一 receipt_id 的重放；记录真实 CI 日志与版本。

## ⑥ 版本差异、阻塞与下一步

11/12 解决调用方自述绕过；11/13 增加 nonce 唯一索引、事务内消费及四类回归。尚未运行 pytest，且未实现可信回执认证、签名验证、防不同 nonce 重包装、远端事实查询、执行器实际接入与真实环境负载测试。

下一步按依赖顺序实现 `TrustedReceiptVerifier`：签名发行方白名单、`op_id/outcome/receipt_id/nonce/issued_at/expires_at` 绑定，先事务外获取可缓存远端证据，再事务内验证；补充并发/故障注入测试和 CI 运行证据。禁止使用模型自述作为远端事实。

## 参考与证据等级

- 本仓库 Outbox 源码及前序工程报告：直接可审计源码（非运行验证）。
- Python sqlite3 事务与锁：https://docs.python.org/3/library/sqlite3.html
- SQLite 事务：https://www.sqlite.org/lang_transaction.html
- SQLite UNIQUE 约束：https://www.sqlite.org/lang_createtable.html#uniqueconst
- pytest：https://docs.pytest.org/en/stable/

本次没有引入新新闻、没有创造 Hint 编号，也没有公开敏感资料。
