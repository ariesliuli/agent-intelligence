# 2026-11-23｜签名回执进程崩溃恢复边界（Signed Receipt Process-Crash Recovery Boundary）

**状态**：新增真实子进程 `os._exit()` 故障注入 pytest 已提交；尚未取得对应 GitHub Actions / Python 3.10、3.12 实际通过记录。仅离线合成 SQLite/HMAC；不等于生产部署。不新增 Hint，`state/processed.json` 最高 HINT-026。

## ① 今日建设目标及关联 Hint

按 `AGENTS.md`、`README.md`、`state/processed.json`、HINT-026、2026-11-22 工程报告及现有 `framework/tests/test_signed_outbox_resilience.py` 核对：11/22 已覆盖线程竞争、对象重建和 SQLite 锁竞争，但**尚未覆盖独立 OS 进程在事务中途硬退出**。本次专门补这一依赖缺口，不重复已有测试，不新增 Hint。

关联 HINT-002（持久状态）、HINT-005/013（恢复/核对）、HINT-023（工具执行事实门禁）、HINT-026（事件唤醒闭环）。历史 HINT-001～023 原文未完整导入，不能宣称全量语义去重。

## ② 框架位置、模块边界及上下游

```text
OpenClaw（未来主控） -> Codex CLI / Claude Code（未来执行器）
  -> 独立可信回执发行者（当前仅合成 simulator）
  -> Outbox.reconcile_signed(op_id, outcome, envelope, keys)
     -> BEGIN IMMEDIATE
     -> HMAC + operation / payload_digest / time binding
     -> INSERT UNIQUE(issuer, receipt_id)
     -> UPDATE operations.state
     -> COMMIT
  -> HINT-026 事件唤醒（尚未接入）
本次测试：单独 Python 子进程在 INSERT 后、COMMIT 前 os._exit(23)
      或 COMMIT 后 os._exit(24) -> 父进程重新打开数据库核对
```

边界：该测试验证 SQLite 单数据库事务的进程终止语义，不证明电源故障、磁盘损坏、网络文件系统或远端设备的 exactly-once。子进程仅持有合成密钥，无设备 IO。

输入 JSON（签名 MAC 由测试运行时计算）：
```json
{"op_id":"op1","outcome":"pending","envelope":{"alg":"HS256","body":{"issuer":"simulator","receipt_id":"r1","op_id":"op1","outcome":"pending","issued_at":90,"expires_at":110,"payload_digest":"sha256:<64-hex>"},"mac":"<64-hex>"}}
```

建议配置 YAML（**设计示例，当前没有配置加载器**）：
```yaml
mode: offline_simulator
device_write: false
recovery:
  ambiguous_auto_retry: false
  crash_test:
    subprocess_timeout_seconds: 15
    exit_before_commit: 23
    exit_after_commit: 24
sqlite:
  begin_mode: IMMEDIATE
  receipt_unique_scope: [issuer, receipt_id]
```

输出/审计 JSON 示例（**期望测试结果，不是已运行结果**）：
```json
{"case":"before_commit","child_exit_code":23,"before_recovery":{"state":"ambiguous","receipts":0},"after_recovery":{"state":"pending","receipts":1},"evidence_level":"expected_simulation"}
```

## ③ 具体实现细节（可交给 Codex / Claude Code）

新增 `framework/tests/test_signed_outbox_process_crash.py`，Python 标准库 `subprocess`、`sqlite3`、`os`、`hashlib`、`hmac` 与 pytest：

1. `test_process_exit_before_commit_rolls_back_receipt_and_state`：父进程准备 `ambiguous` 操作；子进程通过现有 `_tx()` 进入 `BEGIN IMMEDIATE`，执行签名验证与 `consume_verified_receipt()`，但在 `UPDATE` / `COMMIT` 前直接 `os._exit(23)`，绕过 Python `finally`。父进程重新读取应得到 `("ambiguous", 0)`，随后用同一签名回执重新核对，应得到 `("pending", 1)`。
2. `test_process_exit_after_commit_preserves_receipt_and_state`：子进程正常调用 `reconcile_signed()` 提交，然后 `os._exit(24)`；父进程重新打开数据库应得到 `("pending", 1)`，重复调用返回 `False`，不能重复推进。
3. 每个测试使用 `tmp_path` 独立 SQLite 数据库、独立 Python 解释器；捕获 stderr，15 秒超时。子进程返回码是精确断言，避免把导入错误误认为成功注入。
4. 现有 `reconcile_signed()` 生产实现**未修改**；不增加设备权限，不将模拟器自签当作设备事实。

