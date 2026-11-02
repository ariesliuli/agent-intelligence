# HINT-022 — Agent Session Control Plane

**Date:** 2026-11-02. **Archive:** detailed reconstruction from current conversation; original session-local citations not reverified.

## New capability
The report described Agent Host Protocol (AHP) and an October 28 update to Agent Host documentation. Multi-client access to persistent agent sessions; Codex integration was described as experimental.

## Novelty and benefit
Decouple long-running agent session lifecycle from a single chat UI. Reconnect and inspect status rather than restart. Distinct from workflow orchestration, model routing and memory summaries. Does not merge Codex/Claude memories or guarantee recovery after host failure.

## Application
Ubuntu-hosted Codex/Claude workflows for Python, Node-RED, device testing and support automation.

## Minimal Codex task
Implement `agent-session-control-poc` using a supported host and client SDK; read-only session list, status, ordered events, reconnect and audit. No remote command execution in v1.

## Acceptance criteria
- No desktop window required.
- Two clients see consistent state.
- Five-minute disconnect recovery without replaying completed actions.
- Test a supported harness; test Codex experimental integration separately.
- Approval protections preserved; host not exposed publicly.
- Explicit host-failure state.

**Evidence caution:** Confirm current upstream docs before deployment; client-provided tools may not survive disconnect.
