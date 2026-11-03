# HINT-024｜批量判定式规则预筛选（Batch Decision Rule Prefilter）

**发现日期：** 2026-11-04  
**依据发布日期：** Decisions API 正式提供 2026-10-22；Qodo 实际工作流案例 2026-11-02。  
**证据等级：** 官方 API 已提供；Qodo 的跨仓库审查工作流为企业自述案例；“通过 Decisions API 选择 200 条规则”是受访者提出的**潜在用法**，不是已证明的生产部署或收益。

## 一、原始来源
1. OpenAI Decisions API 官方文档：https://developers.openai.com/api/docs/guides/decisions
2. OpenAI 官方 Qodo 案例（2026-11-02）：https://openai.com/index/qodo-codex-plugin/
3. OpenAI Decisions API 发布说明：https://openai.com/index/decisions-api/

## 二、新意与既有 Hint 区别
HINT-001 是 Skill 质量门禁，HINT-008 是能力角色分配，HINT-021 是模型路由，HINT-023 是工具调用顺序验证；这些模块未具体解决**每次运行要从数十至数百条工程规则中选择哪些规则进入审查上下文**的问题。

新方案把任务分成两段：
- **确定性预过滤**：规则按项目、文件路径、版本、风险等级与所需权限进行静态过滤，权限规则永远不能被模型取消。
- **批量语义预筛选**：对剩余规则用 Decisions API 的 `predicate`（概率判断）或 `choice`（固定类别）一次评估；返回置信度/概率后，根据标注样本校准阈值。低置信度或 API 错误回退到全量规则或人工审核，不静默跳过高风险规则。

官方文档确认 `POST /v1/decisions`、`gpt-6-luna`、每次最多 400 个问题、`predicate/choice/score`、JSON 输入和缓存。官方声称相对 Responses API 最多约 10 倍的响应速度优势；**这不是本项目实测**。价格与地域可用性以实时官方页面为准。

## 三、实际应用
- Python：PR 变更只加载与模块、依赖、测试相关的审查规则。
- Node-RED：根据 flow 节点类型筛选 MQTT/HTTP/证书/重试策略检查。
- 设备协议：按设备类型、固件版本、操作风险筛选 CGI、LoRaWAN payload 和配置约束。
- 技术支持：依据工单类型筛选排查步骤，关键安全规则强制保留。
- Codex/Claude：执行前取适用规则，执行后用独立审查器复核；模型建议绝不等同授权。

## 四、交给 Codex 的最小实现任务
创建 `rule-prefilter-poc/`：
1. `rules.yaml`：每条规则包含 `id, scope, risk, mandatory, conditions, text, source, version`。
2. `selector.py`：先做确定性匹配；保留所有 mandatory 规则；对剩余候选批量调用可替换的 `DecisionClient`。
3. `mock_decisions.py`：离线模拟 API 的概率、拒绝、超时、缺失答案、错误类别。
4. `policy.py`：仅将语义筛选用于**建议性规则**；敏感操作的权限必须由独立的确定性策略判断。
5. `benchmark.py`：对至少 100 个有人工标签的模拟任务比较全量规则、关键词规则、批量判定三组的准确率、漏检率、延迟、token/成本；禁止将合成测试当作真实生产收益。
6. `README.md`：中文说明 API 额外收费、隐私边界、阈值校准、回退和关闭开关；默认离线模式。

接口示例：
```json
{"task_id":"T-001","project":"node-red","changed_files":["flows/sample.json"],"risk":"high","rule_set_version":"v1"}
```
输出：
```json
{"selected_rule_ids":["R-001","R-014"],"mandatory_rule_ids":["SEC-001"],"status":"review_required","evidence":{"mode":"mock","rule_set_version":"v1"}}
```

## 五、验收与回滚
- 强制规则保留率 **100%**，任何模型输出都不得删减强制规则。
- 100 个标注用例中，建议性高风险规则的漏检数 **0**；若不满足则不得启用语义筛选。
- 模拟拒绝/超时/无效返回时 **100% 回退**；无隐式允许。
- 报告 P50/P95 延迟、规则召回率、误报率、每百任务成本；只有真实对照数据才宣称提速或节省。
- 配置开关 `DECISION_PREFILTER_ENABLED=false` 立即回退全量规则。
- 不将客户日志、设备凭证或私有代码发送给外部 API；需要脱敏并经数据治理许可。

## 六、局限
Decisions API 是付费服务，只有 `gpt-6-luna` 可用；分类概率不等于正确率。Qodo 的 200 条规则示例属于**设想**，不是验证结果。权限控制、最终验收、跨仓库依赖真实性均需独立验证。此 Hint 是可实施的工程假设，尚未在用户系统运行。
