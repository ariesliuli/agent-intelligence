# 2026-11-16｜回执身份重放缺口回归（Receipt Identity Replay Gap Regression）

> 状态：已提交 **strict xfail 预期失败测试**；尚未取得 pytest/CI 运行日志；安全修复未完成。该测试只验证当前设计缺口，不是生产验证器。GitHub 不含凭证和客户信息。

## ① 今日建设目标及关联 Hint

核对 `AGENTS.md`、`README.md`、`state/processed.json`、Outbox 实现、11/14～15 测试与工程报告、HINT-025。登记最高 HINT-025，历史 HINT-001～023 原文不完整，无法保证语义全量去重。关联 HINT-002/005/013/023；不新增 Hint。

昨日已加入 20 轮双进程 nonce 竞争测试，但 **nonce 唯一并不代表远端 receipt 唯一**。本次选择单一未完成安全边界：不同 nonce 包装相同 `receipt_id`，可能分别授权不同操作。当前 `Outbox.reconcile` 只检查 nonce 表和注入 verifier 的布尔返回值；测试中的 permissive verifier 不是可信认证。今天先把缺口编码成可执行的、严格标记的预期失败回归，避免误将 nonce 门禁宣称为回执身份门禁。

## ② 架构位置和上下游接口

```text
OpenClaw / Codex CLI / Claude Code（尚未实际接入）
    → IntentFacade / Outbox → ambiguous
    → [未来：远端只读取证 + 签名/issuer/时效校验]
    → BEGIN IMMEDIATE
    → [缺失：receipt_id 唯一性 + receipt/op_id 绑定]
    → nonce INSERT → operation UPDATE → COMMIT
```

合成输入：
```json
{"op_id":"op-a","outcome":"pending","evidence":{"op_id":"op-a","outcome":"pending","nonce":"nonce-a","receipt_id":"receipt-1"}}
```
攻击模拟：另一操作 `op-b` 使用 `nonce-b` 和相同 `receipt-1`。期望第二次抛 `PermissionError("replayed_receipt")` 且 `op-b` 仍为 `ambiguous`；现有实现并无这一检查。

## ③ 具体实现细节（可直接交给 Codex）

已新增 `framework/tests/test_outbox_receipt_replay_gap.py`：建立两个独立 ambiguous 操作；以相同 receipt_id、不同 nonce 依次核对；要求第二个被拒绝。使用 `@pytest.mark.xfail(strict=True)` 明确此缺口 **尚未修复**。一旦修复后出现 XPASS，strict 模式会将其视为失败，提醒维护者移除 xfail 并转为普通正向测试。

本次不改生产 Outbox，避免在未设计签名、发行者与迁移策略前错误地赋予 `receipt_id` 可信含义。

下一最小修复任务：
1. 增加 `reconciliation_receipts(issuer TEXT, receipt_id TEXT, op_id TEXT, consumed_at REAL, PRIMARY KEY(issuer,receipt_id))`；仅从独立验证器返回的 **已认证结构化结果** 取值，不信任输入 JSON 自称的 issuer。
2. 可信验证器返回严格结构 `VerifiedReceipt(issuer, receipt_id, op_id, outcome, issued_at, expires_at, payload_digest)`；在验证器外完成远端读取，在 SQLite 事务内只做有界本地验签/一致性检查。禁止网络 IO 持有写锁。
3. 在同一 `BEGIN IMMEDIATE` 内先检查 receipt 唯一性、op_id/outcome/摘要/时间窗，再写 receipt、nonce 与状态；任一步异常全部回滚。
4. 不接受没有 issuer/receipt_id/有效期或验证失败的证据；迁移前保留旧数据库备份，默认拒绝未知旧回执，不能自动放行。
5. verifier 需要可信密钥来源（环境/密钥服务），不能在公共仓库、日志或测试夹具内放真实凭证。测试用合成签名材料，明确非生产密钥。

