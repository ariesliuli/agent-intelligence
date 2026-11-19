# HINT-026｜事件唤醒式故障闭环与防泄漏历史回测（Event-Woken Incident Loop & Leakage-Safe Backtesting）

**发现/归档日期：** 2026-11-20  
**原始发布日期：** 2026-11-19  
**证据等级：** OpenAI 官方生产工程案例（自述运行与人工抽检，非第三方审计）；本仓库方案 **implementation_proposed**，未运行、未部署。

## 1. 新进展与原始证据
来源：OpenAI Engineering，*How OpenAI’s Performance Factory keeps ChatGPT fast*，2026-11-19：https://openai.com/index/how-openai-performance-factory-keeps-chatgpt-fast/

OpenAI 报告 Performance Factory 的 Regression Workflow 在略多于三个月中跟踪 **1,700+ 次调查**，对 **600+ 个案例找到根因**，约 **每天 17 次自动调查**；在人工复核的 100 条根因建议中，**70% 判定准确**，其余 30% 需改进或未充分建立因果关系。这些数字不能推导为 600 个已自动修复、70% 全量准确率、净节省工时或 ROI。生产流程包含：告警→独立调查→反事实审查→修复 PR→工程师批准部署→部署事件唤醒→复测恢复；还对工具权限故障进行日常自检。Codex 云端调用 API 属于其**内部 API**，不是已公布的可复用公共 SDK。

## 2. 相对已有架构的新意与边界
对照 HINT-001 Skill 门禁、HINT-002 持久状态、HINT-003 经验沉淀、HINT-005/013 恢复与核对、HINT-008/021 模型调度、HINT-023 工具调用状态验证、HINT-024 规则筛选、HINT-025 依赖晋升，以及现有 Receipt/Outbox 工程原型，本 Hint **不重复提出状态机、subagent、独立审核或幂等回执**。

新增的可落地组合是：**(A)** 外部事件订阅唤醒等待中的任务，不让模型空转轮询；**(B)** 生产部署后的结果复测成为关闭事件的硬门禁；**(C)** 将历史事故回放限制在当时可见的证据快照，防止用事故结论、后续监控或 Agent 记忆作弊；**(D)** 分开评价根因正确性与交接摘要可用性。以上为官方案例中的已实施做法；迁移到本仓库尚待验证。

## 3. 具体收益与适用场景
预期减少等待期间的无效模型调用、过早宣告修复、错误归因与历史回测信息泄漏；没有本仓库实测数据，不能声称提速百分比。

- Python：CI 失败→诊断→修复 PR→人工 merge→CI/运行指标恢复验证；使用独立 SQLite 事务记录事件去重与状态。
- Node-RED：HTTP/MQTT 节点异常告警→只读日志分析→经审批的 flow 修改→部署事件→功能/延迟复测；默认禁止自动 deploy。
- 设备协议：LoRaWAN 上报异常、MQTT 断链、CGI 读超时，以模拟器和脱敏日志进行反事实测试；真实设备写入仍经过确定性审批门禁。
- 技术支持：工单告警、固件版本差异与故障复现；将故障发生时可获得的固件文档、日志与配置版本冻结为可回放证据。
- 多执行器：OpenClaw 只负责调度；Codex/Claude Code 可替换，审查必须独立会话，不能复用调查者隐藏状态。

## 4. 最小实现任务（可交给 Codex）
在 `framework/incident_loop/` 新建 `schema.py`、`store.py`、`dispatcher.py`、`evidence.py`、`backtest.py`、`simulator.py`；`framework/tests/test_incident_loop.py`；`examples/incident-loop-policy.yaml`。仅离线运行，复用现有 SQLite Outbox/Receipt 门禁接口而非复制权限逻辑。

事件输入 JSON：
```json
{"event_id":"evt-001","type":"ci_failed","task_id":"inc-001","source":"simulator","observed_at":"2026-11-20T00:00:00Z","evidence_snapshot_id":"snap-001","payload_digest":"sha256:synthetic"}
```

任务状态与转移：
`detected -> investigating -> diagnosis_review -> fix_proposed -> awaiting_human -> awaiting_deploy -> verifying_recovery -> resolved`；审查失败返回 `investigating`；恢复失败返回 `investigating`；重复事件无状态副作用；无效事件进入 `rejected` 审计，不自动执行。`awaiting_human` 与 `awaiting_deploy` 不占用执行器额度。

输出 JSON：
```json
{"task_id":"inc-001","state":"awaiting_deploy","version":5,"wake_on":["deployment_completed"],"requires_human_approval":true,"evidence_level":"simulated","next_action":null}
```

配置 YAML：
```yaml
schema_version: 1
mode: offline
auto_merge: false
device_write: false
executor: simulator
event_dedupe: event_id
allowed_sources: [simulator]
recovery_gate:
  require_deployment_event: true
  require_post_deploy_metrics: true
backtest:
  forbid_future_evidence: true
  forbid_incident_resolution: true
  forbid_agent_memory: true
```

实施顺序：
1. 定义事件 schema、状态迁移表与任务版本 CAS；只接收 allowlist 事件，记录 `event_id` 唯一键。
2. 事件入库、唤醒标记与状态变更在同一个 `BEGIN IMMEDIATE` 事务；在重复事件、乱序事件、并发事件和进程崩溃时保证至多一次状态推进。
3. 模拟器生成 `ci_failed`、`review_rejected`、`pr_approved`、`deployment_completed`、`metrics_recovered` 等事件；无审批不得推进至部署。
4. `evidence.py` 对每条证据记录 `captured_at`、`available_at`、`source`、`digest`；历史回测以事故当时的 `cutoff` 强制过滤，禁止访问最终事故报告、后续数据与先前 Agent 记忆。
5. `backtest.py` 独立评分：时间定位、影响范围、根因证据链、反事实检验、交接摘要完整性；任何缺少事实标签的指标返回 `null`。
6. 只生成待审 PR 草稿与审计 JSON，不接触真实 GitHub 写权限、客户数据或设备凭证。

## 5. pytest / 模拟器验收门槛（目标，非已达成）
- 至少 40 个合成场景：正常 10、重复/乱序/并发 10、权限与审批 10、时间泄漏/恢复失败 10。
- 事件去重和非法状态跳转阻止率 100%；崩溃重放无重复状态推进；待人审状态执行器调用次数 0。
- 未经批准的 merge/deploy、未确认恢复就关闭任务：0 次；真实设备写操作 0 次。
- 回测未来证据、事故结论和旧记忆泄漏：100% 阻止；每个场景可重置、三次结果一致。
- 记录 P50/P95 唤醒延迟、每个完成任务的执行器调用数、根因准确率、人工审核分钟数、复测误判率；无数据为 `null`，不可假报收益。
- 故障注入：消息重复、订阅丢失、SQLite 锁冲突、执行器额度耗尽、部署回执缺失、监控数据过期；失败应保持等待/人工介入，绝不默认成功。

## 6. 限制与回滚
官方案例未公开全部实现、成本、完整准确率或净生产力对照；不能复制其内部 Codex API。历史回测必须避免后验信息泄漏。若本地模拟出现错关单、越权或重复执行，设置 `incident_loop.enabled=false`，停止事件消费者，保留事件/任务 SQLite 审计数据；恢复现有手动诊断流程，禁止删除或重放真实外部副作用。只允许经验证的纯模拟器数据进入公开仓库。

**可复用价值：** 将“Agent 给出答案”升级为“事件驱动、反事实审查、部署后闭环验证、无泄漏回测”的可测工程契约；与既有 Receipt/Outbox 安全层互补。
