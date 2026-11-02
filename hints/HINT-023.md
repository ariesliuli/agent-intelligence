# HINT-023 — Stateful Tool-Call Oracle

**Date:** 2026-11-02. **Archive:** detailed reconstruction from current conversation; cited study and figures not independently reverified.

## New evidence
The prior report described an EMNLP 2026 study of simulated hardware-design MCP tasks: 14 tools, 8 task groups and 7 local models. It reported best expected-call coverage of 99.0% and correct no-call rate of 80%. These figures are from a simulation and require source verification.

## Novelty
Test the **sequence and side effects of tool calls**, not only final state. Catch redundant reboots, forbidden configuration changes and missing no-call decisions. Complements existing Skill Quality Gate, Device Capability Gateway and audit.

## Application
Simulate UG65 configuration/reboot, camera CGI reads/writes and Node-RED flow edits/deploys.

## Minimal Codex task
Create Python + pytest `stateful-tool-call-oracle` with isolated state machines, 60 normal cases and 20 forbidden/no-call cases. Define initial state, expected calls, prohibited calls, allowed changes and final state.

## Acceptance criteria (proposed, not measured)
- Expected-call coverage >=95%; extraneous valid calls <=1%; tool failures <=2%.
- No-call accuracy 100%; zero forbidden operations.
- Isolated reset per test, three regression runs, JSON + HTML report.
- Compare full/shortened tool descriptions and isolated/accumulated history.

**Limits:** Simulated validation cannot replace production authorization; verify original research before external citation.
