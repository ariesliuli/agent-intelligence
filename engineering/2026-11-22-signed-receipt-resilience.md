# 2026-11-22｜签名回执并发、重启与锁竞争验证（Signed Receipt Resilience Verification）

**状态**：新增可执行 pytest 测试已提交；GitHub 回读/CI 尚待本次核对；真实设备与生产部署均未进行。**不新增 Hint**，仓库 `state/processed.json` 当前登记最高 HINT-026。

## ① 今日建设目标及关联 Hint
按 `AGENTS.md`、`README.md`、`state/processed.json`、`hints/HINT-026.md` 和 11/21 工程报告核对：上一版已把 HMAC 验证、Receipt 唯一消费和 Outbox 状态迁移纳入同一 SQLite `BEGIN IMMEDIATE`，但并发、重启、锁冲突未验证。本次仅补这些关键边界，不重复发明状态机或新 Hint。关联 HINT-002/005/013/023/026；历史 HINT-001～023 原文不完整，不能宣称全量语义去重。

## ② 框架位置、模块边界及上下游
```text
OpenClaw 主控（尚未接入）
  -> Codex CLI / Claude Code / Node-RED（候选结果，非可信发行者）
  -> 独立发行者签名 envelope（当前仅离线合成）
  -> Outbox.reconcile_signed(op_id,outcome,envelope,keys)
     -> SQLite BEGIN IMMEDIATE
     -> 验证 operation.state == ambiguous
     -> 从持久 payload 计算 sha256
     -> 验证 HMAC + op/outcome/digest/时间
     -> UNIQUE(issuer,receipt_id) 消费
     -> UPDATE operations.state
     -> COMMIT 或 ROLLBACK
  -> 下游事件唤醒闭环（HINT-026，尚未接入）
```
此测试不授予任何设备写入权限，也不把签名视为外部事实证明。真实设备需独立核对器与人工审批。

输入 JSON（MAC 为运行时生成）：
```json
{"op_id":"op1","outcome":"pending","envelope":{"alg":"HS256","body":{"issuer":"simulator","receipt_id":"r1","op_id":"op1","outcome":"pending","issued_at":90,"expires_at":110,"payload_digest":"sha256:<64 hex>"},"mac":"<64 hex>"}}
```
建议配置 YAML（设计契约，不存在加载器）：
```yaml
mode: offline_simulator
device_write: false
issuer_keys: injected_synthetic_only
sqlite:
  begin_mode: IMMEDIATE
  busy_timeout_seconds: 10
  receipt_unique_scope: [issuer, receipt_id]
recovery:
  on_locked: remain_ambiguous
  auto_retry_external_side_effect: false
```

## ③ 具体实现（可直接交给 Codex / Claude Code）
新增 `framework/tests/test_signed_outbox_resilience.py`，完全使用 Python 标准库与 pytest，无真实网络 IO：
1. `test_concurrent_same_receipt_at_most_once`：8 个线程、各自独立 Outbox 连接、Barrier 同时提交同一有效签名；必须恰好一次返回 `True`、7 次 `False`，回执表只记录 1 条，操作变为 pending。
2. `test_restart_preserves_receipt_consumption`：成功提交后重新构造 Outbox；状态与唯一消费保持，重复提交不得再次推进。
3. `test_sqlite_lock_timeout_does_not_consume_receipt`：另一个连接持有 `BEGIN IMMEDIATE`；核对遇到 SQLite locked 错误，operation 仍 ambiguous、回执 0；释放锁后同一回执可以合法完成。

运行：
```bash
cd framework
python -m pytest -q tests/test_signed_outbox_resilience.py
python -m pytest -q tests/
```
CI 配置：`.github/workflows/framework-ci.yml`，Ubuntu 26.04、Python 3.10/3.12、pytest 8.3.5。必须以对应 commit 的真实 Actions 运行结果作为验收证据；不能以测试文件存在冒充测试通过。

## ④ 具体经验（待验证经验）
**触发条件**：网络操作超时后进入 `ambiguous`，多个执行器同时收到相同回执，或 Ubuntu 常驻服务重启。
**环境**：Python 3.10/3.12 目标、SQLite 单库、本地合成 HMAC。
**现象**：此前仅覆盖顺序调用与单次故障回滚；并发、锁争用和重启后的消费持久性缺少测试证据。
**因果假设**：`BEGIN IMMEDIATE` 的单写者串行化加 `PRIMARY KEY(issuer,receipt_id)` 可保证单库内最多一次成功消费；锁冲突不会消耗回执。
**替代根因**：线程测试可能因共享连接、SQLite busy timeout、文件系统锁语义或 runner 版本而不稳定；真实发行者可伪造事实则不受此门禁保护。
**解决步骤**：独立连接并发竞争、重启重建对象、持锁注入 OperationalError，核对状态与唯一索引。
**证据/验证**：测试源码已归档；CI 实测结果以 Actions 为准，尚未声明通过。
**适用边界**：同一 SQLite 数据库；不证明跨主机分布式 exactly-once，不证明远端设备状态。
**回滚**：停用自动 reconcile_signed，保留 ambiguous 人工核对；绝不自动重试未知副作用。
**7/30/90 天复查**：7 天核对两版本 CI；30 天补多进程及进程崩溃故障注入；90 天评估独立 issuer 与部署后事实核验。

## ⑤ 验证与可量化验收
| 指标 | 门槛 | 状态 |
|---|---|---|
| 并发同回执 8 路竞争 | 1 成功、7 无副作用、Receipt=1 | 测试已提交，待 CI |
| 进程对象重建后重复核对 | 0 次重复状态推进 | 测试已提交，待 CI |
| SQLite 锁竞争 | 锁期间 Receipt=0 且 ambiguous；解锁后可成功 | 测试已提交，待 CI |
| Python 3.10/3.12 全量 pytest | 0 非预期失败 | 待 CI 核验 |
| 真实设备写入 | 0 | 未接入 |
| 真实生产净收益/ROI | null | 未测量 |

## ⑥ 版本差异、剩余问题及下一步
11/21 已实现单事务验签与回执消费；11/22 增加并发、重启与锁冲突回归测试，不修改生产接口，也不更新 Hint 编号。下一步检查真实 CI；若失败先按生产缺陷、测试契约、runner 环境三类归因。随后补多进程竞争、强制终止进程后 WAL/rollback journal 恢复测试，以及可配置 busy timeout。再接入 HINT-026 的事件唤醒，但不能将模型自签回执作为真实设备完成证明。

官方参考：SQLite 事务 https://www.sqlite.org/lang_transaction.html ；Python sqlite3 https://docs.python.org/3/library/sqlite3.html ；Python concurrent.futures https://docs.python.org/3/library/concurrent.futures.html 。所有验收数值均为门槛而非已达成收益。
