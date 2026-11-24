# Codex Agent 库进化监测（Codex Agent Evolution）— 2026-11-25

# HINT-027｜服务端技能分发与运行时版本绑定（Skills over MCP & Runtime Version Binding）

**发现日期：** 2026-11-25  
**原始发布日期：** 2026-11-24  
**证据等级：** 官方产品发布，公开 Beta；本仓库方案 implementation_proposed，未运行、未部署。

## 1. 原始证据
Anthropic，*MCP servers can now ship skills, run tasks, and more with Claude*：https://claude.com/ja/resources/articles/skills-over-mcp-tasks-and-more
官方确认 MCP 服务端可同时提供技能、工具和资源，技能按需加载并随服务端更新。Skills over MCP 为公开 Beta，Enterprise 尚待推出；Tasks 与 Elicitation 已正式可用，文件上传尚待推出。兼容客户端才能使用相应扩展；未核实 Codex CLI/OpenClaw 原生支持或具体 wire schema，不假定所有客户端可用。

## 2. 真正新意
HINT-001/020 已涉及技能质量与进化（历史原文未完整恢复）；HINT-025 已提出安装期依赖锁定和晋升；HINT-024 涉及规则筛选；HINT-026 涉及异步事件恢复。本次不重复这些机制。新增连接点是**运行期远程技能发现、按需加载与服务端工具契约的同版本绑定**：服务器更新不应自动改变正在运行任务的指令或权限。将远程技能先作为候选数据，经过宿主批准后才可使用，任务冻结技能内容摘要与工具 schema 摘要；重试、跨模型接管均检查同一快照。此绑定策略为本仓库设计，不是 MCP 已保证的安全属性。

## 3. 收益与应用
预期降低多执行器手动分发技能的维护成本，减少技能与工具 schema 漂移造成的错误；无实测收益。Python：按版本加载解析器与测试规则；Node-RED：按节点版本加载 flow 检查技能；设备协议：按固件及协议版本提供 LoRaWAN/MQTT/CGI 排障说明；技术支持：集中发布经审核的排障知识并保留工单使用版本。技能不得授权设备写入、部署或外部发布。

## 4. 最小实现（交给 Codex）
在 framework/skill_binding/ 创建 adapter.py、registry.py、policy.py、snapshot.py；tests/test_skill_binding.py。先使用离线 mock adapter，核实官方扩展文档与客户端版本后再实现真实协议适配，不把以下内部 JSON 当作 MCP wire format。

输入（合成）：
```json
{"task_id":"sim-1","server_id":"simulator","skill_id":"mqtt-diagnose","skill_digest":"sha256:<synthetic>","tool_schema_digest":"sha256:<synthetic>","firmware":"sim-v1"}
```
输出：
```json
{"decision":"blocked","reason":"unapproved_snapshot","snapshot_id":null,"permissions_added":[]}
```
实现步骤：
1. 定义内部 adapter 接口 discover/fetch；能力不支持时回退已批准本地技能或阻塞，不静默启用新版本。
2. 对原始技能字节与规范化工具 schema 计算 SHA-256；限制大小、文件路径、来源；拒绝未知来源、路径穿越、隐式脚本执行。摘要只证明内容一致，不证明可信。
3. 复用 HINT-025 晋升门禁，将 server_id、skill_id、两个摘要、适用环境及审批记录绑定；远程内容不能修改宿主策略。
4. SQLite 保存不可变任务快照；开始、重试、跨执行器恢复及工具调用前校验快照。服务器 schema 变化时阻塞并要求重新审核，不自动重放外部操作。仅客户端检查不能证明远端实际实现不变，生产接入须有服务端版本保证或独立验证。
5. 默认 offline、read_only、auto_promote=false；工具权限仍由独立确定性门禁控制。仅模拟数据。

## 5. 验收目标（未执行）
至少40个合成用例：正常加载10、版本漂移/恢复10、恶意输入/权限10、离线/不支持/缓存10。未知来源、未批准摘要、schema 漂移、权限扩张、路径穿越在测试集中100%阻止；任务重试与跨执行器恢复快照一致率100%；未经批准的真实写入和脚本执行0次。测量每任务加载字节、Token、P95延迟、人工审核分钟数；无数据为 null。对比本地固定技能与远程绑定方案，质量不得低于基线；三次离线回放一致。

## 6. 局限与回滚
公开 Beta 不等于生产可靠性证明；没有独立部署收益、客户端兼容矩阵或本仓库实测。远端工具行为可能在 schema 不变时变化。设置 remote_skills.enabled=false，恢复最后批准的本地技能和工具配置；保留审计与任务快照，不重放副作用。历史 HINT-001～023 原文未完整恢复，语义去重有残余风险。


## 去重与归档
核对 state/processed.json 最高编号026、HINT-027 路径未存在、HINT-001 重建摘要、HINT-024/025/026 原文、AGENTS.md、README.md、宿主因果直觉规范及11月20日归档。目录读取失败，历史原文未完整恢复，不宣称全量去重。新增 HINT-027，详见 [完整 Hint](../../hints/HINT-027.md)。未执行 pytest；无客户数据或凭证。
