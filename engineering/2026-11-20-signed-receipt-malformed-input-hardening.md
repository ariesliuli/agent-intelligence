# 2026-11-20｜签名回执畸形输入封闭拒绝（Signed Receipt Fail-Closed Hardening）

> **状态：代码与合成 pytest 用例已提交；GitHub 回读确认待本次核验；新 CI 结果未核验；无生产部署。** 本次不新增 Hint，优先补齐已存在的安全契约。全部数据为合成示例，禁止真实密钥与客户资料入库。

## ① 今日建设目标及关联 Hint
读取 AGENTS.md、README.md、state/processed.json、HINT-026、2026-11-18 工程报告及 Outbox/Receipt 原码；登记最高编号 HINT-026。历史 HINT-001～023 原文尚未完全归档，不能宣称全量语义去重。关联 HINT-002/005/013/023、11/17 Receipt Identity Gate、11/18 Signed Receipt Boundary；HINT-026 的事件闭环依赖可靠的状态证据，因此先修复认证边界中可复现的异常路径，而不是重复搭建事件编排。

**明确缺口**：原先 `verify_signed_receipt()` 对已正确签名但 `payload_digest` 不是字符串的 body 直接调用 `hmac.compare_digest(body["payload_digest"], payload_digest)`，会抛出 `TypeError` 而非统一的 `PermissionError`。若 `keys=None`，原实现 `keys.get` 同样抛出 `AttributeError`。这是代码静态可证的输入类型缺口；并非已观测到的生产事故。

## ② 框架位置、模块边界及数据流
```text
OpenClaw (调度，未接入) → Codex/Claude/模拟器 (不可信输出)
  → envelope JSON (不可信) → signed_receipt.verify_signed_receipt()
  → VerifiedReceipt (仅模拟共享密钥信任域)
  → receipt_gate.consume_verified_receipt() (未接入 Outbox)
  → Outbox.reconcile() nonce + operation (现有独立事务，未统一 receipt)
```
上游只允许受控服务提供 issuer-key 映射；不得让模型、Node-RED 任意 Flow 或远端工具持有验证密钥并同时充当独立证明者。下游不接受未认证的普通字典代替签名验证。外部 API/设备事实核验尚未实现，HMAC 不能证明远端副作用已完成。

输入 JSON（`mac` 为运行时合成）：
```json
{"alg":"HS256","body":{"issuer":"simulator","receipt_id":"r-1","op_id":"op-1","outcome":"pending","issued_at":90,"expires_at":110,"payload_digest":"sha256:synthetic"},"mac":"<运行时合成的64位十六进制签名>"}
```
配置 YAML（**设计契约，尚无加载器**）：
```yaml
receipt_auth:
  mode: offline_hmac_simulation
  allow_unsigned: false
  key_source: runtime_injection
  production_enabled: false
  reject_malformed_digest: true
  reject_invalid_keyring: true
```
输出：验证成功返回 `VerifiedReceipt`；验证失败统一抛 `PermissionError`（包含 `invalid_payload_digest`、`invalid_keyring`、`invalid_signature` 等）；不会修改 SQLite。

## ③ 具体实现（可交给 Codex/Claude Code）
本次修改：
1. `framework/agent_core/signed_receipt.py`：先检查 `keys` 为 Mapping，否则 `PermissionError("invalid_keyring")`；先检查已签名 body 的 `payload_digest` 与调用者期望摘要均为字符串，否则 `PermissionError("invalid_payload_digest")`，再做 `compare_digest`。
2. `framework/tests/test_signed_receipt.py`：新增 `None/17/False/[]/dict` 五种签名有效但摘要类型错误的负例；`keys=None` 负例；`op_id` 为 `None/0/[]/dict` 四种负例。共新增 10 个参数化测试实例。
3. 维持 `HS256`、issuer 白名单、操作/结果/摘要绑定、时间窗与拒绝未签名篡改的既有语义；不放宽安全策略。

