# 2026-11-11｜Agent 依赖更新的可审计晋升门禁（Auditable Agent Dependency Promotion Gate）

**关联 Hint：** [HINT-025](../../hints/HINT-025.md)  
**来源发布日期：** 2026-11-03（GitHub 官方 GA 公告）  
**证据等级：** 已发布官方功能；本项目实施、性能和安全收益均**未验证**。

## 发现
GitHub Dependabot 正式支持 APM（Agent Package Manager）的部分 Git 依赖**版本更新**：根据 `apm.yml` 提出 PR，存在 `apm.lock.yaml` 时更新锁文件。它**不支持 APM security updates**，也不更新 `mcp:` 依赖。支持的 ref、格式与限制详见官方文档。

## 相对既有体系的新意
此前 HINT-001/020 关注 Skill 质量与进化，HINT-023 关注工具验证；本次增加**跨执行器 Skill 供应链的更新入口和可审计晋升门禁**。上游更新只能提出候选，必须经来源/锁文件/权限差异/负样例/多执行器测试后才允许晋升；这与宿主因果直觉协议的「经验先验证、再复用」一致。

## 应用与实施
适用 OpenClaw 主控 + Codex CLI/Claude Code 执行器的共享 Skills；Python 编写验证器，Node-RED 与 LoRaWAN/MQTT/HTTP 设备协议用脱敏模拟场景进行回归。最小任务、输入输出 JSON、配置 YAML、30+10 样例验收、回滚策略详见 HINT-025。禁止把更新 PR 当作自动授权。

## 局限
本仓库尚无本次验证的 APM 实装和实测；GitHub 已发布的 Dependabot 支持**不等于**该方案已产生可靠性收益。没有验证数据不填节省比例，也不引入未经审查的第三方 Skill。

## 原始来源
1. GitHub Changelog（2026-11-03）：https://github.blog/changelog/2026-11-03-dependabot-version-updates-support-agent-package-manager/
2. GitHub Docs（2026-11-11 查阅）：https://docs.github.com/en/code-security/reference/supply-chain-security/supported-ecosystems-and-repositories
3. Microsoft APM Docs（2026-11-11 查阅）：https://microsoft.github.io/apm/
