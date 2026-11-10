# HINT-025｜Agent 依赖更新的可审计晋升门禁（Auditable Agent Dependency Promotion Gate）

**发现/归档日期：** 2026-11-11  
**原始发布：** 2026-11-03（GitHub Changelog）  
**证据等级：** 官方正式发布（GA）；以下跨执行器验证/自动晋升流程为**本仓库工程设计，尚未部署和实测**。  
**状态：** implementation_proposed（待实现），非安全漏洞修复完成声明。

## 1. 官方来源与边界

1. GitHub，2026-11-03，*Dependabot version updates support Agent Package Manager*：https://github.blog/changelog/2026-11-03-dependabot-version-updates-support-agent-package-manager/
2. GitHub Docs，*Dependabot supported ecosystems and repositories*（查询日期 2026-11-11；页面未给本次引用段落单独发布日期）：https://docs.github.com/en/code-security/reference/supply-chain-security/supported-ecosystems-and-repositories
3. Microsoft APM 官方文档，*Agent Package Manager*（查询日期 2026-11-11）：https://microsoft.github.io/apm/

**已确认：** Dependabot 已支持 `package-ecosystem: apm` 的版本更新；对 `apm.yml` 中**受支持的 Git 依赖**提出 PR，已有 `apm.lock.yaml` 时执行 `apm lock` 更新锁文件；github.com 全计划 GA。**仅版本更新，不支持 APM security updates**。APM 本身支持将 Skills、prompts、instructions、MCP 依赖声明在 manifest 中，并向多个执行器安装；执行器兼容性需按其 targets matrix 检查。

**重要限制：** 支持 `dependencies.apm` 和 `devDependencies.apm` 的特定 Git 引用（SemVer tag、完整 SHA、branch），不自动更新 `mcp:` 条目、对象形式依赖、本地路径、无 ref 条目等。分支依赖需已有 lockfile；Dependabot 不会凭空生成 lockfile。APM 的安装期策略不能代替运行时工具权限。

## 2. 相比现有 Hint 的真正新意

- HINT-001：Skill 质量门禁；HINT-003：经验沉淀；HINT-020：Skill 进化；HINT-023：工具顺序验证；HINT-024：规则预筛选。
- **新增连接点**：把外部 Skill/指令依赖当作有版本、有锁定内容、有 PR 差异、有回归测试的**软件供应链**管理，而不是由 Agent 直接覆盖共享经验库。
- Dependabot 只负责提出更新，**不负责证明新 Skill 的因果经验正确、安全、兼容 OpenClaw/Codex/Claude**。真正的工程增量是「上游更新 PR → 宿主验证 → 人工/策略批准 → 分阶段晋升 → 可回滚锁定版本」。
- 与 `architecture/HOST-CAUSAL-INTUITION.md` 对齐：经验晋升必须有反例测试和证据，不可把“版本更新”自动视为“经验进化”。

## 3. 具体收益与适用性

**预期收益（尚未测量）：** 减少手工发现 Skill 更新的遗漏、明确来源与内容变更、降低因提示词/工具契约漂移导致的静默退化；不声称已降低 Token 或故障率。

- **Python**：对更新 PR 运行 JSON Schema 校验、恶意/越权指令扫描、pytest 和未见样例回归。
- **Node-RED**：使用脱敏 flow fixtures，检测新 Skill 是否改变 MQTT/HTTP 重试策略、节点配置建议或部署前审批要求。
- **设备协议**：为 LoRaWAN payload、HTTP CGI、MQTT QoS 等维护协议版本与负样例；任何真实设备写操作仍需独立授权。
- **技术支持**：验证新排障 Skill 在旧/新固件和反例上的诊断正确率，避免“看似更智能”的错误迁移。
- **多执行器**：在 Codex CLI、Claude Code、OpenClaw 的兼容性测试中分别记录结果；某一执行器通过不代表全部通过。

## 4. 最小实现任务（交给 Codex）

