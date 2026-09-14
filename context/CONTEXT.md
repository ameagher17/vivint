# Vivint Observability — Context for Claude Desktop

Start here in a fresh conversation. This folder is a pulled-together snapshot of
everything relevant to the **`vivint_observability`** Salesforce org — the AVA
agent migration, the Analytics/Tableau Next dashboard seeding, the Troubleshooting
subagent build, and the test suites written against it. Full session history
lives in `~/.claude/projects/-Users-ameagher-ai/memory/` (`ava-vivint-observability.md`
+ `ava-afkeynote-obs-seed.md`) — this doc is the condensed version plus copies of
the actual artifacts.

**Live project (not duplicated here):** `/Users/ameagher/ai/ava_migration` — the
SFDX project for this org. Metadata, the full `.agent` bundle source, Apex, and
the `observability/` Python seeding scripts (with `.dcenv` creds) live there.
This folder only holds copies of the specific files referenced below for quick
reading; edit the originals in `ava_migration`, not the copies here.

## Org facts

- Org: **`vivint_observability`**, login `trailsignup.d359dd0f913e65@salesforce.com`, org id `00Dfj00000gk5iuEAA`.
- Source org content was migrated from: `afkeynote@salesforce.com` (alias `ava_source`).
- Two agents now live in this org:
  - **`AVA`** — chat-only Service Agent, migrated from afkeynote, v14+ Active. See "Migration" below.
  - **`AVA_Voice_Agent2`** — the voice-capable agent actively being developed (Troubleshooting subagent, test suites). This is the one referenced by files in this folder.
- Reference/sibling org: **`afkeynote`** has its own `AVA_Voice_Agent`, seeded to match `vivint_observability`'s dashboard numbers exactly (see `ava-afkeynote-obs-seed.md`).

## 1. Migration: AVA copied from afkeynote (2026-09-11)

Copied the AVA EinsteinServiceAgent bot + 4 flows into `vivint_observability`.

- **Key gotcha:** must publish the `AiAuthoringBundle`, not just deploy `GenAiPlannerBundle` — the latter's embedded `.agent` file retrieves empty (0 bytes) and the agent won't show up in Agentforce Studio. Fix: retrieve `AiAuthoringBundle:AVA_13`, edit the `.agent`, then `sf agent publish authoring-bundle --api-name AVA` + `sf agent activate`.
- Chat-only transform: removed the `VoiceCallId` linked variable.
- Bot user had to be provisioned fresh (`ava_voice_agent@00dfj00000gk5iu664133047.ext`) — an EinsteinServiceAgent bot requires an assigned agent user.
- `Route_to_Agent` escalation flow repointed to target org's `sfdc_livemessage` channel + `SDO_Service_Messaging` queue.

## 2. Analytics dashboard seeding (2026-09-11 → 2026-09-12)

Goal: make the Analytics tab (Tableau Next), filtered to AVA / last 30 days, read
**20.04% Containment, 91% CSAT, 2:45 (→ 2.75 min) Customer Effort, 84% Customer
Resolution Rate**, with believable month-over-month deltas vs. an August baseline.

- Non-SDO trial org → seeded via **Data Cloud Ingestion API** (client-credentials Connected App), not a real data-sync recipe.
- Blank Analytics tab troubleshooting: root cause was the **Tableau Next app not provisioned** (separate from the semantic model). Enabling Tableau Next + "turn on AI features" auto-provisions the standard Service Agent Analytics app — no custom dashboard needed for the base case. Takes up to ~1hr to provision.
- The **actual dashboard KPI formulas** (pulled from the live semantic model, not guessed):
  - Containment = COUNTD(sessions with no `CLOSED_TRANSFERRED` SESSION_END step) / COUNTD(all sessions).
  - Contact Resolution = COUNTD(sessions with a `CLOSED_ACTION` SESSION_END step) / COUNTD(non-transferred sessions).
  - Customer Effort = AVG per-session `DATEDIFF('second', MIN(interaction start), MAX(interaction end))` — displayed as minutes (no native duration format exists; had to edit the calc to `/60.0` and relabel).
  - CSAT = avg numeric `AiAgentTag` value via TagAssociation → session.
