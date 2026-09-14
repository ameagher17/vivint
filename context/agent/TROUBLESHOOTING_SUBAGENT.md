# Smart Hub Troubleshooting subagent — how it works

Canonical plain-language description of the `Troubleshooting` subagent in
`AVA_Voice_Agent2`. Source of truth for the implementation is
[`AVA_Voice_Agent2.agent`](AVA_Voice_Agent2.agent) (`subagent Troubleshooting:`),
mirrored at `salesforce/force-app/main/default/aiAuthoringBundles/AVA_Voice_Agent2/AVA_Voice_Agent2.agent`.

**Trigger:** The customer tells AVA their Smart Hub panel/system is offline,
unresponsive, frozen, or otherwise malfunctioning. The router hands off to the
`Troubleshooting` subagent.

## Flow

1. **Offer** — AVA asks for permission first: "I can try rebooting your Smart Hub
   panel remotely — that usually takes about a minute, and your security
   monitoring will be briefly offline while it restarts. Want me to go ahead?"
2. **Decline path** — If the customer says no (or asks for a person), AVA hands
   off to a live agent immediately.
3. **First attempt** — If they agree, AVA runs `Run_Smart_Hub_Reboot` (Apex
   `run_smart_hub_reboot`), silently, then reports the result.
4. **Automatic retry** — If the first attempt fails, a single retry runs
   automatically via `Retry_Smart_Hub_Reboot` (Apex `retry_smart_hub_reboot`)
   before AVA says anything — the customer never has to ask twice.
5. **Resolution check** — On a successful reboot, AVA asks once: "Okay, I've
   rebooted your Smart Hub panel. Is everything working now?"
   - Confirmed fixed → marks the issue resolved, asks if there's anything else
     needed, and the router takes back over cleanly (no re-routing the
     customer's confirmation message).
   - Still broken after a successful reboot → escalate to a live agent.
6. **Both attempts fail** → escalate to a live agent with one clear message, no
   repeated retries beyond the two.

## Guardrails baked into the instructions

- Exactly one question per turn, short/conversational responses.
- Never disclose internal IDs, action names, or the raw reboot status value to
  the customer.
- Max 2 reboot attempts total (1 manual + 1 automatic retry) — never loops
  indefinitely.
- State is tracked via the 5 `troubleshooting_*` variables so the subagent (and
  the router, on the way back out) always knows exactly where the conversation
  is.

## Where each piece lives

| Piece | Location |
| --- | --- |
| Subagent definition, scripted lines, guardrails | `context/agent/AVA_Voice_Agent2.agent` → `subagent Troubleshooting:` |
| Router hand-off / hand-back | same file → `agent_router` (`go_to_Troubleshooting`, `before_reasoning` re-entry check) |
| State variables | same file → `variables:` block (`troubleshooting_reboot_offered`, `troubleshooting_reboot_attempted`, `troubleshooting_reboot_attempts`, `troubleshooting_reboot_status`, `troubleshooting_resolved`) |
| First-attempt Apex | `context/apex/run_smart_hub_reboot.cls` |
| Retry Apex | `context/apex/retry_smart_hub_reboot.cls` |
| Invocable wrapper | `context/apex/InvocableSmartHubDeviceReboot.cls` |
| Test suites (not yet in sync — see `CONTEXT.md` §5) | `context/tests/` |

See [`context/CONTEXT.md`](../CONTEXT.md) §4 for the implementation-level notes
(variable transitions, Apex outputs, and the known test-suite discrepancy).
