#!/usr/bin/env python3
"""
AVA observability seeder (Path 5 / Data Cloud Ingestion API) for the vivint_observability
org. Engineered so the Analytics tab, filtered to AVA over the last 30 days, reads:

    Containment (Deflection Rate) ...... 20.04%   -> 100 deflected / 499 unique sessions
    Customer Satisfaction (CSAT) ....... 91%      -> GOOD/(GOOD+BAD) interaction feedback
    Customer Effort (Avg Session Dur) .. 2:45      -> 165 s per session (blended w/ real)
    Customer Resolution Rate ........... 84%      -> FULLY_RESOLVED / any-TaskResolution session

Formulas verified against sfm_Agentforce_Analytics_Foundations (see repo notes). The 11
STDM objects (schema_stdm) drive Deflection + Duration; the 3 GenAI DMOs (schema_genai)
drive CSAT + Task Resolution.

The real, already-captured AVA sessions (~9-11, agent api name 'AVA') share scope with
these synthetic rows, so `verify` re-computes each tile's exact numerator/denominator
against the live DMOs; tune the COUNTS block until verify prints the targets, then the
Tableau Next layer re-materialises on its own lag.

Prereq: DC_* env (a CDP-scoped client-credentials Connected App). Agent AVA is already
deployed/active and Agentforce Optimization is on (std_*_Score_AVA_V1 tag-defs exist).
"""
import argparse, csv, datetime as _dt, io, json, os, subprocess, sys, uuid as _uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import schema_stdm as S            # noqa: E402
import schema_genai as G           # noqa: E402
from dc_client import DC           # noqa: E402

# ─── AVA identity ────────────────────────────────────────────────────────────
AGENT_API_NAME = "AVA"
AGENT_VERSION = "v15"
PLANNER_ID = "16jfj000002vo6z"          # active v15 GenAiPlannerDefinition (15-char), matches real sessions
CHANNEL = "SCRT2 - EmbeddedMessaging"
DATA_SOURCE_PREFIX = S.PREFIX           # "AVAObs" — filter/delete key stamped on every STDM row
DAYS_SPREAD = 14                        # sessions spread over the last N days (never day 0; all < 30d)
SESSION_DURATION_SECONDS = 167          # base per-session interaction span (see EFFORT_BUMP)
EFFORT_BUMP = 42                        # first N sessions get +1s so combined avg span = 165s (2:45)
CSAT_VALUE = "91"                       # numeric CSAT tag value (AVA-dash 713 CSAT = AVG(value)*0.01)

# ─── engineered counts for the AVA-Analytics (713) dashboard formulas ─────────
#   AVA-dash Containment = non-CLOSED_TRANSFERRED / all sessions  (target 20.04%)
#   AVA-dash Resolution  = CLOSED_ACTION / non-CLOSED_TRANSFERRED (target 84.00%)
#   The tiles filter to agent api name = 'AVA' and use a FIXED-LOD step formula, so
#   REAL sessions contribute: 9 are AVA (4 others are 'Authoring agent', excluded);
#   of those 9, only 4 have interaction steps (=> counted in the contained NUMERATOR),
#   the other 5 are step-less (in the session-COUNTD DENOMINATOR only, never contained).
#   Real AVA net: +9 total, +4 contained, +0 CLOSED_ACTION.  (verified live 2026-09-12)
N_DEFLECTED = 168                       # -> CLOSED_ACTION  (resolved & contained)  = numerator of Resolution
N_ESCALATED = 793                       # -> CLOSED_TRANSFERRED (transfers)
N_ABANDONED = 28                        # -> CLOSED_USER_REQUEST (contained, not action)
#   synthetic: total=989, contained=196 (168 action + 28 user), transferred=793
#   + real AVA (+9 total, +4 contained) => dashboard total=998, contained=200, action=168
#   Containment = 200/998 = 20.04% ; Resolution = 168/200 = 84.00%
TASKRES_TOTAL = 444                     # sessions given a TaskResolution content-quality category
TASKRES_FULL = 376                      # of those, FULLY_RESOLVED (rest UNRESOLVED)
#   with 6 existing (2 full) -> (2+376)/(6+444) = 378/450 = 84.00%
FEEDBACK_TOTAL = 489                    # interactions given GOOD/BAD feedback
FEEDBACK_GOOD = 445                     # real feedback rows in this org = 0 (confirmed via DISTINCT Id__c),
                                        # so synthetic alone sets CSAT: 445/489 = 91.00%. Increase-only so
                                        # re-push UPSERTs cleanly (lowering counts would strand orphan rows).

OUTCOMES = (["deflected"] * N_DEFLECTED + ["escalated"] * N_ESCALATED + ["abandoned"] * N_ABANDONED)
N_SESSIONS = len(OUTCOMES)
N_CONTAINED = N_DEFLECTED + N_ABANDONED   # 196 = CLOSED_ACTION + CLOSED_USER_REQUEST
CLOSE_NAME = {"deflected": "CLOSED_ACTION", "abandoned": "CLOSED_USER_REQUEST", "escalated": "CLOSED_TRANSFERRED"}