命令：
```bash
cd framework
python -m pytest -q tests/test_signed_receipt.py tests/test_receipt_gate.py
python -m pytest -q tests/
```
在 GitHub Actions Python 3.10/3.12 两版本上执行；记录 run ID、commit SHA、pytest 统计。只有绿色 CI 日志可标记为 tested。不要把提交成功当成测试通过。

## ④ 具体经验：已定位代码缺口，运行验证待完成
- **触发**：受信任签名者（或被攻陷的签名服务）签署了 JSON 类型不合法的 `payload_digest`，或调用者误传 `keys=None`。
- **环境**：Python 3.10/3.12 目标；`hmac.compare_digest` 要求相容的 bytes/str 参数；合成 HMAC 共享密钥。
- **现象**：此前源码中非字符串摘要触发 `TypeError`；空 keyring 触发 `AttributeError`，绕过统一认证失败异常接口。
- **根因**：签名验证与业务字段类型校验顺序不当；缺少配置对象类型门禁。
- **替代根因**：调用者本应始终传有效 keyring，但这是未验证的上游约束，不能替代防御式校验。
- **处理**：先校验输入类型，异常转为 `PermissionError`；增加合成回归负例。
- **证据**：源码路径与 pytest 用例已提交；实际 CI 结果 = null；生产事故 = null。
- **边界**：只修复这两类异常路径，不代表所有畸形 JSON、Unicode、嵌套类型和超大输入已覆盖。
- **回滚**：恢复本次两个文件至前一版本；不得为了绿色测试恢复接受未认证回执。若有新异常，关闭自动核对、保留 ambiguous 状态并走人工核对。
- **复查**：7天检查 CI 与失败样例，30天补 fuzz 和资源上限，90天评估真实发行者、公钥验证及安全服务边界；未知值保持 null。

## ⑤ 验证与可量化验收
| 指标 | 门槛 | 当前证据 |
|---|---|---|
| 新增 10 个畸形输入用例 | 100% 统一 `PermissionError` | 用例已提交，未核验 CI |
| 原有有效签名/签名篡改 | 既有回归全部通过 | 未核验 CI |
| Python 3.10 + 3.12 | 两版本 0 非预期失败 | 未核验 CI |
| SQLite Outbox 状态 | 验签失败不修改任何操作状态 | 模块本身无数据库 IO；集成尚未验证 |
| 模型/设备真实权限 | 0 自动真实写入 | 本次未接入外部系统 |
| 故障注入与并发原子性 | 0 部分提交/重复消费 | 未实现统一事务，不能宣称通过 |

## ⑥ 相对上一版本、剩余问题与下一步
11/18 的原型建立了 HMAC 认证入口；本次对其 **输入类型错误的 fail-closed 语义**做了可执行的局部补强，未增加新 Hint 编号。此前 CI 的两个测试契约失败已在独立修复中处理，不能混淆为本次运行通过。

下一步按依赖顺序：
1. 取得两版本 GitHub Actions 的实际结果，固定测试基线。
2. 补 `mac`、`alg`、issuer、时间字段及 JSON 资源上限的畸形输入测试，保证所有未认证输入可控失败。
3. 将 `VerifiedReceipt` 的 issuer/receipt_id 唯一约束、nonce 消费与 operation 状态推进合并到 **同一个 SQLite `BEGIN IMMEDIATE`**；禁止在写锁内做网络 IO。
4. 使用模拟器验证崩溃、重复提交、跨操作重放与并发核对；通过后再讨论可信独立核对服务。
5. HINT-026 事件唤醒闭环在这些安全门禁可靠之前不应自动发布/部署。

参考：Python HMAC 官方文档 https://docs.python.org/3/library/hmac.html ；Python `collections.abc.Mapping` https://docs.python.org/3/library/collections.abc.html ；SQLite 事务 https://www.sqlite.org/lang_transaction.html 。