运行：
```bash
cd framework
python -m pytest -q tests/test_signed_outbox_process_crash.py
python -m pytest -q tests/
```
CI 入口 `.github/workflows/framework-ci.yml`：Ubuntu 26.04、Python 3.10/3.12、pytest 8.3.5。应以对应 commit 的实际 Actions 日志验收，不能以文件存在冒充通过。

## ④ 实际案例、失败模式与可复用经验

**待验证经验：进程异常终止时，回执唯一消费与业务状态不能分离持久化。**

- 触发条件：Ubuntu 常驻 Agent 在设备写操作结果核对中遭 SIGKILL、OOM killer 或运行时进程退出
- 环境：单机 Python + SQLite；`BEGIN IMMEDIATE`；合成 HMAC 回执
- 已知事实：源码在单事务内执行回执插入与状态更新；11/22 的测试覆盖线程/对象重建/锁竞争；**本次新增子进程硬退出测试源码**
- 现象与根因假设：若事务未提交，SQLite 应撤销插入；若已提交，重启后应保留唯一回执与状态；测试专门证伪“回执已消费但操作仍 ambiguous”的不一致状态
- 替代根因：文件系统锁语义异常、SQLite journal/WAL 设置差异、数据库损坏、测试子进程导入失败、CI 版本差异
- 解决步骤：分别在 COMMIT 前后硬退出，重启连接，读取状态与回执数量，再测试合法恢复/重复核对
- 证据：测试文件已归档；运行结果与故障通过率 **null**，待 CI
- 适用边界：单 SQLite 数据库本地事务；不证明断电持久性、远端设备结果或跨主机 exactly-once
- 回滚：保留 `ambiguous` 人工核对，不允许未知外部副作用自动重试；测试可单独移除，生产 API 未改
- 7/30/90 天复查：7 天检查两版本 CI；30 天加入多进程竞争、WAL/journal 模式矩阵；90 天接入独立发行者及 HINT-026 事件恢复审计

## ⑤ 验证步骤与量化验收标准

| 指标 | 验收门槛 | 当前证据 |
|---|---|---|
| 子进程事务中退出 | 退出码 23，重启后 ambiguous + receipts=0 | 测试已提交，未运行 |
| 未提交回执恢复 | 同一有效签名可成功推进，receipts=1 | 测试已提交，未运行 |
| 提交后进程退出 | 退出码 24，重启后 pending + receipts=1 | 测试已提交，未运行 |
| 提交后重复回执 | 返回 False，0 次额外推进 | 测试已提交，未运行 |
| Python 3.10 / 3.12 | 两版本全量 pytest 0 非预期失败 | 待真实 CI |
| 真实设备 IO | 0 次 | 离线模拟器 |
| 人工节省时间、净 ROI | null | 无对照测量 |

后续需要另设强制 SIGKILL 的父进程注入和 journal_mode=WAL 测试；本次 `os._exit` 是进程硬退出模拟，**不声称覆盖物理断电**。

## ⑥ 相对上一版本的差异、剩余问题与下一步

11/22 是线程竞争、对象重建和锁争用；11/23 增加**独立进程事务中硬退出**与**已提交后硬退出**的明确边界，仍不修改生产接口。优先读取真实 CI 并分类失败：产品缺陷 / 旧测试契约 / 环境漂移。若通过，再增加多进程抢占和 SQLite WAL 模式；之后才考虑将 HINT-026 的事件唤醒接入可信核对门禁。

官方参考（工程语义，非本仓库通过证明）：SQLite transactions https://www.sqlite.org/lang_transaction.html ；Python `os._exit` https://docs.python.org/3/library/os.html#os._exit ；Python subprocess https://docs.python.org/3/library/subprocess.html 。
