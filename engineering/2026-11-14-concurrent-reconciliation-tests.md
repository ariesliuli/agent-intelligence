# 2026-11-14｜并发核对与事务回滚回归（Concurrent Reconciliation & Atomic Rollback Tests）

> 状态：**测试源码已提交；pytest/CI 未实测；不代表生产验证。** 不新增 Hint，不触及真实设备、网络或客户数据。

## ① 今日建设目标与关联 Hint
核对 `AGENTS.md`、`README.md`、`state/processed.json`、`framework/agent_core/outbox.py`、`framework/tests/test_outbox.py` 与 11/13 工程报告。登记最高编号 HINT-025，001～023 原文不完整。沿用 HINT-002/005/013/023 的任务契约、恢复与独立审计方向。11/13 已实现 SQLite `BEGIN IMMEDIATE` 与 nonce 唯一表，但缺少并发/故障注入测试；且 `test_verifier_truthy_non_bool_rejected` 在传入缺失 nonce 的证据时，先命中 nonce 检查，未真正测试 verifier 严格布尔判断。本次只补这些可复现的测试缺口。

## ② 框架位置、接口及数据流
```text
OpenClaw（未接入）→ Router（原型）→ IntentFacade → SQLite Outbox
→ ambiguous → reconcile(op_id, outcome, evidence)
→ BEGIN IMMEDIATE → state/nonce check → verifier → INSERT nonce → UPDATE state → COMMIT
Codex CLI / Claude Code / Node-RED（尚未接入）
```
接口示例（仅模拟）：
```json
{"op_id":"op1","outcome":"pending","evidence":{"op_id":"op1","outcome":"pending","nonce":"race-1"}}
```
`pending` 只能由**可信远端无副作用证据**授权；本次测试用 `lambda: True` 仅模拟事务机制，不能用作生产 verifier。

## ③ 实现细节与最小执行
新增 `framework/tests/test_outbox_concurrency.py`：
1. 两个不同 Outbox 实例共享一个 SQLite 文件，`Barrier(2)` 同步发起相同 nonce 的核对；期望一个 `True`、一个 `False`，最终状态 `pending` 且 nonce 表只有一条记录。
2. SQLite `BEFORE UPDATE` trigger 对 `ambiguous → pending` 注入 `RAISE(ABORT)`；期望状态仍 `ambiguous`、nonce 插入回滚。删除 trigger 后用同一 nonce 成功核对。
3. 修复 `test_verifier_truthy_non_bool_rejected`，加入有效 nonce，使测试真正到达 `verifier(...) is not True` 分支，阻止整数 `1` 伪装为布尔 `True`。

目录：
```text
framework/agent_core/outbox.py
framework/tests/test_outbox.py
framework/tests/test_outbox_concurrency.py  # 新增
engineering/2026-11-14-concurrent-reconciliation-tests.md
```
离线运行：
```bash
cd framework
python -m compileall -q agent_core tests
python -m pytest -q tests/test_outbox.py tests/test_outbox_concurrency.py
python -m pytest -q tests/
```
建议 CI 使用 Python 3.10 和 3.12；若 `pytest` 导入失败，先检查 `framework/pyproject.toml` 与工作目录，不修改业务安全逻辑绕过错误。

## ④ 可复用具体经验（待验证经验）
- 触发：已有测试宣称覆盖严格布尔 verifier，却在前置输入校验失败。
- 环境：Python pytest、SQLite Outbox 原型。
- 现象：静态代码显示 `test_verifier_truthy_non_bool_rejected` 未提供 nonce，`reconcile()` 会先抛 `reconciliation_nonce_required`，而测试期待 `unverified`；这是可审计的测试缺陷，不是已运行结果。
- 根因：测试数据未满足被测分支的前置条件；异常覆盖率不等于分支实际到达。
- 修复：补有效 nonce；另以并发争用和触发器故障注入验证事务原子性。
- 替代解释：未来若仍失败，应检查 pytest 运行路径、SQLite 锁超时、版本和 trigger 异常类型，不直接归因于事务逻辑。
- 证据：源码对照；运行证据 `null`，CI `null`。
- 适用边界：仅验证本地 SQLite 事务和 Python 代码，不证明远端设备 exactly-once、签名可信或网络异常恢复。
- 回滚：删除新测试文件可撤销新增测试；安全修复不应回滚到无 nonce 版本。7/30/90 天复查 flaky 比例、锁等待、异常覆盖和失败重试。

## ⑤ 验证及量化验收
| 指标 | 目标 | 本次状态 |
|---|---|---|
| 并发同 nonce 双提交 | 100 次重复均恰好 1 成功，nonce 计数 1 | 未运行；现有用例只执行一次 |
| UPDATE 注入失败 | 状态与 nonce 100% 回滚 | 未运行 |
| 删除 trigger 后重试 | 同 nonce 能成功一次 | 未运行 |
| verifier 返回整数 1 | 100% 拒绝，命中 `unverified` 分支 | 源码已修，未运行 |
| 全量 pytest / Python 3.10、3.12 | 失败 0 | 未运行 |
| 真实设备操作 | 0 | 无设备接口调用 |

注意：当前测试的并发断言只做一次竞争，不能代替 100 次压力测试；线程共享本地文件，不等于多进程/多主机部署验证。

## ⑥ 相对上一版本的差异、剩余问题与下一步
11/13 只有事务/nonce 实现与单线程测试；11/14 增加两个独立离线测试，并修复一个未真正到达目标分支的测试。下一步先取得 GitHub Actions 的真实 pytest 结果，再做 100 次随机并发及多进程故障注入。随后实现 `TrustedReceiptVerifier`：发行者白名单、`receipt_id` 唯一性、操作身份绑定、时效与签名校验。网络取证必须在事务外完成；事务内只做有界本地验证，避免 SQLite 写锁长期持有。

## 参考
- Python sqlite3：https://docs.python.org/3/library/sqlite3.html
- SQLite transactions：https://www.sqlite.org/lang_transaction.html
- SQLite CREATE TRIGGER：https://www.sqlite.org/lang_createtrigger.html
- pytest：https://docs.pytest.org/en/stable/
- 本仓库 2026-11-13 报告：`engineering/2026-11-13-atomic-reconciliation-nonce.md`

**安全声明**：所有身份、nonce 和路径均为模拟；无密钥、客户数据、内部地址或真实设备凭证。
