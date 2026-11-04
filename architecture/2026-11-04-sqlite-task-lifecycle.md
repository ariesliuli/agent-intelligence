# 2026-11-04｜可恢复任务状态机（Recoverable Task Lifecycle）

> **工程状态：** 已提交 Python SQLite 原型及 12 个 pytest 测试案例；本地等价实现通过 12/12 测试。GitHub 版本在提交时经过接口精简，**尚未独立运行 GitHub 原样代码的 CI**，因此不能宣称远端版本已验证。无真实 CLI/设备写入。

## ① 今日建设目标及关联 Hint
从昨天 HINT-002/005/008/021 的“只决定谁执行”，推进到“任务在 Ubuntu 服务重启、模型额度耗尽、执行器崩溃后如何恢复”。关联 HINT-002（Task Contract）、005（Workflow Engine）、009（Worktree Handoff）、013（Out-of-Band Audit）、015（Compaction Authority Reset）、023（Tool-Call Oracle）。不创建新 Hint。

## ② 架构与接口
`OpenClaw → Router（昨日）→ SQLite Store（今日）→ Codex/Claude Adapter（待开发）→ 独立验证（待开发）`。

`submit(id,payload)` 幂等提交；`claim(id,owner,ttl,max_attempts)` 原子领取，返回递增的 attempt（fencing token，旧执行器写入隔离令牌）；`write(id,owner,attempt,'checkpoint',value)` 保存进度；`write(...,'result',value)` 完成任务；`get(id)` 查询状态。任务状态：`pending → running → succeeded`，租约过期后可重新领取；超过次数 → `failed`。

输入示例：
```json
{"task_id":"T-001","objective":"解析设备只读状态","risk":"low","allowed_tools":["read"],"required_capabilities":["python"]}
```
检查点：
```json
{"step":"parsed","artifact_sha256":"example-placeholder","side_effects":[]}
```
**重要：** 不允许模型输出自行扩大 `allowed_tools`；授权必须来自独立可信的任务创建方。

## ③ 实现与运行
源码：`framework/agent_core/store.py`；测试：`framework/tests/test_store.py`。
```bash
cd framework
python -m pytest -q tests/test_store.py
```
仅 Python 标准库 + pytest（测试时）。SQLite `BEGIN IMMEDIATE` 序列化写入；主键避免重复创建；重复任务 ID 且 payload 不一致时抛出冲突；写入时校验 owner、attempt、租约未过期，防止过期执行器污染数据库。

## ④ 可复用具体经验（模拟验证）
**场景：** Codex 领取任务后长时间无响应，租约过期，Claude 重新领取；Codex 迟到返回成功。

**失败模式：** 如果只检查任务 ID，旧 Codex 会覆盖 Claude 的新结果。

**处理：** 每次领取增加 attempt；所有 checkpoint/result 写入都携带 owner+attempt 并检查 lease。旧 attempt 的写入拒绝。

**验证：** 本地模拟时钟推进 11 秒，旧 attempt=1 写入失败，新 attempt=2 写入成功。**这只是 SQLite 数据库内的 fencing，不保证外部 CGI、文件、邮件等副作用恰好执行一次。**

## ⑤ 验收标准与回滚
测试覆盖：幂等提交、同 ID 不同内容冲突、领取、禁止双重领取、租约过期重领、旧执行器拒绝、检查点、过期写入拒绝、重试次数上限、缺失任务、无效租约、终态不可重领，共 12 个案例。目标 GitHub CI 12/12，当前需补跑远端原样代码。

回滚：停止使用 Store，恢复手动路由；备份数据库文件；禁止删除未完成任务；真实执行器上线前要求任务 ID 和外部副作用的幂等键。

## ⑥ 差异、限制、下一步
相较 11/03 的纯路由原型，新增持久化任务状态、租约恢复、attempt 隔离、检查点和审计事件表。仍缺：SQLite WAL 与并发压力测试、租约续期、明确失败/取消、崩溃注入测试、外部操作幂等键、可信权限源、真实 CLI adapter、独立审计存储、CI。下一期优先做 **外部副作用的 Outbox + 幂等执行**，避免“数据库没有重复写入，但设备被重启两次”的问题。
