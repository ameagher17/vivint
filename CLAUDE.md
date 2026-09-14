# vivint — repo guide for Claude

Vivint demo repo: AVA / `AVA_Voice_Agent2` Agentforce agent work for the
`vivint_observability` org.

## Start here

- **[`context/CONTEXT.md`](context/CONTEXT.md)** — narrative summary of the org
  migration, dashboard seeding gotchas, the agent-renaming trap, the
  Troubleshooting subagent design, and the test suites.
- **`salesforce/`** — the full SFDX project. This is the live/working project;
  **edit here going forward**. Files under `context/` are quick-reference copies.

## Answering questions about the agents

- **"What does the Troubleshooting subagent do?"** → answer from
  **[`context/agent/TROUBLESHOOTING_SUBAGENT.md`](context/agent/TROUBLESHOOTING_SUBAGENT.md)**
  (the customer-facing flow: offer → reboot → one automatic retry → resolution
  check → escalate). `context/CONTEXT.md` §4 has the implementation-level
  detail; `context/agent/AVA_Voice_Agent2.agent` is the source of truth.
- Agent Script source of truth is
  `salesforce/force-app/main/default/aiAuthoringBundles/AVA_Voice_Agent2/AVA_Voice_Agent2.agent`
  (kept identical to `context/agent/AVA_Voice_Agent2.agent`) — if the two
  diverge, trust the `salesforce/` copy and re-sync the `context/` one.

## Never commit

`.sf/`, `.sfdx/`, and `salesforce/observability/.dcenv*` (Data Cloud
client-credential secrets) are gitignored on purpose.
