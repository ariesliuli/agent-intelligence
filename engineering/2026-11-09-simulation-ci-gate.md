# 2026-11-09｜模拟框架持续集成门禁（Simulation CI Gate）

> 状态：已编写 GitHub Actions workflow；**CI 结果待 GitHub 实际执行确认**。本报告不宣称测试通过、不宣称生产安全。真实设备写入继续禁止。关联 HINT-002、005、013、023；不新增 Hint。

## ① 今日建设目标及关联 Hint
在 11/08 Facade 源码和测试已经提交、但没有可复现测试环境的基础上，建立可重复运行的 Python 版本矩阵。核对 README、AGENTS、processed、11/07 与 11/08 报告及 Store/Outbox/Atomic/Facade 源码：已有测试仍包含**展示已知漏洞的测试**，不能将绿色 CI 等同安全认证。

## ② 框架位置与上下游接口
`OpenClaw（未接） → Router（未接） → IntentFacade → AtomicIntentStore → SQLite → Outbox → Executor（未接）`。
新增的 CI 位于**代码合并验证层**，不参与运行时调度，不授予设备权限。
输入契约：GitHub push、pull_request（framework 目录变更）或 workflow_dispatch；输出契约：每个 Python 版本的成功/失败 Job 状态。CI 不会写回生产 SQLite。
计划中的配置契约（**尚无 YAML 加载器**）：
```yaml
runtime:
  external_writes_enabled: false
validation:
  python: ["3.10", "3.12"]
  pytest: "8.3.5"
  working_directory: framework
```
模拟提交 JSON（既有 Facade）：
```json
{"task_id":"t1","task_payload":{"goal":"simulation"},"op_id":"o1","action":"read_status","op_payload":{"target":"sim"},"idempotency_key":"t1:read:v1"}
```

## ③ 具体实现细节
新增 `.github/workflows/framework-ci.yml`，最小权限 `contents: read`；Ubuntu runner；Python 3.10/3.12 矩阵；固定 pytest 8.3.5；编译检查及 `cd framework && python -m pytest -q tests/`。不配置 secrets、不执行任何真实设备写操作。只对 framework 和 workflow 文件变动触发 push/PR；可手动触发。
执行器可在本地复现：
```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install 'pytest==8.3.5'
python -m compileall -q framework/agent_core framework/tests
(cd framework && python -m pytest -q tests/)
```
异常分类：依赖安装失败→环境问题；导入失败→工作目录/包结构问题；断言失败→代码回归；权限拒绝→预期 fail-closed。**不得自动修复失败测试为通过，也不得自动跳过。**

## ④ 具体经验（待验证经验）
触发：测试源码已经提交但执行环境缺少依赖或不在 framework 工作目录。环境：Python、pytest、SQLite。现象：先前 11/08 测试收集未成功，无法判定业务断言。根因假设：运行环境依赖或导入路径不一致。解决：在 CI 显式设置 Python、安装固定 pytest 版本、设置 working-directory；用两种 Python 版本发现兼容性差异。证据：既有报告记录失败，本次 workflow 源码可审计；**尚无新 CI 执行证据**。边界：CI 通过仅证明模拟测试在指定环境通过，不证明对抗性权限隔离或真实设备 exactly-once。

## ⑤ 验证步骤与量化验收
1. GitHub Actions 中触发 workflow_dispatch，确认 Python 3.10/3.12 两个 Job 均成功；目标 2/2。
2. 记录各版本 pytest 测试数量及失败数，目标失败 0、跳过 0（若发现预存跳过须单独记录）。
3. 在 PR 中故意制造一个断言失败，确认 CI 为红（只在测试分支进行，不合并）。
4. 检查 Actions token 权限为只读，设备凭证数量 0。
5. 将来新增强制安全回归：未经认证的 `Outbox.reconcile` 接受数必须为 0；旧编排路径绕过 Facade 数为 0。**当前均未满足**，不能作为本期已达标结果。
6. ≥50 次多进程 SIGKILL/锁竞争测试尚未执行。

## ⑥ 与上一版差异、剩余问题及下一步
11/08 仅有 Facade 和测试源码；11/09 新增可复现的 GitHub Actions 执行入口，未修改生产模块。下一步先取得 CI 真实运行结果；随后把展示漏洞的测试改为要求拒绝未认证证据的**安全断言**，实现签名核对入口并迁移旧调用，最后再研究进程级权限边界。
回滚：删除 workflow 文件即可撤销 CI；不改 SQLite schema，不影响模拟模块；真实设备写入保持关闭。

## 参考资料（官方）
- GitHub Actions workflow syntax: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- GitHub Actions token permissions: https://docs.github.com/en/actions/security-for-github-actions/security-guides/automatic-token-authentication
- pytest 文档: https://docs.pytest.org/en/stable/
- Python sqlite3: https://docs.python.org/3/library/sqlite3.html
