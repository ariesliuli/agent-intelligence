# 2026-11-25｜验证证据与提交版本绑定（Verification Evidence & Commit Binding）

## ① 目标与关联 Hint
读取 AGENTS.md、README.md、宿主两份规范、state/processed.json、HINT-026/027、11/20 与 11/25 daily、11/23 工程报告及现有 Outbox/Receipt 测试。最高编号 027，不新增。历史 001–023 原文不完整。关联 002/013/023/026/027（历史编号依据现有索引及 026 的引用）。优先偿还验证债务，而非增加执行器能力。
实际查询测试提交 1e3167dd82fd3075e152be7330e412272d4eefdd 的 combined status 与 workflow runs，均为空；后者仅覆盖 PR 触发，不能推断 CI 未运行或失败。

## ② 层级与接口
OpenClaw → 执行器 → Git commit → 独立 CI → JUnit XML + 环境 JSON → 人工/未来确定性验收门禁 → 经验晋升。当前只实现证据采集，不实现自动晋升或远端工具调用。
输入示例：{"commit":"<expected SHA>","required_python":["3.10","3.12"],"suite":"framework/tests"}
输出环境 JSON 字段：commit, python, sqlite, platform, run_id, run_attempt。测试 XML 独立保存。期望决策（尚无解析器）：{"status":"blocked","reason":"missing_or_mismatched_evidence","verified":false}
状态：implemented → tested（实际执行）→ verified（独立核对同版本结果）；缺失、失败、版本不符保持 blocked，不授权设备写入。

## ③ 实现
修改 .github/workflows/framework-ci.yml，提交 6df08d39d3cd0806404094d173a2064bef6bd4af。保留 Ubuntu 26.04、Python 3.10/3.12、pytest 8.3.5。pytest 增加 --junitxml=verification-results.xml；always() 记录实际 checkout SHA、Python、SQLite、平台、run ID/attempt；upload-artifact@v4 分矩阵及 attempt 保存 XML 与 JSON，保留 30 天。pytest 失败不被 continue-on-error 掩盖。若前置失败，XML 可能缺失，artifact 存在不代表测试执行。
配置（实际 YAML 的核心）：
```yaml
strategy:
  fail-fast: false
  matrix:
    python-version: ['3.10', '3.12']
```
本地复现：cd framework && python -m pytest -q tests/ --junitxml=verification-results.xml
下一步实现只读 evidence_gate.py：从可信 CI 获取 job conclusion、完整 XML 与环境 JSON；检查 SHA、矩阵、run attempt、预期 suite、测试数非零、失败/错误为零、跳过及 xfail 符合批准基线。拒绝缺失/畸形/跨版本/重复矩阵证据。不能信任 Agent 自报 JSON。PR merge commit 与 head SHA 不同，必须按实际 checkout 与预期测试对象比较。
参考：https://docs.pytest.org/en/stable/how-to/output.html#creating-junitxml-format-files ；https://docs.github.com/en/actions/using-workflows/storing-workflow-data-as-artifacts ；https://github.com/actions/upload-artifact/tree/v4 。这些是接口参考，不是本次运行通过证据；本次未独立在线复核文档版本。

## ④ 具体经验：证据查询范围与测试结果不可混淆
触发：查询历史测试提交却返回空列表。环境：GitHub connector，PR 范围的 workflow 查询与 combined status。观察：两个查询返回空数组。原因：查询接口覆盖范围不足以证明 push workflow 状态；替代假设：运行尚未生成、权限限制或记录不可见。解决：使用真实 run ID 查询 jobs/artifacts，绑定 checkout SHA 与 attempt；保留原始 XML。已验证事实仅为查询结果与配置回读；待验证经验为新 artifact 是否完整生成。适用 Python、Node-RED 离线 flow 验证、设备协议模拟、跨模型交接。7 天核对 CI，30 天验证门禁及证据保留，90 天复查错误晋升率。ROI=null。

## ⑤ 验收
两版本各有 XML+JSON，SHA 与实际测试对象一致，失败与错误为 0，测试数量非零，预期 xfail/skip 明确；缺失证据误晋升 0。未来门禁至少覆盖成功、失败、缺失 XML、空 suite、错误 SHA、错误 Python、重复矩阵、旧 attempt 八类测试。当前配置已回读；CI 运行、通过率、artifact 完整性均 null，未部署。

## ⑥ 差异与回滚
此前只输出终端 pytest 日志；现在保存结构化证据和环境。尚无证据消费器、可信发行者或真实设备核对。回滚仅撤销工作流提交，恢复原 pytest 命令；不修改 Outbox、安全校验或真实设备状态。公开仓库只允许合成测试，禁止上传客户日志、密钥或内部地址；未来真实测试不得沿用公开 artifact 路径。
