# 2026-11-17｜回执身份门禁独立原型（Receipt Identity Gate Prototype）

> 状态：源码与离线测试已提交；pytest/CI 未运行；尚未集成 Outbox；无真实验签或生产安全承诺。不新增 Hint。

## ① 今日建设目标及关联 Hint
已读取 AGENTS.md、README.md、state/processed.json、framework/agent_core/outbox.py、11/16 报告及测试、HINT-023。登记最高 HINT-025。沿 HINT-002/005/013/023 与 11/16 strict-xfail 缺口，优先实现独立的 **issuer + receipt_id** 持久身份门禁，而非重复增加 nonce 测试。历史 Hint 原文不全，不能宣称全量语义去重。

## ② 架构位置与上下游接口
```text
OpenClaw / Codex CLI / Claude Code [尚未接入]
 → Outbox ambiguous
 → 远端只读取证 + 独立签名验证器 [未实现]
 → VerifiedReceipt [本次定义]
 → BEGIN IMMEDIATE [由调用者负责]
 → consume_verified_receipt() [本次实现]
 → nonce INSERT + operation UPDATE [下一步集成]
 → COMMIT / ROLLBACK
```
**信任边界**：`VerifiedReceipt` 是内部数据类型而非密码学证明；任何 Python 调用者仍能构造它。生产集成前必须保证对象仅由可信验签模块产生，且不能允许外部调用者绕过门禁。不要把模型输出转换成此对象就宣称认证。

输入（合成、非签名）：```json
{"issuer":"test-issuer","receipt_id":"r1","op_id":"op-a","outcome":"pending","issued_at":90,"expires_at":110,"payload_digest":"sha256:test"}
```
设计配置（**尚未支持**）：
```yaml
receipt_gate:
  require_signature: true
  trusted_issuers: [] # 运行环境注入，禁止提交真实密钥
  clock_skew_seconds: 5
  fail_closed: true
```

## ③ 具体实现细节
新增 `framework/agent_core/receipt_gate.py`：冻结的 `VerifiedReceipt` 数据结构；字段类型、非空、长度、操作身份、outcome、时间窗口校验；`reconciliation_receipts` 表以 `(issuer, receipt_id)` 为复合主键；冲突转为 `PermissionError("replayed_receipt")`；函数不自行 commit，要求调用者将插入和状态更新置于同一事务。

新增 `framework/tests/test_receipt_gate.py`：跨操作重放、过期、未来时间、绑定错误、空 ID、NaN、发行者命名空间、注入异常后的回滚。使用合成数据，无设备网络调用。

最小执行任务（Codex/Claude Code）：
1. 在隔离 Ubuntu Python 3.10/3.12 环境运行 `cd framework && python -m pytest -q tests/test_receipt_gate.py tests/test_outbox_receipt_replay_gap.py -rx`。
2. 修复任何实际测试失败；记录环境、pytest 版本、完整输出，不得以预期 XFAIL 作为安全修复证据。
3. 新建独立验签适配器：可信 issuer 配置、签名验证、payload digest 与操作指纹绑定、到期与时钟偏差、拒绝未知算法/密钥。
4. 重构 Outbox：验签不得在 SQLite 写锁内进行网络请求；但验签与消费之间须用原子门禁防竞态；receipt、nonce、operation 三者在同一 `BEGIN IMMEDIATE` 内变更。不能允许旧 permissive verifier 绕过生产门禁。
5. 删除原 strict xfail 前先让原攻击测试真正通过；补并发双进程与触发器故障注入。
6. 增加 schema migration 与旧库备份，禁止默认将旧无回执证据升级为已认证。

## ④ 具体经验（待验证经验）
触发：Nonce 唯一约束已存在，但不同 Nonce 可以包装同一回执。环境：本仓库 Python SQLite Outbox。现象：11/16 源码审计发现缺少 Receipt 身份表。根因假设：把请求级随机标识误当作远端事实身份。替代根因：可信外部验证器可能另有防重放能力，但本仓库无生产实现证据。处理：本次增加独立身份表和可调用的本地验证函数。证据：提交的代码与测试，运行日志 `null`，生产部署 `null`。边界：只能证明本地 SQLite 设计意图，不能证明真实签名、跨数据库一致性或远端 exactly-once。回滚：移除新模块和测试；不修改旧 Outbox。7/30/90 天复查集成状态、重放拒绝率、故障注入及误拒绝。

## ⑤ 验证与量化验收
| 项目 | 目标 | 状态 |
|---|---|---|
| 合成回执重复消费 | 第二次拒绝率 100% | 测试已提交，未运行 |
| issuer 分域 | 相同 receipt_id 不同 issuer 可独立记录 | 测试已提交，未运行 |
| 过期/未来/绑定错误/NaN | 负例 100% 拒绝 | 测试已提交，未运行 |
| 故障注入 | 插入后异常全回滚 | 测试已提交，未运行 |
| 真实验签 | 未认证 100% 拒绝 | 未实现 |
| Outbox 三表事务 | 0 部分提交 | 未集成 |
| Python 3.10/3.12 CI | 0 非预期失败 | 未验证 |
| 外部设备写操作 | 0 | 仅离线模拟 |

## ⑥ 差异、剩余问题与下一步
相较 11/16 只提交 strict-xfail 攻击样例，本次新增可复用的 Receipt 身份对象、SQLite 复合唯一约束与离线测试。**但这不是已修复的 Outbox 安全缺口**：生产路径仍旧使用原 verifier，旧 XFAIL 保留。下一步应先获取 pytest/CI 实测，再构建独立验签适配器与 Outbox 原子集成。

参考：
- SQLite 事务：https://www.sqlite.org/lang_transaction.html
- SQLite 主键与唯一性：https://www.sqlite.org/lang_createtable.html
- pytest xfail：https://docs.pytest.org/en/stable/how-to/skipping.html
- 仓库原有源码：framework/agent_core/outbox.py