**前提**：本仓库目前未确认有可更新的真实外部 APM 依赖。先在**独立试验目录/分支**创建安全、公开、版本化的测试依赖；不要为了演示在生产配置中添加未知第三方 Skill。

```yaml
# .github/dependabot.yml（示例；仅在根目录确有 apm.yml 后启用）
version: 2
updates:
  - package-ecosystem: "apm"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 3
```

```yaml
# apm.yml（示意，不是可直接使用的真实依赖）
name: agent-intelligence-poc
version: 0.1.0
dependencies:
  apm:
    - example-org/approved-skill-repo#v1.0.0
```

**输入事件契约（合成）：**
```json
{
  "pr": 123,
  "dependency": "example-org/approved-skill-repo",
  "from_ref": "v1.0.0",
  "to_ref": "v1.1.0",
  "manifest": "apm.yml",
  "lockfile": "apm.lock.yaml",
  "harnesses": ["codex", "claude-code", "openclaw"],
  "risk": "high"
}
```

**验证输出契约：**
```json
{
  "decision": "block",
  "evidence_level": "simulated",
  "checks": {
    "manifest_valid": true,
    "lockfile_consistent": true,
    "source_allowlisted": true,
    "no_permission_expansion": false,
    "regression_passed": null,
    "harness_compatibility": {"codex": null, "claude-code": null, "openclaw": null}
  },
  "reason": "权限扩展，需人工审查"
}
```

1. `experiments/apm-update-gate/`：最小 `apm.yml`、已有 lockfile、固定版本的公开测试 Skill；先确认 APM 版本、锁文件生成方法及目标执行器支持情况。
2. `gate.py`：解析 PR manifest/lock diff；仅允许批准的来源和明确版本；对新增 MCP/权限/工具调用能力默认 `block`。
3. `policy.yaml`：定义可信来源、允许的目标执行器、是否需人工审批、风险级别；不允许 AI 修改自己的审批策略并自动合并。
4. `tests/test_gate.py`：覆盖 tag/SHA/branch 更新、缺锁、MCP 变更、隐藏 Unicode、权限扩张、缺测试、执行器不兼容、回滚。
5. `benchmark.py`：比较旧/新 Skill 在相同的**未见任务**上正确率、误诊率、Token、延迟和人工审查成本；输出每执行器指标，缺数据写 `null`。
6. CI 只允许在无敏感凭证的沙箱中执行 PR 测试，`contents: read`；不能在不可信 PR 中使用具有写权限的密钥；禁用自动合并。

## 5. 验收标准、失败模式与回滚

| 项目 | 可量化门槛 |
|---|---|
| 未授权依赖来源/权限扩张 | 100% 阻止（模拟样本） |
| 无 lockfile / lock 不一致 | 100% 阻止晋升 |
| 新增 MCP 工具未经审批 | 100% 阻止 |
| 跨执行器缺失测试结果 | 必须标 `unknown` 并阻止生产晋升 |
| 测试集 | 至少 30 个合成正/负例 + 10 个未见任务，记录覆盖范围 |
| 质量 | 新版不能低于既定基线；比较准确率/误判/Token/延迟，不只看通过数 |
| 回滚 | 在模拟器中通过锁文件恢复旧版本，重复运行结果一致 |

**失败模式**：更新 Skill 内含提示注入、执行器解析差异、锁文件漂移、隐式 MCP 扩权、SemVer tag 被重写、更新后错误率升高。Dependabot 的 PR 不是安全背书；`apm.lock.yaml` 内容哈希有助于复现但不能证明内容可信。

**回滚**：不合并 PR，或恢复上次已批准的 `apm.yml` + `apm.lock.yaml`；清理对应安装缓存并重新验证。真实设备、客户信息、凭证不得进入公共 CI。

## 6. 结论

本次是**已发布的依赖管理能力 + 待验证的宿主晋升门禁工程方案**。没有证据证明当前仓库已安装 APM、已自动收到 Dependabot PR、已跑通多执行器或已获得生产收益。首先完成隔离 PoC，再决定是否引入生产仓库。
