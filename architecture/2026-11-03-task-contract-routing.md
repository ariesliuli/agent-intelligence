# 2026-11-03｜任务契约与动态路由（Task Contract & Adaptive Model Routing）

> **状态：** 本地可执行原型，10 项 pytest 测试通过；GitHub 已归档源码与测试。**未接入真实 OpenClaw / Codex CLI / Claude Code，也未验证真实额度接口。** 本文为新工程实现，不是历史 Hint 原文。

## ① 建设目标与关联 Hint
关联 HINT-002（任务契约）、005（确定性工作流）、008（能力分配）、021（动态模型路由）、023（工具调用验证）。先把抽象设计变成确定性的路由决策，再接真实执行器。

## ② 框架位置与上下游
`OpenClaw → Task Contract → Router → Executor Adapter（待开发）→ Verifier（待开发）→ Audit/Experience Memory（待开发）`

任务输入：
```json
{"task_id":"T-001","objective":"实现只读设备状态解析器","risk":"low","required_capabilities":["python"],"allowed_tools":["read"],"verify_independently":false}
```

路由输出：
```json
{"status":"ready","executor":"claude","verifier":null,"reason":"policy_match"}
```

Worker 字段：`name`、`capabilities`、`available`、`remaining_units`、`estimated_cost`、`quality_score`、`tool_permissions`。额度为**模拟的抽象单位**，不能直接映射 CLI 官方剩余量。

## ③ 实现细节
代码：[`framework/agent_core/router.py`](../framework/agent_core/router.py)。测试：[`framework/tests/test_router.py`](../framework/tests/test_router.py)。

执行顺序：①校验契约基本字段与风险等级；②过滤不可用或额度耗尽的 Worker；③过滤能力或工具权限不足者；④按质量降序、成本升序、名称升序稳定排序；⑤高风险或指定独立审核时，必须选择不同的第二个 Worker；⑥返回 `ready`、`blocked` 或 `approval_required`，不直接执行命令。

运行：
```bash
cd framework
python -m pytest -q
```
依赖 Python 3.10+ 与 pytest；当前没有外部 API、密钥或网络依赖。

## ④ 可复用工程经验（模拟验证）
- **触发条件：** Codex 或 Claude 单独额度耗尽，或某执行器不可用。
- **现象：** 静态模型选择会继续派单给不可用执行器；不受控降级可能绕过权限。
- **根因假设：** 额度状态、能力约束与权限检查没有统一的决策接口。
- **解决方法：** 先过滤可用性/额度/能力/权限，再排序；高风险任务缺少独立审核时进入审批状态。
- **验证：** 本地 pytest 10 项通过；这是路由策略测试，不代表真实 CLI 自动切换已成功。
- **边界：** 尚无实时额度获取、CLI 调用、持久化恢复或真实模型质量评分。不得把模型提供的任务权限字段当成真实授权。

## ⑤ 验收标准
1. Codex 无额度、Claude 可用 → Claude。
2. Claude 无额度、Codex 可用 → Codex。
3. 双方可用 → 确定性排序；双方不可用 → blocked。
4. 工具权限不足 → blocked，不允许不安全降级。
5. 高风险只有一个执行器 → approval_required。
6. 高风险有两个执行器 → 执行者与审核者不同。
7. 本地 10 项测试全部通过；不访问外部网络。

## ⑥ 本期差异、限制、下一步
相较 HINT-021 历史摘要，本期首次提供可执行 Python 路由代码和回归测试。下一期优先：SQLite 任务状态机、租约超时、幂等重试、审计事件；之后再验证真实 CLI 额度接口。回滚：禁用路由入口，恢复手动选择执行器；本期不修改真实运行环境。
