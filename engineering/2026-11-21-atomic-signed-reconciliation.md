# 2026-11-21｜签名回执与 Outbox 原子核对（Atomic Signed Receipt Reconciliation）

**状态：代码和合成测试已提交；GitHub 回读待核验；CI/pytest 结果未核验；未接入真实设备。** 不新增 Hint。仅使用合成密钥与模拟 payload。

## ① 今日建设目标及关联 Hint
读取 `AGENTS.md`、`README.md`、`state/processed.json`、`HINT-026.md`、11/20 工程报告及 `framework/agent_core/{outbox,receipt_gate,signed_receipt}.py` 和相关测试。当前最高 HINT-026；历史 HINT-001～023 原文未完整归档，不声称已做完整语义去重。

针对 11/20 遗留的关键缺口：原有 `Outbox.reconcile()` 只消费 nonce；`consume_verified_receipt()` 的唯一回执表未接入 Outbox。此前的离线签名验证与状态迁移没有形成单一原子提交。关联 HINT-002/005/013/023 与 HINT-026 事件闭环。今天只实现该接口，不复制事件编排。

## ② 框架位置与上下游接口
```text
OpenClaw (未接入) -> Codex/Claude/Node-RED (不可信候选事件)
    -> 受控离线签名模拟器 envelope
    -> Outbox.reconcile_signed(op_id, outcome, envelope, keys=...)
       -> BEGIN IMMEDIATE
       -> 读取 ambiguous operation + 原始 payload
       -> SHA-256 payload 摘要绑定 + HMAC 验证 + 时间窗校验
       -> reconciliation_receipts UNIQUE(issuer,receipt_id)
       -> operations.state/result UPDATE
       -> COMMIT
```
上游不允许模型自己生成可信 keyring；真实设备写入需要独立的远端事实核验、审批和审计。下游成功返回 bool；不可信输入抛 `PermissionError`；数据库写入失败回滚。

输入 JSON（MAC 运行时计算）：
```json
{"op_id":"op1","outcome":"pending","envelope":{"alg":"HS256","body":{"issuer":"simulator","receipt_id":"r1","op_id":"op1","outcome":"pending","issued_at":90,"expires_at":110,"payload_digest":"sha256:<实际操作payload的64位hex摘要>"},"mac":"<64位hex>"}}
```
设计配置（尚无 YAML 加载器）：
```yaml
reconciliation:
  mode: offline_simulator
  key_source: injected_test_keyring
  device_write: false
  allow_model_issued_receipts: false
  require_ambiguous_state: true
  receipt_unique_scope: [issuer, receipt_id]
  transaction: BEGIN_IMMEDIATE
```
成功返回 `true`；若状态不是 `ambiguous` 返回 `false`；结果 `result` 只存 `issuer`、`receipt_id` 与认证标志，不持久化密钥或签名原文。

## ③ 可直接执行的实现细节
- 修改 `framework/agent_core/outbox.py`：初始化时建立 `reconciliation_receipts` 表；新增 `reconcile_signed()`，在一个 `BEGIN IMMEDIATE` 中完成操作状态读取、对已存 payload 计算摘要、HMAC 验签、receipt 唯一消费与状态迁移。原 `reconcile()` 暂不变，避免破坏兼容。
- 新增 `framework/tests/test_signed_outbox_atomic.py`：有效签名、未签名篡改、错误 payload、错误 keyring、跨操作重放、UPDATE 故障回滚、非 ambiguous 状态共七类合成测试。
- 不引入外部依赖；Python 标准库 `sqlite3`/`hashlib`/`hmac`，pytest 测试。
- 执行：`cd framework && python -m pytest -q tests/test_signed_outbox_atomic.py && python -m pytest -q tests/`；在 GitHub Actions Python 3.10/3.12 上确认运行 ID、commit SHA 和失败数。
- 约束：签名认证不等于真实设备动作完成；此接口只供离线信任域模拟。真实环境必须增加可信独立核对器及 issuer 密钥隔离，不允许任意受控执行器自签“已完成”。

## ④ 具体经验（待验证经验）
**触发**：网络写入超时后 operation 进入 ambiguous；两个执行器或重试流程试图使用同一回执确认状态。
**环境**：SQLite + Python；离线合成 HMAC 发行者；无真实设备。
**现象**：原实现存在两个相互独立的消费路径，未保证 receipt 唯一性与状态变化同一提交。
**根因假设**：模块演进时先后实现 Receipt Gate 和 Outbox Nonce Gate，缺少跨模块事务契约。
**替代根因**：若真实发行者可被执行器控制，原子性再好也无法证明远端动作事实。
**解决**：在持有 SQLite 写事务期间验签、消费唯一回执、更新操作状态；事务异常回滚。
**验证**：新增故障触发器使状态 UPDATE 失败，断言回执插入也回滚；CI 实测 = null。
**边界**：SQLite 单库原子性；不提供分布式 exactly-once，不验证设备实际状态，也不证明独立性。
**回滚**：停用 `reconcile_signed` 调用，保留 `ambiguous` 进入人工核对；回滚该方法及测试；不得退回无验证的自动重试。
**复查**：7 天核对 CI；30 天补并发、SQLite 锁、进程重启；90 天评估可信发行者隔离与真实设备只读对照。

## ⑤ 验证与可量化验收
| 指标 | 门槛 | 当前状态 |
|---|---|---|
| 七类合成测试 | 全部通过 | 已提交，运行待确认 |
| Python 3.10/3.12 全套 pytest | 非预期失败 0 | 未核验 |
| 签名/摘要篡改 | 100% 拒绝，状态不变 | 测试已提交 |
| 跨操作 receipt_id 重放 | 100% 拒绝 | 测试已提交 |
| 状态更新异常 | receipt 与 operation 同时回滚 | 测试已提交 |
| 并发竞争 / 崩溃重启 | 0 重复消费 | 待测试 |
| 外部设备写入 | 0 | 未接入 |
| 真实部署收益、工时与 ROI | null | 未测量 |

## ⑥ 相对上一版本与下一步
11/20 仅加固畸形输入；11/21 把签名验证、receipt 唯一约束和 Outbox 状态迁移组合为同一 SQLite 事务。未把原 `reconcile()` 的 nonce 与新 receipt 表合并，且未完成外部独立事实验证，不能称为生产级可信回执。

下一步先验证 CI，再做多线程/多进程并发、SQLite 锁冲突、重复回执、重启持久化和边界输入 fuzz。通过后设计 `TrustedReceiptVerifier` 独立发行者服务，最后才接入 HINT-026 的部署后复测闭环。

参考：Python `hmac` https://docs.python.org/3/library/hmac.html ；SQLite 事务 https://www.sqlite.org/lang_transaction.html ；SQLite UNIQUE https://www.sqlite.org/lang_createtable.html 。
