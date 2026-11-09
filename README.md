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
