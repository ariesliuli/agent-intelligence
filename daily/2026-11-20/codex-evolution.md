# Codex Agent 库进化监测（Codex Agent Evolution）— 2026-11-20

## 新进展（New Development）
- **发布日期：** 2026-11-19
- **原始来源：** OpenAI Engineering，*How OpenAI’s Performance Factory keeps ChatGPT fast*：https://openai.com/index/how-openai-performance-factory-keeps-chatgpt-fast/
- **证据等级：** 官方生产实践自述；非第三方审计。官方称三个月多 1,700+ 调查、600+ 找到根因，人工复核 100 条建议中 70% 准确。不能推断自动修复数量、节省工时或 ROI。
- **计划与已实施区分：** 告警调查、独立对抗审查、人工批准 PR、部署后验证和事件唤醒已在官方案例运行；无需人审的自动发布、主动发现更多优化仍属探索。

## 相比已有 Hint 的真正新意（Novelty）
不重复通用状态机、Skill、工具验证、模型路由或独立审核；新增重点为**事件唤醒等待任务 + 部署后恢复门禁 + 当时证据可见性约束的历史回测**，并将诊断准确率和交接摘要质量分别评估。对照 HINT-001～025 的已知记录及 HINT-023～025 原文，未发现 Performance Factory 同源归档；HINT-001～022 原始文档仍未完整恢复，语义去重存在残余风险。

## 工程收益与限制（Benefit & Limits）
预期减少等待轮询的模型调用和未复测就结案的风险；本仓库尚无实测收益。官方的云端 Codex 调用接口为内部 API，不能视为公开可调用接口。

## 应用（Application）
Python：CI/SQLite 事件闭环；Node-RED：脱敏 flow 的部署后复测；设备协议：LoRaWAN/MQTT/CGI 故障模拟和版本证据冻结；技术支持：工单根因反事实审查、修复后验收；OpenClaw/Codex/Claude：任务状态外置、执行器可替换。

## Codex 最小实现（Minimal Implementation）
详见 [HINT-026](../../hints/HINT-026.md)：在 `framework/incident_loop/` 实现事件去重、状态迁移、唤醒订阅、人工审批、恢复验证与禁止未来证据泄漏的历史回测；使用 SQLite `BEGIN IMMEDIATE`，不触碰真实设备和生产密钥。

## 验收（Acceptance）
40+ 合成用例，非法状态跳转/重复事件/未来证据泄漏 100% 阻止，未经批准部署 0 次，未验证恢复就结案 0 次；三次可重复，测量调用数与 P95 延迟；未运行的指标全部标为 `null`。

## 去重与归档（Deduplication）
- **新增编号：** HINT-026（核对 `state/processed.json` 当前最高为 025）。
- **状态：** implementation_proposed，未执行 pytest，未部署。
- **来源与历史：** `state/processed.json`、`AGENTS.md`、`README.md`、HINT-023/024/025；对其余历史原文未作虚假完整核验。
- **隐私：** 无密钥、客户信息、设备凭证或内部地址。
