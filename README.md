# Agent Intelligence

A versioned, evidence-first archive for daily AI Agent engineering and productivity-gap research.

## Layout
- `daily/YYYY-MM-DD/codex-evolution.md`: qualifying engineering developments.
- `daily/YYYY-MM-DD/productivity-gap.md`: qualifying productivity-gap signals.
- `hints/HINT-XXX.md`: reusable, numbered engineering proposals.
- `state/processed.json`: deduplication index (not an execution log).
- `templates/`: reporting formats.
- `scripts/`: local import and validation utilities.

**Publishing rule:** No qualifying evidence = no daily report, no new Hint. Keep sources, dates, confidence and limitations explicit. Never commit secrets, customer data, device credentials, private IPs or proprietary records. This repository is intentionally public. Publish only non-sensitive content; keep credentials, customer data and private infrastructure details out of Git.

**Automation status:** Repository scaffolding does not itself connect ChatGPT scheduled tasks to GitHub writes. A separate supported ingest mechanism must be configured and verified.

## 宿主思维与长期评价（Host Reasoning & Long-Horizon Evaluation）

**统一原则：第一性原理反思优先于照搬现成方法。** 根因分析可选 5 Whys（五问法）、FTA（故障树）、FMEA（失效模式分析）和反事实测试；根据风险选择分析深度，避免所有任务都消耗大量 Token。

评价不仅计算当次 Token 与执行时间，还要考虑未来重复故障、返工、停机、错误干预和人工复核。未来避免的损失属于**带不确定性的预测**，没有对照验证不能写成已经实现的收益。

- [宿主级第一性原理与未来止损评估（完整规范）](architecture/HOST-FIRST-PRINCIPLES.md)
- [Agent 宿主行为约束](AGENTS.md)

当前状态：**规范已纳入仓库，尚未实现自动分级与长期预测评测器**。

## 宿主思维体系（Host Cognitive Architecture）

**最终目标：极限优化 AI 因果直觉。** 用庞大且可验证的经验积累，持续进行因果抽象、压缩、迁移验证和淘汰，让 Agent 在低 Token 成本下快速判断，并在经验不适用时自动升级到第一性原理分析。

**所有读取本库的 AI 请从 [AGENTS.md](AGENTS.md) 开始，依次阅读：**

1. [宿主因果直觉进化协议（Host Causal Intuition Evolution）](architecture/HOST-CAUSAL-INTUITION.md)
2. [宿主级第一性原理与未来止损评估（Host First-Principles）](architecture/HOST-FIRST-PRINCIPLES.md)

**状态**：这是跨 Agent 的共享规范与实施路线，尚非已部署的直觉学习引擎。经验检索不会自动改变模型权重；必须由执行器实际加载并验证。
