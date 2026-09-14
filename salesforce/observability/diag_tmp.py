import dc_client as dc
c=dc.DC()
def run(sql):
    b=c.query(sql)[1]; return b.get("data") if isinstance(b,dict) and "data" in b else b
sql="""
SELECT SUBSTRING(CAST(ai.ssot__StartTimestamp__c AS VARCHAR),1,7) mo,
       COUNT(*) turns, AVG(date_diff('second',ai.ssot__StartTimestamp__c,ai.ssot__EndTimestamp__c)) avg_span
FROM ssot__AiAgentInteraction__dlm ai
JOIN ssot__AiAgentSessionParticipant__dlm p ON p.ssot__AiAgentSessionId__c=ai.ssot__AiAgentSessionId__c AND p.ssot__AiAgentSessionParticipantRole__c='AGENT'
WHERE ai.ssot__AiAgentInteractionType__c='TURN' AND p.ssot__AiAgentApiName__c='AVA'
GROUP BY 1 ORDER BY 1
"""
for row in (run(sql) or []): print(row)
