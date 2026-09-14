# vivint
Vivint Demo Repo

AVA / AVA_Voice_Agent2 Agentforce agent work for the `vivint_observability` org:
Analytics dashboard seeding, the Troubleshooting (Smart Hub reboot) subagent, and
its test suites.

- **[`context/CONTEXT.md`](context/CONTEXT.md)** — start here. Narrative summary of the org migration, dashboard seeding gotchas, the agent-renaming trap, the Troubleshooting subagent design, and the test suites.
- **`context/agent/`, `context/apex/`, `context/tests/`, `context/safety/`** — quick-reference copies of the key artifacts described in `CONTEXT.md`.
- **`salesforce/`** — the full SFDX project (metadata, Apex, LWC, the `observability/` Data Cloud seeding scripts). This is the live/working project; edit here going forward.

Not included: `.sf/`, `.sfdx/`, and `observability/.dcenv*` (Data Cloud client-credential
secrets) are gitignored / excluded on purpose — never commit those.