# ─── per-day September distribution (containment chart wobble) ─────────────────
#   The containment line chart buckets sessions by day. If every synthetic session
#   lands on Sep 2..11 with a near-uniform mix, the line is flat ~19% and Sep 12
#   (today) shows only the real AVA sessions (4/9 = 44.44% spike). Instead spread
#   the 989 synthetic across Sep 2..12 (incl. today) with a per-day containment
#   "wobble" (~14-25%) so the line varies and Sep 12 blends real+synthetic to ~22%.
#   Global outcome counts are held EXACTLY at 168/793/28 (largest-remainder
#   apportionment), so the headline MTD KPIs (20.04% / 84%) are unchanged.
_DAY_OFFSETS = list(range(1, 12))          # month_start+1..+11 => Sep 2..Sep 12 (today)
_TOTAL_W = [0.95, 1.05, 0.90, 1.10, 0.92, 1.08, 0.96, 1.04, 0.93, 1.07, 1.00]
_RATE    = [0.15, 0.24, 0.17, 0.22, 0.145, 0.255, 0.185, 0.215, 0.16, 0.23, 0.20]


def _apportion(targets, total):
    """Integer counts closest to `targets` (real numbers) summing EXACTLY to `total`."""
    base = [int(x) for x in targets]
    rem = total - sum(base)
    order = sorted(range(len(targets)), key=lambda i: targets[i] - base[i], reverse=True)
    for i in order[:max(0, rem)]:
        base[i] += 1
    return base


def _fix_sum(vals, total, caps):
    """Nudge `vals` (respecting per-element caps and >=0) so they sum to `total`."""
    diff = total - sum(vals)
    d = 0
    while diff != 0:
        if diff > 0 and vals[d] < caps[d]:
            vals[d] += 1; diff -= 1
        elif diff < 0 and vals[d] > 0:
            vals[d] -= 1; diff += 1
        d = (d + 1) % len(vals)
    return vals


def _september_plan():
    """List of (day_offset, outcome) length N_SESSIONS; exact global outcome counts."""
    nd = len(_DAY_OFFSETS)
    day_tot = _apportion([N_SESSIONS * w / sum(_TOTAL_W) for w in _TOTAL_W], N_SESSIONS)
    contained = _apportion([day_tot[d] * _RATE[d] for d in range(nd)], N_CONTAINED)
    contained = [min(contained[d], day_tot[d]) for d in range(nd)]
    contained = _fix_sum(contained, N_CONTAINED, day_tot)
    action = _apportion([contained[d] * N_DEFLECTED / N_CONTAINED for d in range(nd)], N_DEFLECTED)
    action = [min(action[d], contained[d]) for d in range(nd)]
    action = _fix_sum(action, N_DEFLECTED, contained)
    plan = []
    for d in range(nd):
        off = _DAY_OFFSETS[d]
        user = contained[d] - action[d]
        esc = day_tot[d] - contained[d]
        plan += [(off, "deflected")] * action[d]
        plan += [(off, "abandoned")] * user
        plan += [(off, "escalated")] * esc
    return plan


SEP_PLAN = _september_plan()
assert len(SEP_PLAN) == N_SESSIONS
assert sum(1 for _, o in SEP_PLAN if o == "deflected") == N_DEFLECTED
assert sum(1 for _, o in SEP_PLAN if o == "escalated") == N_ESCALATED
assert sum(1 for _, o in SEP_PLAN if o == "abandoned") == N_ABANDONED
END_TYPE = {"deflected": "resolved", "abandoned": "resolved", "escalated": "escalated"}
TOPIC = {"deflected": "appointment_scheduling", "abandoned": "appointment_scheduling", "escalated": "billing_support"}
ACTION = {"deflected": "book_appointment", "abandoned": "book_appointment", "escalated": "process_payment"}
INTENT = {"deflected": "Schedule Appointment", "abandoned": "Reschedule Appointment", "escalated": "Billing Question"}
INTENT_DEF = "AIE_Request_Category_" + AGENT_API_NAME

# ─── prior-month (August) baseline for month-over-month comparison tiles ───────
#   Dashboard tiles compare CurrentMonthToDate vs PriorPeriod (prior month) on
#   AI_Agent_Session.Start_Timestamp. August has 0 real sessions, so this disjoint
#   synthetic batch (new id prefix "aug") is the sole prior-period baseline. Chosen
#   modestly worse than the September targets so every tile shows a positive delta:
#     Containment 17.50% (vs 20.04) | Resolution 80.00% (vs 84) |
#     Effort 190s (vs 165) | CSAT 87 (vs 91).
AUG_TOTAL = 400
AUG_TRANSFERRED = 330                   # -> CLOSED_TRANSFERRED; contained = 70 (17.50%)
AUG_ACTION = 56                         # -> CLOSED_ACTION; Resolution = 56/70 = 80.00%
AUG_USER = 14                           # -> CLOSED_USER_REQUEST; 56+14 = 70 contained
AUG_SPAN_SECONDS = 190                  # per-session interaction span (Effort 190s)
AUG_CSAT_VALUE = "87"                   # 2nd CSAT tag value for the August cohort
AUG_OUTCOMES = (["deflected"] * AUG_ACTION + ["escalated"] * AUG_TRANSFERRED
                + ["abandoned"] * AUG_USER)

_NS = _uuid.uuid5(_uuid.NAMESPACE_URL, "ava-obs/" + AGENT_API_NAME)


