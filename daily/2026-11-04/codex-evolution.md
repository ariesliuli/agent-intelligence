# 2026-11-04｜Codex Agent 库进化监测

## 本次结论
新增 **HINT-024：批量判定式规则预筛选（Batch Decision Rule Prefilter）**。相对历史 Skill 门禁、角色分配、模型路由，新增的是将大规模**建议性工程规则的适用性选择**从生成式推理中拆出，以固定类型的批量判断接口预筛选，并且保留确定性的强制权限规则。

## 日期与来源
- 2026-10-22：OpenAI Decisions API 一般提供，官方开发者文档：https://developers.openai.com/api/docs/guides/decisions
- 2026-11-02：Qodo 官方案例：https://openai.com/index/qodo-codex-plugin/ 。Qodo 描述现有 Codex 插件的上下文审查工作流，但其使用 Decisions API 筛选 200 条规则仍是未来机会，而非验证的生产成果。

## 可落地收益与证据边界
官方支持最多 400 问/次的固定类型判断，支持 JSON、概率和缓存；相对普通生成接口的速度提升是官方产品主张，未在本项目实测。潜在收益为减少无关规则进入审查上下文、降低冗余调用，但需要实际测量。风险：分类漏检、阈值偏差、外部 API 成本及隐私。强制安全规则不允许被模型过滤。

## 工程任务
详见 [HINT-024](../../hints/HINT-024.md)：可替换 DecisionClient、离线模拟器、规则库、100 条标注任务、性能与漏检对照、失败回退；优先在 Python/Node-RED/设备协议技术支持中做离线 PoC。

## 去重
现有 HINT-001–023 未明确覆盖**批量类型化规则适用性判定**；HINT-021 的模型路由和 HINT-023 的工具调用验证属于不同决策层。没有为旧内容另起编号。

## 归档状态
若此文件在 GitHub 可见，则表示归档成功；`state/processed.json` 必须同步更新，避免重复编号。
