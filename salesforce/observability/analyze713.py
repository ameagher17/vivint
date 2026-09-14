"""Measure current live values of the 713 AVA-dashboard formulas against seeded DMOs."""
import json
from dc_client import DC
dc = DC()

def q(sql):
    st, r = dc.query(sql)
    if st != 200:
        print("QUERY %s: %s" % (st, str(r)[:300])); return None
    return r.get("data", [])

# session-level SESSION_END outcome presence (step -> interaction -> session)
sql_sess = """
SELECT
  COUNT(DISTINCT s.ssot__Id__c) AS total,
  COUNT(DISTINCT CASE WHEN se.transferred=1 THEN s.ssot__Id__c END) AS transferred,
  COUNT(DISTINCT CASE WHEN se.action=1 THEN s.ssot__Id__c END) AS action
FROM ssot__AiAgentSession__dlm s
LEFT JOIN (
  SELECT i.ssot__AiAgentSessionId__c AS sid,
    MAX(CASE WHEN st.ssot__AiAgentInteractionStepType__c='SESSION_END' AND st.ssot__Name__c='CLOSED_TRANSFERRED' THEN 1 ELSE 0 END) AS transferred,
    MAX(CASE WHEN st.ssot__AiAgentInteractionStepType__c='SESSION_END' AND st.ssot__Name__c='CLOSED_ACTION' THEN 1 ELSE 0 END) AS action
  FROM ssot__AiAgentInteractionStep__dlm st
  JOIN ssot__AiAgentInteraction__dlm i ON st.ssot__AiAgentInteractionId__c = i.ssot__Id__c
  GROUP BY i.ssot__AiAgentSessionId__c
) se ON se.sid = s.ssot__Id__c
"""
r = q(sql_sess)
if r:
    row = r[0]
    total = float(row[0]); tr = float(row[1]); ac = float(row[2])
    contained = total - tr
    print("SESSIONS total=%d transferred=%d action=%d" % (total, tr, ac))
    print("  Containment(713) = non-transferred/total = %.4f (%.2f%%)  [target 20.04%%]" % ((contained/total), 100*contained/total))
    print("  Resolution(713)  = action/non-transferred = %.4f (%.2f%%)  [target 84.00%%]" % ((ac/contained if contained else 0), 100*ac/contained if contained else 0))

# effort: avg over sessions of (max interaction end - min interaction start) seconds
sql_eff = """
SELECT AVG(span) AS avg_span, COUNT(*) AS n FROM (
  SELECT i.ssot__AiAgentSessionId__c AS sid,
    date_diff('second', CAST(MIN(i.ssot__StartTimestamp__c) AS TIMESTAMP), CAST(MAX(i.ssot__EndTimestamp__c) AS TIMESTAMP)) AS span
  FROM ssot__AiAgentInteraction__dlm i
  GROUP BY i.ssot__AiAgentSessionId__c
) t
"""
r = q(sql_eff)
if r:
    print("EFFORT avg interaction span = %s sec over %s sessions  [target 165s]" % (r[0][0], r[0][1]))

# CSAT tags: numeric tag values > 10
sql_csat = """
SELECT COUNT(*) AS n, AVG(v) AS avgv FROM (
  SELECT TRY_CAST(ssot__Value__c AS DOUBLE) AS v FROM ssot__AiAgentTag__dlm
) t WHERE v > 10
"""
r = q(sql_csat)
if r:
    print("CSAT numeric tags(value>10): n=%s avg=%s  [need avg 91 => CSAT 91%%]" % (r[0][0], r[0][1]))
