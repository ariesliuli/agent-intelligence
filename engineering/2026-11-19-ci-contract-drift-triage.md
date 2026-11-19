# 2026-11-19｜跨版本 CI 失败归因与契约漂移修复（CI Contract Drift Triage）

> 状态：读取 GitHub Actions run 44211768234 两个原始 job 日志，并回读仓库测试；两个失败用例已在仓库中由其他提交修正，**尚未取得修正后 CI 全绿证据**。本报告是诊断与验证契约，不声称部署或生产安全修复。不新增 Hint。

## ① 今日建设目标与关联 Hint

关联 HINT-002/005/013/023 与 11/16–18 Receipt/Outbox 工程报告。先核对 AGENTS.md、README.md、state/processed.json（last_hint_id=25）、Outbox、signed_receipt、receipt_gate、集成测试与签名测试。目标优先解除 Python 3.10/3.12 CI 红灯，而非继续堆叠安全原型。历史 HINT-001～023 全量原文尚未恢复，不主张完成全量语义去重。

## ② 架构位置、上下游与接口

```text
GitHub Actions matrix Python 3.10 / 3.12
  -> compileall [通过]
  -> pytest tests/ [失败：两个旧/错误测试契约]
  -> Outbox.reconcile(op_id, outcome, evidence: dict)
       -> fail-closed when no independent reconciliation_verifier
  -> verify_signed_receipt(envelope, keys, op_id, outcome, payload_digest, now)
       -> signed receipt_id can vary; identity uniqueness is separate SQLite gate
  -> receipt_gate.consume_verified_receipt(...) [尚未与 Outbox 原子集成]
```

请求契约（合成，无客户数据）：
```json
{"op_id":"op-1","outcome":"pending","evidence":{"op_id":"op-1","outcome":"pending","nonce":"n-1"}}
```
配置（建议、未落地）：
```yaml
ci:
  python: ["3.10", "3.12"]
  pytest: "8.3.5"
  require_zero_unexpected_failures: true
reconciliation:
  require_trusted_verifier: true
  allow_unverified_string: false
receipt:
  receipt_id_binding: signed_body
  uniqueness_scope: ["issuer", "receipt_id"]
```

## ③ 失败定位、实现任务与状态机

原始 run： https://github.com/ariesliuli/agent-intelligence/actions/runs/44211768234

两个 Python 版本均为 **106 passed, 2 failed, 1 xfailed**。pytest 8.3.5 安装成功、compileall 成功。失败：
1. `test_integration_contract.py::test_reconcile_requires_evidence_but_not_authentication_yet`：旧测试期望 `reconcile(..., "unverified-string")` 成功；当前 Outbox 强制 evidence 为 dict，且未注入可信 verifier 时拒绝核对。这是测试与 fail-closed 安全契约漂移，不能为了通过测试重新允许未认证字符串。
2. `test_signed_receipt.py::test_signed_but_wrong_binding_rejected[change0]`：旧测试认为持有正确签名但不同 `receipt_id` 应拒绝；实际验证器只绑定签名内容与请求的 op_id/outcome/payload_digest。合法的新 receipt_id 应通过验签；**重复消费**必须由 `issuer + receipt_id` 数据库唯一约束拒绝，不能在验签层写死一个 ID。

在本次检查过程中，仓库已出现与上述归因一致的更新：集成测试现改为断言无 verifier 时 fail-closed；签名测试已把变更 receipt_id 移出拒绝参数集，并增加有效新 ID 正例。由于文件在诊断过程中发生并发变化，未覆盖已有修正，也未声称这些变更由本报告提交。需使用新 commit 的 CI 结果确认。

交给 Codex 的最小任务：
1. 拉取最新 main，记录 SHA；运行 `cd framework && python -m pytest -q tests/ -rx`，分别在 Python 3.10/3.12 执行。
2. 保留无 verifier 拒绝、未签名 receipt_id 篡改拒绝、已正确签名新 ID 允许、数据库重放拒绝四条互补契约。
3. 若两版本全绿，更新 CI 文档记录 job URL 与 SHA；否则按首个 traceback 修复，不修改安全门禁去迁就旧断言。
4. 独立安排 `reconciliation_receipts` 与 `reconciliation_nonces`、operation UPDATE 的同一 SQLite `BEGIN IMMEDIATE` 事务；该安全缺口仍未关闭。

## ④ 具体经验（已验证 CI 失败归因；修复效果待验证）

触发：11/18 run 同时在 Python 3.10 和 3.12 失败。环境：GitHub Actions Ubuntu 26.04、pytest 8.3.5、Python 3.10.22 / 3.12.16。现象：两个版本相同两条失败，编译通过。根因：测试契约滞后于安全收紧；以及把 Receipt 身份认证与重复消费混为一谈。替代根因（Node 20 警告、Ubuntu 迁移、Python 版本不兼容）与实际 traceback 不符。修复步骤：更新测试以保留 fail-closed，区分签名合法性和数据库重放。证据：两个 job 的原始 traceback 与修订后的测试源码；**修复后 CI 结果=null**。适用边界：测试契约漂移诊断，不证明真实设备回执可信。回滚：只回滚不正确的测试变更，不放宽 Outbox 验证器。7/30/90 天复查：跨版本 CI 稳定率、重放测试与独立认证接入进度。

Node 20 deprecated 提示来自 `actions/checkout@v4` 与 `actions/setup-python@v5`，建议独立升级至支持新 Node runtime 的主版本并验证；Ubuntu 26 迁移为环境变更提示，**均不是本次两条 pytest 失败的直接证据**。

## ⑤ 验证步骤与量化验收

| 指标 | 门槛 | 当前 |
|---|---|---|
| 旧 run Python 3.10/3.12 | 归因完整 | 已查日志：每组 106 pass / 2 fail / 1 xfail |
| 修正后 Python 3.10/3.12 | 两组 0 unexpected fail | 未取得 CI 证据 |
| 无 verifier 核对 | 100% 拒绝 | 测试已更新，未复跑 |
| 合法签名新 receipt_id | 100% 允许 | 测试已更新，未复跑 |
| 签名篡改 / DB 重放 | 100% 拒绝 | 需回归 |
| 真实 Outbox 三表原子事务 | 0 部分提交、0 重放成功 | 尚未实现 |

## ⑥ 与上一版本差异、阻塞及下一步

11/18 是离线签名认证原型，未执行 CI；今天取得实际跨版本失败日志，确定两个具体断言错误，并发现测试已在诊断期间被更新。剩余阻塞：缺少修正后的绿色 run、真实可信 issuer、Outbox 原子集成。下一步按依赖顺序：先跑全量 CI，再做原子事务与故障注入，最后才考虑生产信任域。公开报告不含密钥、客户信息、设备凭证或内部地址。

参考：
- Python HMAC：https://docs.python.org/3/library/hmac.html
- SQLite 事务：https://www.sqlite.org/lang_transaction.html
- GitHub Actions Node 20 迁移：https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