- **Tiles filter to a specific agent + exclude step-less sessions from the containment numerator** — this tripped up an early verification pass (got 19.22%/87.96% instead of 20.04%/84%) until accounted for.
- Re-tuning outcome counts **requires a purge-then-repush**, not a plain UPSERT, because step ids embed the outcome name — lowering a count otherwise strands orphan steps that get miscounted.
- Full gotcha list (DMO categories, duplicate-row corruption, Trino date-diff syntax, purge throttling, etc.) is in memory file `ava-vivint-observability.md` — read it before touching the seeding scripts again.
- Companion seeding for the **afkeynote** reference org (`AVA_Voice_Agent`, matching numbers) is in `ava-afkeynote-obs-seed.md` — same dashboard, same formulas, different DataSourceId prefix.

## 3. The `_v<N>` publish naming trap (2026-09-13) — read before creating any new agent copy

**Never name a local `AiAuthoringBundle` copy `<Name>_v<N>`** (e.g. `AVA_Voice_Agent_v2`) when you intend a brand-new, separate agent. The `sf agent publish authoring-bundle` resolver strips a trailing `_v<digit>` and treats it as "a new version of base bundle `<Name>`" — it silently republished onto the *existing* `AVA_Voice_Agent` bot and renamed it in place. Bot renames are unsupported/hazardous and can't be cleanly reverted.

What happened and the fix, in short:
1. `AVA_Voice_Agent_v2` copy → accidentally renamed the live `AVA_Voice_Agent` bot's label/DeveloperName to `AVA_Voice_Agent_v2`. Left as-is (content untouched, only cosmetic name changed) rather than risk further repair.
2. The actually-intended second agent had to be named with **no trailing `_v<N>` pattern** — landed on **`AVA_Voice_Agent2`** (no underscore), which published clean as a genuinely new bot.
3. Each new bot copy needs its **own dedicated `default_agent_user`** (never reuse one — it silently re-targets the existing bot), with licenses **and** the `AgentforceServiceAgentUser` **permission set** (not just the license) assigned before the first publish attempt.
4. Stale local bundle folders left over from a bad retrieve can also get swept into a deploy of the whole `aiAuthoringBundles/` dir — clean those up too.
5. Byproduct debris (`AVA_Voice_Agent_v3` stray Bot, stray Inactive v2 BotVersion) is sitting in the org, inert but needs manual Setup UI cleanup — can't be removed via CLI.

**Rule of thumb:** no `_v<N>` suffix on a new copy's name, ever; always a fresh dedicated bot user; assign the permission set before first publish.

## 4. Troubleshooting subagent — Smart Hub remote reboot

Added to `AVA_Voice_Agent2` (see `agent/AVA_Voice_Agent2.agent`, `subagent Troubleshooting:`).

> For the plain-language, customer-facing walkthrough of this flow (offer → reboot → automatic retry → resolution check → escalation, plus the guardrails), see **[`agent/TROUBLESHOOTING_SUBAGENT.md`](agent/TROUBLESHOOTING_SUBAGENT.md)**. The notes below are the implementation-level detail.

**Behavior:** when the customer reports their Smart Hub panel/system is offline or malfunctioning, the agent offers a remote reboot, runs it, and handles retry/escalation:
1. Ask permission once (exact scripted line — reboot takes ~1 min, security monitoring briefly offline).
2. On agreement, run `Run_Smart_Hub_Reboot` (Apex `run_smart_hub_reboot` via `InvocableSmartHubDeviceReboot`). On decline, escalate to a human.
3. If the first attempt fails, `before_reasoning` automatically triggers exactly **one** retry (`Retry_Smart_Hub_Reboot` / `retry_smart_hub_reboot.cls`) — max 2 attempts total.
4. On success, ask the customer to confirm it's fixed; `mark_resolved` sets `troubleshooting_resolved`. If still broken after a successful reboot, or after both attempts fail, escalate to a human.
5. `after_reasoning` sets `troubleshooting_reboot_offered = True` so the router (`agent_router`) routes back into `Troubleshooting` on the next turn if the issue isn't resolved yet — this is the `before_reasoning` check on `agent_router` (`if troubleshooting_reboot_offered == True and troubleshooting_resolved == False: transition to @subagent.Troubleshooting`).

