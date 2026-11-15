# 2026-11-15｜跨进程核对竞争回归（Multiprocess Reconciliation Race Regression）

> 状态：**多进程测试源码已提交；未取得 pytest/CI 实测结果。** 不新增 Hint；不接触真实设备或客户环境。

## ① 今日建设目标与关联 Hint
核对 `AGENTS.md`、`README.md`、`state/processed.json`、Outbox 源码、既有单进程/线程测试、11/13～11/14 工程报告和 CI workflow。登记最高 HINT-025；001～023 原文部分属于重建，不能假装已完整核实。关联 HINT-002/005/013/023。11/14 已覆盖单次线程竞争及 UPDATE 触发器回滚，但仍缺**真正独立进程竞争**；因此本次只补这一测试层级，不重复设计核对状态机。

## ② 架构位置与上下游接口
```text
OpenClaw / Codex CLI / Claude Code（尚未接入）
  → Router → IntentFacade → SQLite Outbox（当前原型）
  → ambiguous → reconcile(op_id, outcome, evidence)
  → BEGIN IMMEDIATE → nonce 检查 → verifier → nonce INSERT → state UPDATE
  → SQLite COMMIT
```
本次测试以 `multiprocessing.get_context("spawn")` 创建两个独立 Python 进程，连接同一 SQLite 文件。每轮建立新数据库和新 nonce；主进程准备 `ambiguous`，子进程通过 ready Queue + Event 同步开始，结果经 Queue 回传。没有 HTTP/MQTT/CGI 设备调用。

输入 JSON（合成）：
```json
{"op_id":"op1","outcome":"pending","evidence":{"op_id":"op1","outcome":"pending","nonce":"nonce-0"}}
```
结果契约：两个竞争进程应恰好一个返回 `True`，另一个返回 `False`；状态 `pending`；nonce 表仅一条。第二个返回 `False` 是因其进入事务后看到状态已非 `ambiguous`，不是授权失败。生产可信 verifier 仍缺失。

## ③ 具体实现与最小执行
新增 `framework/tests/test_outbox_multiprocess.py`，以 pytest 参数化运行 20 轮，每轮独立数据库和两个 spawn 子进程。使用 `Queue.get(timeout=...)`、`Event.wait(timeout=...)` 避免无限等待；finally 中 join、terminate 和检查退出码，防止 CI 残留进程。

```yaml
module: sqlite_outbox_multiprocess_race
python: ["3.10", "3.12"]
test_file: framework/tests/test_outbox_multiprocess.py
rounds: 20
processes_per_round: 2
database: isolated_sqlite_file_per_round
network: disabled
expected:
  true_count: 1
  false_count: 1
  nonce_rows: 1
  final_state: pending
```

本地命令：
```bash
cd framework
python -m compileall -q agent_core tests
python -m pytest -q tests/test_outbox_multiprocess.py
python -m pytest -q tests/
```
CI 现有 `.github/workflows/framework-ci.yml` 使用 ubuntu-latest、Python 3.10/3.12、pytest 8.3.5，push 到 framework 路径触发。**workflow 配置存在不等于已执行成功**；必须回读运行日志确认。

## ④ 具体经验：待验证经验（Pending Validation）
- 触发：原有单线程竞争测试被当作跨进程安全保证。
- 环境：SQLite 单文件数据库；Python multiprocessing spawn；pytest。
- 现象：静态可证，11/14 测试用 `ThreadPoolExecutor`，虽然每线程独立连接 SQLite，但不能验证进程隔离、spawn 导入和多进程锁竞争。
- 根因假设：测试环境的并发维度低于实际 Ubuntu 常驻多执行器的进程维度。
- 处理：新增独立进程同步起跑、每轮隔离状态、可观察成功/失败及 nonce 计数、子进程回收。
- 替代根因：若 CI 失败，先检查 spawn 导入、机器调度、超时、SQLite 锁、测试启动时间；不能立即断言数据库事务有缺陷。
- 证据：源码已提交；运行日志 null；性能数据 null；生产部署 null。
- 适用边界：单主机 SQLite 文件，不覆盖 NFS/共享文件系统、多主机、签名认证、设备端 exactly-once 或远端执行幂等。
- 回滚：删除本测试文件即可撤销测试增量；不要撤销既有安全门禁。7/30/90 天观察 CI flaky 率、运行时长、数据库锁等待和真实回执失败案例。

## ⑤ 验证与量化验收
| 项目 | 目标 | 现状 |
|---|---|---|
| 20 轮独立双进程竞争 | 20/20 恰好 1 True、1 False | 代码已提交，未实测 |
| nonce 唯一性 | 每轮 1 行 | 未实测 |
| 最终状态 | 每轮 pending | 未实测 |
| 子进程退出 | 40/40 exitcode=0 | 未实测 |
| Python 3.10/3.12 | 两版本 CI 均通过 | 未实测 |
| 完整 pytest | 0 failures | 未实测 |
| 实际设备写入 | 0 | 测试无设备调用 |

测试未达 100 轮压力验收，且未实现随机调度/崩溃注入；不以 20 轮冒充生产可靠性统计证明。

## ⑥ 相对上一版的差异、阻塞与下一步
11/14 仅单次双线程竞争和触发器回滚；11/15 新增 20 次双进程独立数据库竞争。仍需**取得 GitHub Actions 运行记录**，若失败修复后重新验证；然后补 100 次压力测试和子进程崩溃注入。下一工程模块应是 `TrustedReceiptVerifier`：远端事实获取在事务外、事务内仅做有界本地验签，绑定 `op_id/outcome/receipt_id/nonce/issued_at/expires_at`，并防止不同 nonce 包装同一 receipt_id。任何模型自述均不能充当远端事实。

## 参考
- Python multiprocessing：https://docs.python.org/3/library/multiprocessing.html
- Python sqlite3：https://docs.python.org/3/library/sqlite3.html
- SQLite 事务：https://www.sqlite.org/lang_transaction.html
- pytest 参数化：https://docs.pytest.org/en/stable/how-to/parametrize.html
- 现有 CI：`.github/workflows/framework-ci.yml`
- 上一报告：`engineering/2026-11-14-concurrent-reconciliation-tests.md`

**安全声明**：只包含合成身份和本地数据库；没有密钥、客户信息、设备凭证或内部地址。
