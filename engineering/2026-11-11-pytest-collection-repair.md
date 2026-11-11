# 2026-11-11｜修复 pytest 收集阻塞并强化核对回归（Pytest Collection Repair & Reconciliation Regression）

> **状态**：源码已提交，CI/完整 pytest 尚未确认；不宣称测试通过或生产部署。无新 Hint。关联 HINT-002、005、013、023 与宿主第一性原理规范。

## ① 今日建设目标及关联 Hint

检查仓库 `AGENTS.md`、`README.md`、`state/processed.json`、`hints/`、`daily/`、`architecture/`、`engineering/` 与 `framework/`。当前最高 HINT-025；001～023 大多为重建摘要，不能视为完整原文。11/10 已引入 fail-closed `Outbox.reconcile`，今天不重复开发认证方案，而是先排除阻断全部测试收集的**确定性语法错误**。

`framework/tests/test_outbox.py` 原有：

```python
s,_=env; enqueue(s); with pytest.raises(PermissionError):
```

Python 的复合语句 `with` 不能放在该分号之后。该文件在解析阶段触发 `SyntaxError`，pytest 可能无法收集该测试模块。此为**源码静态可确认**的缺陷；不是已执行的测试结果。

## ② 框架位置与上下游接口

```text
OpenClaw（未接入）
  → Router（模拟路由）
  → IntentFacade
  → AtomicIntentStore / SQLite Outbox
  → reconcile(op_id, outcome, evidence)
  → verifier（注入接口；生产级认证尚缺）
  → pytest + GitHub Actions（运行状态待确认）
```

改动仅限 `framework/tests/test_outbox.py`。不修改业务状态机、外部执行器或设备权限。

## ③ 具体实现与接口契约

将语法错误拆成独立语句：

```python
s,_=env
enqueue(s)
with pytest.raises(PermissionError, match='reconciliation_verifier_required'):
    s.reconcile('op1','succeeded',{'op_id':'op1','outcome':'succeeded'})
```

增加三个模拟回归用例：

1. `test_verifier_truthy_non_bool_rejected`：验证器返回整数 `1` 不能代替布尔 `True`；`ambiguous` 不变。
2. `test_reconcile_only_ambiguous_state`：即使验证器返回 `True`，`pending` 状态不能被 `reconcile` 改写。
3. `test_expired_lease_not_finished_after_reconciliation`：旧租约超时后，旧 owner/attempt 不得提交结果；重新 claim 的 attempt 必须递增。

输入：`op_id`、`outcome`、`evidence` 对象；状态 `pending → inflight → ambiguous → pending`。验证失败抛 `PermissionError`，状态不变；非法格式抛 `ValueError`。

**安全局限**：目前可注入的 `lambda: True` 只是模拟测试替身，不代表签名认证、远端副作用确认、nonce 防重放或可信授权。验证器调用发生在数据库事务外；并发、重放与 TOCTOU 仍未解决。

最小配置：Python 3.10/3.12、`pytest==8.3.5`、SQLite 本地临时文件，无网络和真实设备。无需 YAML；现有 CI 配置在 `.github/workflows/framework-ci.yml`。

## ④ 具体经验（静态可验证，运行结果待验证）

**触发**：在测试代码中将 `with` 放在分号后面。**环境**：Python 测试模块。**现象**：解析失败，测试无法正常收集。**根因**：Python 语法不允许此处的复合语句。**解决**：拆行并增加回归测试。**证据**：GitHub 上的修复前后源码可比对；完整 pytest 未运行。**适用边界**：Python 源码解析和 pytest 收集；不说明其他模块运行逻辑正确。

可复用机制：**先消除测试收集阻塞，再评价安全回归是否通过**。CI 配置存在不等于测试能运行；静态解析通过也不等于功能正确。

## ⑤ 验证步骤与可量化验收标准

```bash
cd framework
python -m compileall -q agent_core tests
python -m pytest -q tests/test_outbox.py
python -m pytest -q tests/
```

验收目标（**未实测**）：Python 3.10/3.12 两矩阵 `compileall` 与全部 pytest 收集/执行失败数为 0；新增三个测试通过；未验证核对接受数为 0；旧租约提交成功数为 0；实际设备写入数为 0。

本次尝试 `git clone` 执行完整测试，容器 DNS 无法解析 `github.com`，故未获得真实 pytest 输出。必须由 GitHub Actions 或可访问仓库的 Ubuntu 环境完成运行确认。不可将源码审阅当作 CI 绿灯。

## ⑥ 与上一版本差异、剩余问题与下一步

11/10：引入默认拒绝核对，但测试文件含语法阻塞。11/11：修复该语法并增加三个边界回归。**代码变更已提交，运行结果仍待确认**。

下一步按依赖顺序：① 读取 Actions 运行日志并修复所有真实失败；② 将可信核对证据验证与状态转换合并为事务化一次性消费，明确并发锁定策略；③ 增加重复 nonce、跨操作绑定、过期证明、同时核对竞争测试；④ 最后才接入真实执行器。回滚：恢复测试文件前一版不安全（会重新引入语法错误），因此优先修复后续测试，不回滚 fail-closed 生产逻辑。

## 来源

- Python 官方语法（compound statements）：https://docs.python.org/3/reference/compound_stmts.html
- pytest 官方文档：https://docs.pytest.org/en/stable/
- Python sqlite3：https://docs.python.org/3/library/sqlite3.html
- 相关仓库代码：`framework/agent_core/outbox.py`、`framework/tests/test_outbox.py`、`.github/workflows/framework-ci.yml`。

**数据治理**：只含合成标识与示例，不含客户信息、密钥、内部地址或设备凭证。