**State variables** (all in the `.agent` file's `variables:` block): `troubleshooting_reboot_offered`, `troubleshooting_reboot_attempted`, `troubleshooting_reboot_attempts` (max 2), `troubleshooting_reboot_status` ("Success"/"Failed"), `troubleshooting_resolved`.

**Apex backing** (copied into `apex/` here):
- `InvocableSmartHubDeviceReboot.cls` — invocable wrapper.
- `run_smart_hub_reboot.cls` / `retry_smart_hub_reboot.cls` — first attempt / automatic retry, each returning `rebootStatus` + `outputMessage`.
- `FirmwareRebootDemo.cls` — larger demo class in the same area (firmware-update-via-reboot flow); check `ava_migration` for how it relates to the two reboot classes above if extending this.

Guardrail baked into the reasoning instructions: never disclose internal IDs, action names, or the raw reboot status value to the customer; exactly one question per turn.

## 5. Test suites written against AVA_Voice_Agent2

Two parallel test artifacts exist for the firmware/troubleshooting flow — **note they're not fully in sync with the subagent above**, see discrepancy note below.

- **`tests/Quick_Agentforce_Service_Agent-firmware-troubleshooting.yaml`** — human-readable test case spec (5 utterances: firmware update request, direct reboot request, "still not working" escalation, off-topic deflection, prompt-injection resistance).
- **`tests/AVA_Firmware_Troubleshooting.aiEvaluationDefinition-meta.xml`** — the same 5 cases as a deployable `AiEvaluationDefinition` (per-case `topic_assertion` / `actions_assertion` / `output_validation` expectations), runnable via `sf agent test run` / `sf agent test results` against the org.
- **`safety/NIST_Adversarial_Safety-testSpec.md`** — copy of the `nist-adversarial-safety-test` skill spec (six hard blocks: system-prompt disclosure, prompt-injection, unsolicited PII, sensitive-data egress, safety-classifier override, protected-category refusal). Use the `nist-adversarial-safety-test` skill to actually run this against the agent and get a SAFE/NEEDS_REVIEW/UNSAFE verdict.

**Discrepancy to resolve next session:** both test files target `subjectName: Quick_Agentforce_Service_Agent` and assert `expectedTopic: Firmware_Updates` — but the live `.agent` file's subagent is named `Troubleshooting` (Smart Hub reboot), not `Firmware_Updates`, and the current design routes reboot failures to `escalate_to_human` directly rather than the test's `Go_to_Escalation` action name. These test files likely predate the current `Troubleshooting` subagent implementation (or were drafted against an earlier/planned topic name) and need to be updated to match: rename `subjectName`/topic references to the real agent (`AVA_Voice_Agent2`) and subagent (`Troubleshooting`), and align action names (`escalate_to_human`) and expected outcomes with the actual scripted reboot/retry/escalate flow in §4 before re-running `sf agent test run`.

## Where things live

| What | Path |
|---|---|
| Live SFDX project (edit here) | `/Users/ameagher/ai/ava_migration` |
| `.agent` source (copy here for reading) | `agent/AVA_Voice_Agent2.agent` |
| Apex reboot classes (copies) | `apex/*.cls` |
| Test spec + eval definition (copies) | `tests/*` |
| NIST safety test spec (copy) | `safety/NIST_Adversarial_Safety-testSpec.md` |
| Observability seeding scripts + creds (**not copied — live only**) | `/Users/ameagher/ai/ava_migration/observability/` |
| Full memory (org history, every gotcha) | `~/.claude/projects/-Users-ameagher-ai/memory/ava-vivint-observability.md` |
| Companion afkeynote seeding memory | `~/.claude/projects/-Users-ameagher-ai/memory/ava-afkeynote-obs-seed.md` |