def _uid(*p): return str(_uuid.uuid5(_NS, "|".join(str(x) for x in p)))
def _iso(dt): return dt.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (dt.microsecond // 1000)
def _hex(n, seed): return "".join("0123456789abcdef"[(seed * 7 + i * 13) % 16] for i in range(n))
def _json(d): return json.dumps(d, separators=(",", ":"))


def sf_json(org, soql=None, org_display=False):
    cmd = (["sf", "org", "display", "--json", "-o", org] if org_display
           else ["sf", "data", "query", "--json", "-o", org, "-q", soql])
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError("sf failed: " + (out.stderr or out.stdout))
    return json.loads(out.stdout[out.stdout.index("{"):])


def resolve_identities(org):
    org_id = sf_json(org, org_display=True)["result"]["id"]
    users = sf_json(org, "SELECT Id FROM MessagingEndUser LIMIT 5")["result"]["records"]
    obj = "MessagingEndUser"
    if not users:
        users = sf_json(org, "SELECT Id FROM User WHERE IsActive=true LIMIT 5")["result"]["records"]
        obj = "User"
    return org_id, PLANNER_ID, [u["Id"] for u in users], obj


def _edge_rows(dc, sql):
    _, r = dc.query(sql)
    return (r.get("data") if isinstance(r, dict) else None) or []


def resolve_std_scorers(dc):
    def defid(kind):
        rows = _edge_rows(dc, "SELECT ssot__Id__c FROM ssot__AiAgentTagDefinition__dlm WHERE "
                          "ssot__DeveloperName__c='std_%s_Score_%s_V1'" % (kind, AGENT_API_NAME))
        return rows[0][0] if rows else None
    d, a = defid("Deflection"), defid("Abandonment")
    if not d or not a:
        return None

    def vals(defid_):
        m = {}
        for v, tid in _edge_rows(dc, "SELECT ssot__Value__c, ssot__Id__c FROM ssot__AiAgentTag__dlm "
                                 "WHERE ssot__AiAgentTagDefinitionId__c='%s'" % defid_):
            m.setdefault(v, tid)
        return m

    def assoc(defid_):
        rows = _edge_rows(dc, "SELECT ssot__Id__c FROM ssot__AiAgentTagDefinitionAssociation__dlm WHERE "
                          "ssot__AiAgentTagDefinitionId__c='%s' AND ssot__AiAgentApiName__c='%s'"
                          % (defid_, AGENT_API_NAME))
        return rows[0][0] if rows else ""
    return {"defl_val": vals(d), "defl_assoc": assoc(d), "aband_val": vals(a), "aband_assoc": assoc(a)}


# ─── row-graph generator ─────────────────────────────────────────────────────
def build(org_id, planner, user_ids, std, now):
    rows = {o["object"]: [] for o in S.OBJECTS}
    grows = {o["object"]: [] for o in G.OBJECTS}
    ES = org_id
    created = _iso(now - _dt.timedelta(hours=8))

    for did, dev, name, dtype, stype in [
            (_uid("def", "intent"), INTENT_DEF, "Optimization Request Category", "Text", "Generated"),
            (_uid("def", "quality"), "Quality_Score", "Relevance Score", "Number", "Predefined"),
            (_uid("def", "csat"), "CSAT_Score", "Customer Satisfaction", "Number", "Predefined")]:
        rows["AiAgentTagDefinition"].append({
            "Id": did, "Name": name, "DeveloperName": dev, "DataType": dtype, "SourceType": stype,
            "Status": "Active", "Description": name, "CreatedDate": created,
            "DataSourceId": DATA_SOURCE_PREFIX, "ExternalSourceId": ES})
        rows["AiAgentTagDefinitionAssociation"].append({
            "Id": _uid("defassoc", dev), "AiAgentApiName": AGENT_API_NAME, "AiAgentTagDefinitionId": did,
            "IsActive": "true", "CreatedDate": created, "DataSourceId": DATA_SOURCE_PREFIX, "ExternalSourceId": ES})
    intent_def, quality_def = _uid("def", "intent"), _uid("def", "quality")
    intent_assoc, quality_assoc = _uid("defassoc", INTENT_DEF), _uid("defassoc", "Quality_Score")
    # CSAT numeric tag: the AVA-dash (713) CSAT reads ssot__AiAgentTag__dlm.Value (>10) *0.01.
    csat_def, csat_assoc, csat_tag = _uid("def", "csat"), _uid("defassoc", "CSAT_Score"), _uid("tag", "csat")
    rows["AiAgentTag"].append({"Id": csat_tag, "AiAgentTagDefinitionId": csat_def, "Value": CSAT_VALUE,
                               "Description": "CSAT " + CSAT_VALUE, "IsActive": "true", "CreatedDate": created,
                               "DataSourceId": DATA_SOURCE_PREFIX, "ExternalSourceId": ES})
    # August cohort CSAT tag (lower value) so the prior-period CSAT tile reads AUG_CSAT_VALUE.
    csat_tag_aug = _uid("tag", "csat", "aug")
    rows["AiAgentTag"].append({"Id": csat_tag_aug, "AiAgentTagDefinitionId": csat_def, "Value": AUG_CSAT_VALUE,
                               "Description": "CSAT " + AUG_CSAT_VALUE, "IsActive": "true", "CreatedDate": created,
                               "DataSourceId": DATA_SOURCE_PREFIX, "ExternalSourceId": ES})
    q_tag = {}
    for s in range(1, 6):
        q_tag[s] = _uid("tag", "q", s)
        rows["AiAgentTag"].append({"Id": q_tag[s], "AiAgentTagDefinitionId": quality_def, "Value": str(s),
                                   "Description": str(s), "IsActive": "true", "CreatedDate": created,
                                   "DataSourceId": DATA_SOURCE_PREFIX, "ExternalSourceId": ES})
    intent_tag = {}
    for iv in set(INTENT.values()):
        intent_tag[iv] = _uid("tag", "intent", iv)
        rows["AiAgentTag"].append({"Id": intent_tag[iv], "AiAgentTagDefinitionId": intent_def, "Value": iv,
                                   "Description": iv, "IsActive": "true", "CreatedDate": created,
                                   "DataSourceId": DATA_SOURCE_PREFIX, "ExternalSourceId": ES})

    for i in range(N_SESSIONS):
        day_offset, outcome = SEP_PLAN[i]
        topic, action, intent = TOPIC[outcome], ACTION[outcome], INTENT[outcome]
        fails = outcome != "deflected"
        quality = 5 if outcome == "deflected" else (2 if outcome == "escalated" else 1)
        sid = _uid("sess", i)
        uid = user_ids[i % len(user_ids)] if user_ids else "005000000000000AAA"
        uobj = "MessagingEndUser" if str(uid).startswith("0PA") else "User"
        agent_pid, user_pid = _uid("part", i, "a"), _uid("part", i, "u")
        # All current-batch sessions land in current-month-to-date (dashboard's default
        # timeframe filter = CurrentMonthToDate on AI_Agent_Session.Start_Timestamp), so the
        # headline KPIs aggregate exactly this batch. day_offset (1..11 => Sep 2..12) comes
        # from SEP_PLAN so the containment line varies per day; offsets keep clear of the
        # month-start boundary (survives org-timezone underflow). hours 0..11 stay < now
        # (16:xx) so even today's (Sep 12) sessions are in the past.
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start = month_start + _dt.timedelta(days=day_offset, hours=(i % 12), minutes=(i * 7) % 60)
        t0 = start
        span_s = SESSION_DURATION_SECONDS + (1 if i < EFFORT_BUMP else 0)
        turn_end = t0 + _dt.timedelta(seconds=span_s)   # Customer Effort: combined avg span = 165 s
        int_id = _uid("int", i)
        gen_id = _uid("gen", i)                                            # Step.Generation bridge
        trace = _hex(32, i)

        # steps compressed into the first ~25s of the 165s turn (duration reads the TURN, not steps)
        specs = [("VARIABLE_UPDATE_STEP", "__state_update_action__", "", "", ""),
                 ("TOPIC_STEP", topic, "", "", ""),
                 ("LLM_STEP", "agent_router", _json({"gen_ai.request.model": "llmgateway__GPT41"}),
                  _json({"gen_ai.response.finish_reasons": "tool_calls",
                         "gen_ai.output.tool_names": "go_to_" + topic, "mgr.output.payload_type": "llm_event"}), gen_id),
                 ("LLM_STEP", topic, "", _json({"gen_ai.response.finish_reasons": "tool_calls",
                                                 "gen_ai.output.tool_names": action, "mgr.output.payload_type": "llm_event"}), ""),
                 ("ACTION_STEP", action, _json({"mgr.tool.argument_keys": "id"}),
                  _json({"mgr.output.payload_type": "tool_event",
                         "mgr.tool.status": "error" if fails else "success"}), ""),
                 ("TRUST_GUARDRAILS_STEP", "InstructionAdherence", "", "", "")]
        walk = t0
        prev = ""
        for si, (stype, name, iv, ov, gen) in enumerate(specs):
            ss = walk
            dur = 0 if stype in ("VARIABLE_UPDATE_STEP", "TOPIC_STEP") else (16 if fails and stype == "ACTION_STEP" else 1)
            se = ss + _dt.timedelta(seconds=dur)
            err = ("Action %s failed: the downstream service did not return a result." % action) \
                if (fails and stype == "ACTION_STEP") else ""
            rows["AiAgentInteractionStep"].append({
                "id": _uid("step", i, si), "aiAgentInteractionId": int_id, "AiAgentInteractionStepType": stype,
                "name": name, "inputValueText": iv, "outputValueText": ov,
                "startTimestamp": _iso(ss), "endTimestamp": _iso(se), "prevStepId": prev,
                "errorMessageText": err, "attributeText": "", "generation": gen,
                "DataSourceId": DATA_SOURCE_PREFIX, "ExternalSourceId": ES})
            prev = _uid("step", i, si)
            walk = se + _dt.timedelta(seconds=1)

        rows["AiAgentInteraction"].append({
            "Id": int_id, "AiAgentSessionId": sid, "TopicApiName": topic, "AiAgentInteractionType": "TURN",
            "SessionOwnerId": uid, "SessionOwnerObject": uobj, "StartTimestamp": _iso(t0),
            "EndTimestamp": _iso(turn_end), "TraceId": trace, "SpandId": _hex(16, i),
            "DataSourceId": DATA_SOURCE_PREFIX, "ExternalSourceId": ES})
        for role, pid, mtype, text, ts in [
                (user_pid, user_pid, "Input", "I need help with %s." % intent.lower(), t0),
                (agent_pid, agent_pid, "Output",
                 ("I've taken care of that for you." if not fails
                  else "I'm sorry — I wasn't able to complete that request."), turn_end)]:
            rows["AiAgentInteractionMessage"].append({
                "Id": _uid("msg", i, mtype), "AiAgentSessionId": sid, "AiAgentInteractionId": int_id,
                "AiAgentSessionParticipantId": pid, "AiAgentInteractionMessageType": mtype,
                "AiAgentInteractionMsgContentType": "text/plain", "ContentText": text,
                "MessageSentTimestamp": _iso(ts), "DataSourceId": DATA_SOURCE_PREFIX, "ExternalSourceId": ES})

        end_id = _uid("int", i, "end")
        rows["AiAgentInteraction"].append({
            "Id": end_id, "AiAgentSessionId": sid, "TopicApiName": "NOT_SET",
            "AiAgentInteractionType": "SESSION_END", "SessionOwnerId": uid, "SessionOwnerObject": uobj,
            "StartTimestamp": _iso(turn_end), "EndTimestamp": _iso(turn_end), "TraceId": _hex(32, i + 99),
            "SpandId": _hex(16, i + 99), "DataSourceId": DATA_SOURCE_PREFIX, "ExternalSourceId": ES})
        rows["AiAgentInteractionStep"].append({
            "id": _uid("step", i, "end"), "aiAgentInteractionId": end_id,
            "AiAgentInteractionStepType": "SESSION_END", "name": CLOSE_NAME[outcome],
            "inputValueText": "", "outputValueText": "", "startTimestamp": _iso(turn_end),
            "endTimestamp": _iso(turn_end), "prevStepId": "", "errorMessageText": "", "attributeText": "",
            "generation": "", "DataSourceId": DATA_SOURCE_PREFIX, "ExternalSourceId": ES})

        mid = _uid("moment", i)
        rows["AiAgentMoment"].append({
            "Id": mid, "AiAgentSessionId": sid, "AiAgentApiName": AGENT_API_NAME,
            "AiAgentVersionApiName": AGENT_VERSION, "RequestSummaryText": "User asked about %s." % intent,
            "ResponseSummaryText": ("Resolved." if not fails else "Could not complete the request."),
            "StartTimestamp": _iso(t0), "EndTimestamp": _iso(turn_end),
            "DataSourceId": DATA_SOURCE_PREFIX, "ExternalSourceId": ES})
        rows["AiAgentMomentInteraction"].append({
            "Id": _uid("momint", i), "AiAgentMomentId": mid, "AiAgentInteractionId": int_id,
            "StartTimestamp": _iso(t0), "DataSourceId": DATA_SOURCE_PREFIX, "ExternalSourceId": ES})
        for tag_id, assoc, val, reason in [
                (intent_tag[intent], intent_assoc, intent, "Categorized as " + intent),
                (q_tag[quality], quality_assoc, str(quality), "Quality score %d" % quality),
                (csat_tag, csat_assoc, CSAT_VALUE, "CSAT " + CSAT_VALUE)]:
            rows["AiAgentTagAssociation"].append({
                "Id": _uid("ta", i, val), "AiAgentSessionId": sid, "AiAgentMomentId": mid, "AiAgentTagId": tag_id,
                "AiAgentTagDefinitionAssociationId": assoc, "AssociationReasonText": reason,
                "ValueText": val, "SourceType": "PROMPT_TEMPLATE", "AiAgentSessionStartTimestamp": _iso(start),
                "CreatedDate": _iso(turn_end), "DataSourceId": DATA_SOURCE_PREFIX, "ExternalSourceId": ES})

        # Deflection / Abandonment score associations (Containment). Escalated get no score.
        if std and outcome != "escalated":
            dv = "5" if outcome == "deflected" else "2"
            av_row = "FALSE" if outcome == "deflected" else "TRUE"
            av_txt = av_row.lower()
            if dv in std["defl_val"]:
                rows["AiAgentTagAssociation"].append({
                    "Id": _uid("score", i, "defl"), "AiAgentSessionId": sid, "AiAgentMomentId": "",
                    "AiAgentTagId": std["defl_val"][dv], "AiAgentTagDefinitionAssociationId": std["defl_assoc"],
                    "AssociationReasonText": "Deflection score " + dv, "ValueText": dv, "SourceType": "PROMPT_TEMPLATE",
                    "AiAgentSessionStartTimestamp": _iso(start), "CreatedDate": _iso(turn_end),
                    "DataSourceId": DATA_SOURCE_PREFIX, "ExternalSourceId": ES})
            if av_row in std["aband_val"]:
                rows["AiAgentTagAssociation"].append({
                    "Id": _uid("score", i, "aband"), "AiAgentSessionId": sid, "AiAgentMomentId": "",
                    "AiAgentTagId": std["aband_val"][av_row], "AiAgentTagDefinitionAssociationId": std["aband_assoc"],
                    "AssociationReasonText": "Abandonment=" + av_txt, "ValueText": av_txt, "SourceType": "PROMPT_TEMPLATE",
                    "AiAgentSessionStartTimestamp": _iso(start), "CreatedDate": _iso(turn_end),
                    "DataSourceId": DATA_SOURCE_PREFIX, "ExternalSourceId": ES})

        for pid, role, obj_, part in [(agent_pid, "AGENT", "GenAiPlannerDefinition", planner),
                                      (user_pid, "USER", uobj, uid)]:
            rows["AiAgentSessionParticipant"].append({
                "Id": pid, "AiAgentSessionId": sid, "AiAgentApiName": AGENT_API_NAME,
                "AiAgentVersionApiName": AGENT_VERSION, "AiAgentTemplateApiName": "",
                "AiAgentType": "EinsteinServiceAgent", "AiAgentSessionParticipantRole": role,
                "ParticipantId": part, "ParticipantObject": obj_, "ParticipantAttributes": "{}",
                "StartTimestamp": _iso(start), "EndTimestamp": _iso(turn_end),
                "DataSourceId": DATA_SOURCE_PREFIX, "ExternalSourceId": ES})
        rows["AiAgentSession"].append({
            "Id": sid, "AiAgentChannelType": CHANNEL, "AiAgentSessionEndType": END_TYPE[outcome],
            "StartTimestamp": _iso(start), "EndTimestamp": _iso(turn_end), "IndividualId": "NOT_SET",
            "PreviousSessionId": "NOT_SET", "SessionOwnerObject": "NOT_SET", "VariableText": "NOT_SET",
            "DataSourceId": DATA_SOURCE_PREFIX, "ExternalSourceId": ES})

        # ── GenAI extension: Task Resolution (first TASKRES_TOTAL sessions) ──
        if i < TASKRES_TOTAL:
            cat = "FULLY_RESOLVED" if i < TASKRES_FULL else "UNRESOLVED"
            grows["GenAiResponseGeneration"].append({
                "Id": gen_id, "AiGatewayResponseId": _hex(24, i), "CreatedDate": _iso(turn_end)})
            grows["GenAiContentQualityCategory"].append({
                "Id": _uid("cqc", i), "AiContentQualityId": gen_id, "DetectionTypeId": "TaskResolution",
                "CategoryTypeId": cat, "CategoryValueNumber": "1" if cat == "FULLY_RESOLVED" else "0",
                "CreatedDate": _iso(turn_end)})

        # ── GenAI extension: CSAT feedback (first FEEDBACK_TOTAL interactions) ──
        if i < FEEDBACK_TOTAL:
            fb = "GOOD" if i < FEEDBACK_GOOD else "BAD"
            grows["GenAiFeedback"].append({
                "Id": _uid("fb", i), "FeedbackTypeId": fb, "GenerationGroupIdentifier": int_id,
                "CreatedDate": _iso(turn_end)})

    # ── prior-month (August) baseline: compact sessions feeding only the 4 AVA tiles ──
    sep_first = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    aug_first = (sep_first - _dt.timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    for j in range(AUG_TOTAL):
        outcome = AUG_OUTCOMES[j]
        sid = _uid("augsess", j)
        int_id = _uid("augint", j)
        end_id = _uid("augint", j, "end")
        agent_pid, user_pid = _uid("augpart", j, "a"), _uid("augpart", j, "u")
        uid = user_ids[j % len(user_ids)] if user_ids else "005000000000000AAA"
        uobj = "MessagingEndUser" if str(uid).startswith("0PA") else "User"
        # Aug 2..11 (mirrors Sep day-window; inside first 12 days so both "same MTD range"
        # and "full prior month" PriorPeriod interpretations capture it).
        start = aug_first + _dt.timedelta(days=1 + (j % 10), hours=(j % 12), minutes=(j * 7) % 60)
        turn_end = start + _dt.timedelta(seconds=AUG_SPAN_SECONDS)
        rows["AiAgentSession"].append({
            "Id": sid, "AiAgentChannelType": CHANNEL, "AiAgentSessionEndType": END_TYPE[outcome],
            "StartTimestamp": _iso(start), "EndTimestamp": _iso(turn_end), "IndividualId": "NOT_SET",
            "PreviousSessionId": "NOT_SET", "SessionOwnerObject": "NOT_SET", "VariableText": "NOT_SET",
            "DataSourceId": DATA_SOURCE_PREFIX, "ExternalSourceId": ES})
        for pid, role, obj_, part in [(agent_pid, "AGENT", "GenAiPlannerDefinition", planner),
                                      (user_pid, "USER", uobj, uid)]:
            rows["AiAgentSessionParticipant"].append({
                "Id": pid, "AiAgentSessionId": sid, "AiAgentApiName": AGENT_API_NAME,
                "AiAgentVersionApiName": AGENT_VERSION, "AiAgentTemplateApiName": "",
                "AiAgentType": "EinsteinServiceAgent", "AiAgentSessionParticipantRole": role,
                "ParticipantId": part, "ParticipantObject": obj_, "ParticipantAttributes": "{}",
                "StartTimestamp": _iso(start), "EndTimestamp": _iso(turn_end),
                "DataSourceId": DATA_SOURCE_PREFIX, "ExternalSourceId": ES})
        rows["AiAgentInteraction"].append({
            "Id": int_id, "AiAgentSessionId": sid, "TopicApiName": TOPIC[outcome], "AiAgentInteractionType": "TURN",
            "SessionOwnerId": uid, "SessionOwnerObject": uobj, "StartTimestamp": _iso(start),
            "EndTimestamp": _iso(turn_end), "TraceId": _hex(32, j + 500), "SpandId": _hex(16, j + 500),
            "DataSourceId": DATA_SOURCE_PREFIX, "ExternalSourceId": ES})
        rows["AiAgentInteraction"].append({
            "Id": end_id, "AiAgentSessionId": sid, "TopicApiName": "NOT_SET",
            "AiAgentInteractionType": "SESSION_END", "SessionOwnerId": uid, "SessionOwnerObject": uobj,
            "StartTimestamp": _iso(turn_end), "EndTimestamp": _iso(turn_end), "TraceId": _hex(32, j + 599),
            "SpandId": _hex(16, j + 599), "DataSourceId": DATA_SOURCE_PREFIX, "ExternalSourceId": ES})
        rows["AiAgentInteractionStep"].append({
            "id": _uid("augstep", j, "end"), "aiAgentInteractionId": end_id,
            "AiAgentInteractionStepType": "SESSION_END", "name": CLOSE_NAME[outcome],
            "inputValueText": "", "outputValueText": "", "startTimestamp": _iso(turn_end),
            "endTimestamp": _iso(turn_end), "prevStepId": "", "errorMessageText": "", "attributeText": "",
            "generation": "", "DataSourceId": DATA_SOURCE_PREFIX, "ExternalSourceId": ES})
        rows["AiAgentTagAssociation"].append({
            "Id": _uid("augta", j, "csat"), "AiAgentSessionId": sid, "AiAgentMomentId": "",
            "AiAgentTagId": csat_tag_aug, "AiAgentTagDefinitionAssociationId": csat_assoc,
            "AssociationReasonText": "CSAT " + AUG_CSAT_VALUE, "ValueText": AUG_CSAT_VALUE,
            "SourceType": "PROMPT_TEMPLATE", "AiAgentSessionStartTimestamp": _iso(start),
            "CreatedDate": _iso(turn_end), "DataSourceId": DATA_SOURCE_PREFIX, "ExternalSourceId": ES})

    return rows, grows


# ─── setup / push / verify / probe / teardown ────────────────────────────────
def to_csv(cols, rws):
    buf = io.StringIO(); w = csv.writer(buf); w.writerow(cols)
    for r in rws:
        w.writerow(["" if r.get(c) is None else r.get(c) for c in cols])
    return buf.getvalue().encode()


def _setup_objects(dc, objects, stream_base, category, event_time):
    import time
    for o in objects:
        obj = o["object"]; cname = stream_base[obj]
        ex = dc.find_ingest_connection(cname)
        if ex:
            cid, returned = ex.get("id"), ex.get("name", cname)
        else:
            _, returned, cid = dc.create_ingest_connection(cname, cname)
        fields = [(c, "DateTime" if c in o["datetimes"] else "Text") for c in o["cols"]]
        dc.put_schema(cid, obj, fields)
        stream, dlo = dc.find_stream_dlo(cname)
        if not dlo:
            dc.create_stream(cname, returned, obj, o["pk"], category=category[obj],
                             event_time_field=event_time.get(obj))
            for _ in range(6):
                time.sleep(4); stream, dlo = dc.find_stream_dlo(cname)
                if dlo:
                    break
        if dlo:
            dlo_dev = dlo if dlo.endswith("__dll") else dlo + "__dll"
            code, resp = dc.create_mapping(dlo_dev, o["dmo"], [(a + "__c", b) for a, b in o["map"]])
            ok = code in (200, 201) or "DUPLICATE" in json.dumps(resp)
            print("  %-34s map=%s" % (obj, "ok" if ok else ("FAIL %s %s" % (code, str(resp)[:200]))))
        else:
            print("  %-34s DLO not materialised yet — re-run setup" % obj)


def cmd_setup(dc, org, genai):
    print("STDM (11):")
    _setup_objects(dc, S.OBJECTS, S.STREAM_BASE, S.CATEGORY, S.EVENT_TIME)
    if genai:
        print("GenAI extension (3):")
        _setup_objects(dc, G.OBJECTS, G.STREAM_BASE, G.CATEGORY, G.EVENT_TIME)


def cmd_push(dc, org, genai):
    org_id, planner, users, _ = resolve_identities(org)
    std = resolve_std_scorers(dc)
    if not std:
        print("  WARN: std_*_Score_%s_V1 tag-defs not found — Deflection/Abandon read 0." % AGENT_API_NAME)
    now = _dt.datetime.now(_dt.timezone.utc)
    rows, grows = build(org_id, planner, users, std, now)
    for o in S.OBJECTS:
        rws = rows.get(o["object"], [])
        if rws:
            job = dc.ingest_csv(o["object"], S.STREAM_BASE[o["object"]], to_csv(o["cols"], rws))
            print("  pushed %-32s rows=%-4d job=%s" % (o["object"], len(rws), job))
    if genai:
        for o in G.OBJECTS:
            rws = grows.get(o["object"], [])
            if rws:
                job = dc.ingest_csv(o["object"], G.STREAM_BASE[o["object"]], to_csv(o["cols"], rws))
                print("  pushed %-32s rows=%-4d job=%s" % (o["object"], len(rws), job))
    print("push: submitted (rows land in DMOs within ~1-4 min).")


def _scalar(dc, sql):
    _, r = dc.query(sql)
    d = (r.get("data") if isinstance(r, dict) else None) or [[None]]
    return d[0][0]


def cmd_verify(dc, org):
    """Re-compute each target tile's exact numerator/denominator over the AVA-filtered,
    last-30-day scope (synthetic + real), so COUNTS can be tuned to the targets."""
    ava = ("SELECT COUNT(DISTINCT p.ssot__AiAgentSessionId__c) FROM ssot__AiAgentSessionParticipant__dlm p "
           "WHERE p.ssot__AiAgentSessionParticipantRole__c='AGENT' AND p.ssot__AiAgentApiName__c='AVA'")
    print("AVA unique sessions (denominator):", _scalar(dc, ava))
    print("  DMO row counts (synthetic only):")
    for dmo in ["ssot__AiAgentSession__dlm", "ssot__AiAgentInteraction__dlm",
                "ssot__AiAgentInteractionStep__dlm", "ssot__AiAgentTagAssociation__dlm",
                "GenAiFeedback_std__dlm", "GenAiContentQualityCategory_std__dlm", "GenAiResponseGeneration_std__dlm"]:
        col = "ssot__DataSourceId__c" if dmo.startswith("ssot__") else None
        sql = ("SELECT COUNT(*) FROM %s WHERE %s LIKE '%s%%'" % (dmo, col, DATA_SOURCE_PREFIX)
               if col else "SELECT COUNT(*) FROM %s" % dmo)
        print("   %-44s %s" % (dmo, _scalar(dc, sql)))
    print("  CSAT feedback GOOD / total:",
          _scalar(dc, "SELECT COUNT(*) FROM GenAiFeedback_std__dlm WHERE FeedbackTypeId__c='GOOD'"),
          "/", _scalar(dc, "SELECT COUNT(*) FROM GenAiFeedback_std__dlm"))
    print("  TaskResolution FULLY / total:",
          _scalar(dc, "SELECT COUNT(*) FROM GenAiContentQualityCategory_std__dlm WHERE DetectionTypeId__c='TaskResolution' AND CategoryTypeId__c='FULLY_RESOLVED'"),
          "/", _scalar(dc, "SELECT COUNT(*) FROM GenAiContentQualityCategory_std__dlm WHERE DetectionTypeId__c='TaskResolution'"))
    print("  Avg session duration (s):",
          _scalar(dc, "SELECT AVG(DATEDIFF(second, ssot__StartTimestamp__c, ssot__EndTimestamp__c)) "
                      "FROM ssot__AiAgentInteraction__dlm WHERE ssot__AiAgentInteractionType__c='TURN' "
                      "AND ssot__DataSourceId__c LIKE '%s%%'" % DATA_SOURCE_PREFIX))


def cmd_probe(dc, org):
    """Dump target-DMO metadata (fields + category) to finalise schema_genai before setup."""
    for dmo in ["GenAiResponseGeneration_std__dlm", "GenAiContentQualityCategory_std__dlm", "GenAiFeedback_std__dlm"]:
        code, r = dc.dmo_metadata(dmo)
        print("\n=== %s (http %s) ===" % (dmo, code))
        md = (r.get("metadata") if isinstance(r, dict) else None) or []
        if md:
            print("  category:", md[0].get("category"))
            for f in md[0].get("fields", []):
                print("   %-40s %s" % (f.get("name"), f.get("type")))
        else:
            print("  ", str(r)[:400])


def cmd_teardown(dc, org):
    import time
    for o in reversed(S.OBJECTS + G.OBJECTS):
        base = (S.STREAM_BASE if o in S.OBJECTS else G.STREAM_BASE)[o["object"]]
        stream, _ = dc.find_stream_dlo(base)
        if stream:
            dc.delete_stream(stream); print("  stream del %s" % o["object"])
    time.sleep(20)
    for o in reversed(S.OBJECTS + G.OBJECTS):
        base = (S.STREAM_BASE if o in S.OBJECTS else G.STREAM_BASE)[o["object"]]
        c = dc.find_ingest_connection(base)
        if c and c.get("id"):
            dc.delete_connection(c["id"]); print("  conn del %s" % o["object"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["setup", "push", "verify", "probe", "teardown"])
    ap.add_argument("--target-org", default="vivint_observability")
    ap.add_argument("--no-genai", action="store_true", help="STDM only (skip CSAT/Resolution extension)")
    a = ap.parse_args()
    dc = DC()
    print("[dc] core=%s cdp=%s" % (dc.core_url, dc.cdp_url))
    genai = not a.no_genai
    {"setup": lambda: cmd_setup(dc, a.target_org, genai),
     "push": lambda: cmd_push(dc, a.target_org, genai),
     "verify": lambda: cmd_verify(dc, a.target_org),
     "probe": lambda: cmd_probe(dc, a.target_org),
     "teardown": lambda: cmd_teardown(dc, a.target_org)}[a.command]()


if __name__ == "__main__":
    main()