建议输出契约：
```json
{"verified":true,"issuer":"simulated-issuer","receipt_id":"receipt-1","op_id":"op-a","outcome":"pending","issued_at":100,"expires_at":130,"payload_digest":"sha256:simulated","evidence_level":"simulated"}
```

建议配置（**设计示例，不代表当前代码支持**）：
```yaml
receipt_gate:
  require_authenticated_issuer: true
  require_unique_receipt_id: true
  reject_missing_expiry: true
  clock_skew_seconds: 5
  fail_closed: true
  network_inside_write_transaction: false
```

执行：
```bash
cd framework
python -m pytest -q tests/test_outbox_receipt_replay_gap.py -rx
python -m pytest -q tests/
```
运行前应先确认 Python 3.10/3.12、pytest 8.3.5 与现有 workflow；本次尚未取得运行日志。

## ④ 具体经验（待验证经验）

- 触发：nonce 防重放已实现，被误解为远端事实不可重复消费。
- 环境：Python SQLite Outbox 原型，`reconciliation_nonces` 表。
- 现象：源码静态检查表明只对 nonce 建唯一索引；同一 receipt_id 不受约束；两个不同操作可使用不同 nonce。
- 根因假设：把一次提交的随机 nonce 当作远端回执的稳定业务身份；忽略了不同身份空间。
- 替代解释：生产 verifier 如果本来独立绑定 receipt/op_id 并拒绝复用，可能已在外层缓解；但当前仓库未提供这种生产实现。
- 处理：提交 strict xfail 负样例，先显式暴露风险，再设计 issuer+receipt_id 的持久化门禁。
- 证据：Outbox 源码与测试文件；pytest 结果 `null`；真实部署 `null`。
- 适用边界：本地单主机 SQLite，不证明远端设备 exactly-once，也不适用于任意可伪造 receipt_id。
- 回滚：撤销新增测试文件即可恢复前一测试集；不应将撤销测试误认为风险消失。7/30/90 天复查缺口修复、CI 失败率和回执身份冲突。

## ⑤ 验证步骤及量化验收

| 检查 | 门槛 | 本次状态 |
|---|---|---|
| 已知缺口回归 | 当前应 XFAIL；修复后 XPASS 触发 strict 提醒 | 源码已提交，未运行 |
| 相同 receipt_id / 不同 nonce | 第二次 100% 拒绝 | 未实现 |
| 不同 issuer / 相同 receipt_id | 按发行者作用域明确处理 | 未实现 |
| receipt/op/outcome/expiry 绑定 | 合成负例 100% 拒绝 | 未实现 |
| 故障注入 | receipt、nonce、状态全回滚 | 未实现 |
| Python 3.10 / 3.12 | 全量 pytest 0 非预期失败 | 未验证 |
| 外部真实设备调用 | 0 | 仅模拟测试 |

注意 `xfail` 不是安全通过率；必须在修复后移除标记，加入独立认证与故障注入测试才可声称门禁完成。

## ⑥ 相对上一版差异、剩余问题与下一步

11/15 验证多进程争抢 **同一 nonce**；11/16 新增 **不同 nonce 复用同一远端 receipt** 的严格预期失败测试，明确两种身份空间的差别。未改变 Outbox 运行逻辑、未新增 Hint、未宣称修复或 CI 成功。

下一步优先运行 CI 并取得日志；再实现 `TrustedReceiptVerifier` + 发行者作用域的 receipt 唯一索引，移除 xfail 并添加签名篡改、过期、跨操作重放及事务回滚测试。未经认证的模型输出不得解锁重试。

参考：
- Python pytest xfail：https://docs.pytest.org/en/stable/how-to/skipping.html
- SQLite unique constraints：https://www.sqlite.org/lang_createtable.html
- SQLite transactions：https://www.sqlite.org/lang_transaction.html
- 本仓库：`framework/agent_core/outbox.py`、`engineering/2026-11-15-multiprocess-reconciliation-race.md`
