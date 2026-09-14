"""Split synthetic (AVAObs) vs real sessions for the 713-formula inputs."""
import json
from dc_client import DC
dc = DC()
def rows(sql):
    st, r = dc.query(sql)
    if st != 200:
        print("ERR", st, str(r)[:200]); return []
    return r.get("data", [])

# per-session: is it synthetic? does it have transferred/action SESSION_END? interaction span
sql = """
WITH sess AS (
  SELECT s.ssot__Id__c AS sid,
    CASE WHEN s.ssot__DataSourceId__c LIKE 'AVAObs%' THEN 'syn' ELSE 'real' END AS kind
  FROM ssot__AiAgentSession__dlm s
),
ends AS (
  SELECT i.ssot__AiAgentSessionId__c AS sid,
    MAX(CASE WHEN st.ssot__AiAgentInteractionStepType__c='SESSION_END' AND st.ssot__Name__c='CLOSED_TRANSFERRED' THEN 1 ELSE 0 END) AS tr,
    MAX(CASE WHEN st.ssot__AiAgentInteractionStepType__c='SESSION_END' AND st.ssot__Name__c='CLOSED_ACTION' THEN 1 ELSE 0 END) AS ac
  FROM ssot__AiAgentInteractionStep__dlm st
  JOIN ssot__AiAgentInteraction__dlm i ON st.ssot__AiAgentInteractionId__c=i.ssot__Id__c
  GROUP BY i.ssot__AiAgentSessionId__c
),
span AS (
  SELECT i.ssot__AiAgentSessionId__c AS sid,
    date_diff('second', CAST(MIN(i.ssot__StartTimestamp__c) AS TIMESTAMP), CAST(MAX(i.ssot__EndTimestamp__c) AS TIMESTAMP)) AS sp
  FROM ssot__AiAgentInteraction__dlm i GROUP BY i.ssot__AiAgentSessionId__c
)
SELECT sess.kind,
  COUNT(*) AS n,
  SUM(COALESCE(ends.tr,0)) AS transferred,
  SUM(COALESCE(ends.ac,0)) AS action,
  AVG(COALESCE(span.sp,0)) AS avg_span,
  SUM(COALESCE(span.sp,0)) AS sum_span
FROM sess LEFT JOIN ends ON ends.sid=sess.sid LEFT JOIN span ON span.sid=sess.sid
GROUP BY sess.kind
"""
print("kind | n | transferred | action | avg_span | sum_span")
for r in rows(sql):
    print(r)
