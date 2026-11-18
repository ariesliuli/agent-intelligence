# 2026-11-18｜签名回执认证边界（Signed Receipt Authentication Boundary）

> 状态：新增离线 HMAC-SHA256 验签模块及合成测试；未执行 pytest/CI；未接入 Outbox；未部署。**不能声称生产可信回执已实现。** 不新增 Hint。

## ① 今日建设目标及关联 Hint
先读取 AGENTS.md、README.md、state/processed.json、receipt_gate.py、Outbox、11/16–17 报告和 HINT-023；登记最高 HINT-025。历史 HINT-001～023 原文不完整，无法证明全量语义去重。关联 HINT-002/005/013/023。11/17 的 VerifiedReceipt 可由任意调用者构造；今天新增 **认证入口**，但不在没有外部可信发行者时修改 Outbox 状态机。

## ② 框架位置与数据流
```text
OpenClaw / Codex / Claude [未接入]
  → 远端只读取证 [未实现]
  → envelope (untrusted)
  → verify_signed_receipt() [本次新增；离线 HMAC]
  → VerifiedReceipt + validate_receipt() [已有]
  → consume_verified_receipt() [已有 SQLite 唯一约束]
  → Outbox nonce + operation UPDATE [未集成]
```
边界：HMAC 只能证明知道共享密钥的一方签过消息；如果调用者也持有该密钥，则不能构成独立证明。生产优先使用发行者公钥验证、可信设备 API 只读核对或独立审核服务。签名验证通过也不等于远端副作用真实发生。

输入（合成）：
```json
{"alg":"HS256","body":{"issuer":"simulator","receipt_id":"r-1","op_id":"op-1","outcome":"pending","issued_at":90,"expires_at":110,"payload_digest":"sha256:synthetic"},"mac":"<64位小写十六进制HMAC，运行时生成>"}
```
设计配置（尚无配置加载器）：
```yaml
receipt_auth:
  mode: offline_hmac_simulation
  key_source: runtime_injection
  allow_unsigned: false
  production_enabled: false
```

## ③ 可执行实现与接口契约
新增 `framework/agent_core/signed_receipt.py`：严格 envelope 字段集合、固定 HS256 算法、issuer 白名单、至少32字节密钥、规范 JSON、HMAC constant-time 比较、payload_digest/op_id/outcome/时间窗绑定；返回 `VerifiedReceipt`，失败抛 `PermissionError`。不联网、不提交、不持有 SQLite 锁。新增 `framework/tests/test_signed_receipt.py`：成功样例、签名后字段篡改、已签但绑定错误、过期/未来、未知 issuer、算法降级、不同 payload 摘要。

**关键限制**：返回的 Python dataclass 仍可被调用者直接伪造；模块边界不是进程隔离。生产调用必须保证验签和状态迁移处于受控服务边界，不允许其他插件直接调用 `consume_verified_receipt`。目前尚无可信 issuer/真实设备签名协议。

Codex 最小任务：
1. 在 Python 3.10/3.12 下运行 `cd framework && python -m pytest -q tests/test_signed_receipt.py tests/test_receipt_gate.py -rx`，记录版本、日志、失败原因。
2. 增加严格字段类型与畸形输入 fuzz/参数化测试；确认不会泄漏 TypeError/KeyError，所有未认证输入 fail closed。
3. 设计 `TrustedReceiptVerifier` 抽象（公钥验签或远端独立核对）；定义 key rotation、issuer 撤销、摘要算法版本与时间可信来源。
4. 仅在认证器可用后，将 receipt、nonce、operation 状态纳入一个 `BEGIN IMMEDIATE` 事务；网络 IO 不得位于 SQLite 写锁内。
5. 将旧 strict XFAIL 转为正常测试之前必须保证拒绝重放，并测试崩溃注入、旧库迁移与多进程竞争。

## ④ 具体经验（待验证经验）
触发：已实现 `VerifiedReceipt` 类型与唯一约束，但类型由普通 Python 调用者自由构造。环境：Python SQLite Outbox 原型。现象：类型约束与密码学认证之间存在可绕过的信任边界。根因假设：把结构化数据类型当成可信来源。替代解释：生产上可能由外部受控服务限制调用，但仓库没有部署证据。解决：新增隔离的离线验签入口；**尚未形成不可绕过的生产边界**。证据：源码和合成测试已提交；pytest结果=null，生产运行=null。适用边界：共享密钥受控的离线模拟，不能证明远端 exactly-once。回滚：删除新增模块/测试；旧 Outbox 未改。7/30/90天复查验签集成、真实发行者认证、误拒绝、重放和密钥轮换。

## ⑤ 验证步骤与量化门槛
| 指标 | 验收门槛 | 状态 |
|---|---|---|
| 合成有效签名 | 100% 通过 | 测试已提交，未运行 |
| 篡改/算法降级/未知 issuer | 100% 拒绝 | 测试已提交，未运行 |
| 过期/未来/跨操作/摘要不符 | 100% 拒绝 | 测试已提交，未运行 |
| Python 3.10/3.12 pytest | 0 非预期失败 | 未验证 |
| Outbox 三表事务 | 0 部分提交 | 未实现 |
| 真实发行者认证与设备部署 | 独立证据 | 未实现 |

## ⑥ 与上一版本差异、阻塞和下一步
11/17 只有身份门禁与可构造的 VerifiedReceipt；11/18 新增**合成签名校验入口**，但未把它误称生产可信验证器。阻塞：缺少真实发行者签名契约、密钥生命周期、运行日志及受控服务边界。下一步优先执行 CI 并补强异常输入，然后再接 Outbox；不修改 state/processed.json，不新增 Hint。

参考：
- Python HMAC 文档：https://docs.python.org/3/library/hmac.html
- SQLite 事务：https://www.sqlite.org/lang_transaction.html
- OWASP Cryptographic Storage Cheat Sheet：https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html
