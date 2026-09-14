"""
EXTENSION objects beyond the 11 STDM sources — the GenAI *_std__dlm DMOs that drive
two of AVA's four target tiles. These are NOT in the reference impl; derived from the
sfm_Agentforce_Analytics_Foundations semantic model:

  Customer Satisfaction (CSAT %) = Positive/(Positive+Negative) user feedback, at the
     INTERACTION level:  User_Feedback_Status_clc reads GenAiFeedback_std__dlm
     (FeedbackTypeId__c GOOD/BAD, latest by CreatedDate__c), joined to the interaction by
     GenerationGroupIdentifier__c == AI_Agent_Interaction.Id.

  Customer Resolution Rate (%) = Task_Resolution_Rate_clc =
     COUNTD(sessions where TaskResolution category == 'FULLY_RESOLVED')
     / COUNTD(sessions with ANY TaskResolution category).
     Join chain: AiAgentInteractionStep.ssot__GenerationId__c == GenAiResponseGeneration.Id__c
     == GenAiContentQualityCategory.AiContentQualityId__c, with DetectionTypeId__c='TaskResolution'
     and CategoryTypeId__c in {FULLY_RESOLVED, UNRESOLVED}.

⚠ CATEGORY + target field api names below are best-guess and MUST be validated with
DC.dmo_metadata(dmo).metadata[0].fields[].name before/at setup (probe_genai.py). std
DMOs may also reject custom IngestApi DLO mappings entirely — validate first.
"""
DT_TEXT, DT_DATETIME = "Text", "DateTime"


def _fields(cols, datetimes):
    return [(c, DT_DATETIME if c in datetimes else DT_TEXT) for c in cols]


def schema_fields(o):
    return _fields(o["cols"], o["datetimes"])


PREFIX = "AVAObs"

_STREAM_SUFFIX = {
    "GenAiResponseGeneration": "Gen",
    "GenAiContentQualityCategory": "CQC",
    "GenAiFeedback": "Fb",
}
STREAM_BASE = {obj: "%s_%s" % (PREFIX, sfx) for obj, sfx in _STREAM_SUFFIX.items()}
# Probe (2026-09-11) confirmed all three target DMOs are category Engagement, not the
# Profile/Related originally guessed. DLO category MUST equal DMO category or the mapping
# 400s; each Engagement object also needs a DateTime event-time field (CreatedDate__c, verified present).
CATEGORY = {
    "GenAiResponseGeneration": "Engagement",
    "GenAiContentQualityCategory": "Engagement",
    "GenAiFeedback": "Engagement",
}
EVENT_TIME = {
    "GenAiResponseGeneration": "CreatedDate",
    "GenAiContentQualityCategory": "CreatedDate",
    "GenAiFeedback": "CreatedDate",
}

OBJECTS = [
    {"object": "GenAiResponseGeneration", "pk": "Id", "dmo": "GenAiResponseGeneration_std__dlm",
     "cols": ["Id", "AiGatewayResponseId", "CreatedDate"],
     "datetimes": ["CreatedDate"],
     "map": [("Id", "Id__c"), ("AiGatewayResponseId", "AiGatewayResponseId__c"),
             ("CreatedDate", "CreatedDate__c")]},
    {"object": "GenAiContentQualityCategory", "pk": "Id", "dmo": "GenAiContentQualityCategory_std__dlm",
     # Parent (AiContentQualityId__c) == the generation Id above; the detector + category
     # are the two literals Task_Resolution_Status_clc reads.
     "cols": ["Id", "AiContentQualityId", "DetectionTypeId", "CategoryTypeId",
              "CategoryValueNumber", "CreatedDate"],
     "datetimes": ["CreatedDate"],
     "map": [("Id", "Id__c"), ("AiContentQualityId", "AiContentQualityId__c"),
             ("DetectionTypeId", "DetectionTypeId__c"), ("CategoryTypeId", "CategoryTypeId__c"),
             ("CategoryValueNumber", "CategoryValueNumber__c"), ("CreatedDate", "CreatedDate__c")]},
    {"object": "GenAiFeedback", "pk": "Id", "dmo": "GenAiFeedback_std__dlm",
     # GenerationGroupIdentifier__c == AI_Agent_Interaction.Id links a rating to a turn.
     "cols": ["Id", "FeedbackTypeId", "GenerationGroupIdentifier", "CreatedDate"],
     "datetimes": ["CreatedDate"],
     "map": [("Id", "Id__c"), ("FeedbackTypeId", "FeedbackTypeId__c"),
             ("GenerationGroupIdentifier", "GenerationGroupIdentifier__c"),
             ("CreatedDate", "CreatedDate__c")]},
]
