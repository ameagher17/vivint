"""
STDM Ingestion-API source definitions (Path 5) — the 11 canonical objects.

For each object:
  * object    — IngestApi schema object name (== the generator CSV name == sourceName)
  * pk        — primary key field
  * cols      — CSV columns (== DLO schema field names)
  * datetimes — which cols are DateTime-typed (Engagement objects need one as event time)
  * category  — DLO category; MUST equal the target DMO's category or the mapping 400s
  * dmo       — the canonical ssot__AiAgent*__dlm this DLO maps to
  * map       — [(dloField, targetField)] DLO->DMO field pairs

Field maps carry hard-won corrections (TelemetryTraceId/SpanId, ParticipantAttributeText,
PrevStepId, dropped AgentId, omitted Boolean IsActive, and the un-prefixed ValueText/
SourceType extension fields on TagAssociation). Categories + target field api names are
consistent across STDM orgs; if a mapping 400s in a new org, re-verify the target field
names with DC.dmo_metadata(dmo) -> .metadata[0].fields[].name.

Every object also maps Id -> ssot__Id__c AND ExternalSourceId -> ssot__ExternalSourceId__c
(the latter is the Analytics-tab render gate).
"""

# Change this per demo. Connection name (== sourceName) stays the full object name;
# only the short stream base uses the prefix (the materialized stream name
# "<base>_<event>_<hash>" overflows the platform limit for long object names).
PREFIX = "AVAObs"

DT_TEXT, DT_DATETIME = "Text", "DateTime"


def _fields(cols, datetimes):
    return [(c, DT_DATETIME if c in datetimes else DT_TEXT) for c in cols]


def schema_fields(o):
    return _fields(o["cols"], o["datetimes"])


# NOTE: this org's ssot__AiAgentSession__dlm and ssot__AiAgentInteractionStep__dlm are
# category Engagement (verified via dmo_metadata 2026-09-11), NOT Profile as the reference
# impl assumed. DLO category must equal DMO category or the mapping 400s.
CATEGORY = {
    "AiAgentSession": "Engagement",
    "AiAgentSessionParticipant": "Engagement",
    "AiAgentInteraction": "Engagement",
    "AiAgentInteractionMessage": "Engagement",
    "AiAgentInteractionStep": "Engagement",
    "AiAgentMoment": "Engagement",
    "AiAgentMomentInteraction": "Engagement",
    "AiAgentTagDefinition": "Related",
    "AiAgentTagDefinitionAssociation": "Related",
    "AiAgentTag": "Related",
    "AiAgentTagAssociation": "Engagement",
}
EVENT_TIME = {   # only for Engagement-category objects
    "AiAgentSession": "StartTimestamp",
    "AiAgentInteractionStep": "startTimestamp",
    "AiAgentSessionParticipant": "StartTimestamp",
    "AiAgentInteraction": "StartTimestamp",
    "AiAgentInteractionMessage": "MessageSentTimestamp",
    "AiAgentMoment": "StartTimestamp",
    "AiAgentMomentInteraction": "StartTimestamp",
    "AiAgentTagAssociation": "CreatedDate",
}
_STREAM_SUFFIX = {
    "AiAgentSession": "Session", "AiAgentSessionParticipant": "SessPart",
    "AiAgentInteraction": "Interaction", "AiAgentInteractionMessage": "IntMsg",
    "AiAgentInteractionStep": "IntStep", "AiAgentMoment": "Moment",
    "AiAgentMomentInteraction": "MomInt", "AiAgentTagDefinition": "TagDef",
    "AiAgentTagDefinitionAssociation": "TagDefAssoc", "AiAgentTag": "Tag",
    "AiAgentTagAssociation": "TagAssoc",
}
STREAM_BASE = {obj: "%s_%s" % (PREFIX, sfx) for obj, sfx in _STREAM_SUFFIX.items()}

OBJECTS = [
    {"object": "AiAgentSession", "pk": "Id", "dmo": "ssot__AiAgentSession__dlm",
     "cols": ["Id", "AiAgentChannelType", "AiAgentSessionEndType", "StartTimestamp",
              "EndTimestamp", "IndividualId", "PreviousSessionId", "SessionOwnerObject",
              "VariableText", "DataSourceId", "ExternalSourceId"],
     "datetimes": ["StartTimestamp", "EndTimestamp"],
     "map": [("Id", "ssot__Id__c"), ("ExternalSourceId", "ssot__ExternalSourceId__c"),
             ("AiAgentChannelType", "ssot__AiAgentChannelType__c"),
             ("AiAgentSessionEndType", "ssot__AiAgentSessionEndType__c"),
             ("StartTimestamp", "ssot__StartTimestamp__c"), ("EndTimestamp", "ssot__EndTimestamp__c"),
             ("IndividualId", "ssot__IndividualId__c"), ("PreviousSessionId", "ssot__PreviousSessionId__c"),
             ("SessionOwnerObject", "ssot__SessionOwnerObject__c"), ("VariableText", "ssot__VariableText__c")]},
    {"object": "AiAgentSessionParticipant", "pk": "Id", "dmo": "ssot__AiAgentSessionParticipant__dlm",
     "cols": ["Id", "AiAgentSessionId", "AiAgentApiName", "AiAgentVersionApiName",
              "AiAgentTemplateApiName", "AiAgentType", "AiAgentSessionParticipantRole",
              "ParticipantId", "ParticipantObject", "ParticipantAttributes",
              "StartTimestamp", "EndTimestamp", "DataSourceId", "ExternalSourceId"],
     "datetimes": ["StartTimestamp", "EndTimestamp"],
     "map": [("Id", "ssot__Id__c"), ("ExternalSourceId", "ssot__ExternalSourceId__c"),
             ("AiAgentSessionId", "ssot__AiAgentSessionId__c"), ("AiAgentApiName", "ssot__AiAgentApiName__c"),
             ("AiAgentVersionApiName", "ssot__AiAgentVersionApiName__c"),
             ("AiAgentTemplateApiName", "ssot__AiAgentTemplateApiName__c"), ("AiAgentType", "ssot__AiAgentType__c"),
             ("AiAgentSessionParticipantRole", "ssot__AiAgentSessionParticipantRole__c"),
             ("ParticipantId", "ssot__ParticipantId__c"), ("ParticipantObject", "ssot__ParticipantObject__c"),
             ("ParticipantAttributes", "ssot__ParticipantAttributeText__c"),
             ("StartTimestamp", "ssot__StartTimestamp__c"), ("EndTimestamp", "ssot__EndTimestamp__c")]},
    {"object": "AiAgentInteraction", "pk": "Id", "dmo": "ssot__AiAgentInteraction__dlm",
     "cols": ["Id", "AiAgentSessionId", "TopicApiName", "AiAgentInteractionType",
              "SessionOwnerId", "SessionOwnerObject", "StartTimestamp", "EndTimestamp",
              "TraceId", "SpandId", "DataSourceId", "ExternalSourceId"],
     "datetimes": ["StartTimestamp", "EndTimestamp"],
     "map": [("Id", "ssot__Id__c"), ("ExternalSourceId", "ssot__ExternalSourceId__c"),
             ("AiAgentSessionId", "ssot__AiAgentSessionId__c"), ("TopicApiName", "ssot__TopicApiName__c"),
             ("AiAgentInteractionType", "ssot__AiAgentInteractionType__c"),
             ("SessionOwnerId", "ssot__SessionOwnerId__c"), ("SessionOwnerObject", "ssot__SessionOwnerObject__c"),
             ("StartTimestamp", "ssot__StartTimestamp__c"), ("EndTimestamp", "ssot__EndTimestamp__c"),
             ("TraceId", "ssot__TelemetryTraceId__c"), ("SpandId", "ssot__TelemetryTraceSpanId__c")]},
    {"object": "AiAgentInteractionMessage", "pk": "Id", "dmo": "ssot__AiAgentInteractionMessage__dlm",
     "cols": ["Id", "AiAgentSessionId", "AiAgentInteractionId", "AiAgentSessionParticipantId",
              "AiAgentInteractionMessageType", "AiAgentInteractionMsgContentType",
              "ContentText", "MessageSentTimestamp", "DataSourceId", "ExternalSourceId"],
     "datetimes": ["MessageSentTimestamp"],
     "map": [("Id", "ssot__Id__c"), ("ExternalSourceId", "ssot__ExternalSourceId__c"),
             ("AiAgentSessionId", "ssot__AiAgentSessionId__c"), ("AiAgentInteractionId", "ssot__AiAgentInteractionId__c"),
             ("AiAgentSessionParticipantId", "ssot__AiAgentSessionParticipantId__c"),
             ("AiAgentInteractionMessageType", "ssot__AiAgentInteractionMessageType__c"),
             ("AiAgentInteractionMsgContentType", "ssot__AiAgentInteractionMsgContentType__c"),
             ("ContentText", "ssot__ContentText__c"), ("MessageSentTimestamp", "ssot__MessageSentTimestamp__c")]},
    {"object": "AiAgentInteractionStep", "pk": "id", "dmo": "ssot__AiAgentInteractionStep__dlm",
     # "generation" -> ssot__GenerationId__c bridges Task-Resolution: Step.Generation ==
     # Ai_Response_Generation.Generation_Id == ContentQualityCategory.Parent (see schema_genai).
     "cols": ["id", "aiAgentInteractionId", "AiAgentInteractionStepType", "name",
              "inputValueText", "outputValueText", "startTimestamp", "endTimestamp",
              "prevStepId", "errorMessageText", "attributeText", "generation",
              "DataSourceId", "ExternalSourceId"],
     "datetimes": ["startTimestamp", "endTimestamp"],
     "map": [("id", "ssot__Id__c"), ("ExternalSourceId", "ssot__ExternalSourceId__c"),
             ("aiAgentInteractionId", "ssot__AiAgentInteractionId__c"),
             ("AiAgentInteractionStepType", "ssot__AiAgentInteractionStepType__c"), ("name", "ssot__Name__c"),
             ("inputValueText", "ssot__InputValueText__c"), ("outputValueText", "ssot__OutputValueText__c"),
             ("startTimestamp", "ssot__StartTimestamp__c"), ("endTimestamp", "ssot__EndTimestamp__c"),
             ("prevStepId", "ssot__PrevStepId__c"), ("errorMessageText", "ssot__ErrorMessageText__c"),
             ("attributeText", "ssot__AttributeText__c"), ("generation", "ssot__GenerationId__c")]},
    {"object": "AiAgentMoment", "pk": "Id", "dmo": "ssot__AiAgentMoment__dlm",
     "cols": ["Id", "AiAgentSessionId", "AiAgentApiName", "AiAgentVersionApiName",
              "RequestSummaryText", "ResponseSummaryText", "StartTimestamp",
              "EndTimestamp", "DataSourceId", "ExternalSourceId"],
     "datetimes": ["StartTimestamp", "EndTimestamp"],
     "map": [("Id", "ssot__Id__c"), ("ExternalSourceId", "ssot__ExternalSourceId__c"),
             ("AiAgentSessionId", "ssot__AiAgentSessionId__c"), ("AiAgentApiName", "ssot__AiAgentApiName__c"),
             ("AiAgentVersionApiName", "ssot__AiAgentVersionApiName__c"),
             ("RequestSummaryText", "ssot__RequestSummaryText__c"), ("ResponseSummaryText", "ssot__ResponseSummaryText__c"),
             ("StartTimestamp", "ssot__StartTimestamp__c"), ("EndTimestamp", "ssot__EndTimestamp__c")]},
    {"object": "AiAgentMomentInteraction", "pk": "Id", "dmo": "ssot__AiAgentMomentInteraction__dlm",
     "cols": ["Id", "AiAgentMomentId", "AiAgentInteractionId", "StartTimestamp",
              "DataSourceId", "ExternalSourceId"],
     "datetimes": ["StartTimestamp"],
     "map": [("Id", "ssot__Id__c"), ("ExternalSourceId", "ssot__ExternalSourceId__c"),
             ("AiAgentMomentId", "ssot__AiAgentMomentId__c"), ("AiAgentInteractionId", "ssot__AiAgentInteractionId__c"),
             ("StartTimestamp", "ssot__StartTimestamp__c")]},
    {"object": "AiAgentTagDefinition", "pk": "Id", "dmo": "ssot__AiAgentTagDefinition__dlm",
     "cols": ["Id", "Name", "DeveloperName", "DataType", "SourceType", "Status",
              "Description", "CreatedDate", "DataSourceId", "ExternalSourceId"],
     "datetimes": ["CreatedDate"],
     "map": [("Id", "ssot__Id__c"), ("ExternalSourceId", "ssot__ExternalSourceId__c"),
             ("Name", "ssot__Name__c"), ("DeveloperName", "ssot__DeveloperName__c"),
             ("DataType", "ssot__DataType__c"), ("SourceType", "ssot__SourceType__c"),
             ("Status", "ssot__Status__c"), ("Description", "ssot__Description__c"),
             ("CreatedDate", "ssot__CreatedDate__c")]},
    {"object": "AiAgentTagDefinitionAssociation", "pk": "Id", "dmo": "ssot__AiAgentTagDefinitionAssociation__dlm",
     # IsActive omitted — ssot__IsActive__c is Boolean, IngestApi carries Text (400s); not needed to render.
     "cols": ["Id", "AiAgentApiName", "AiAgentTagDefinitionId", "IsActive",
              "CreatedDate", "DataSourceId", "ExternalSourceId"],
     "datetimes": ["CreatedDate"],
     "map": [("Id", "ssot__Id__c"), ("ExternalSourceId", "ssot__ExternalSourceId__c"),
             ("AiAgentApiName", "ssot__AiAgentApiName__c"), ("AiAgentTagDefinitionId", "ssot__AiAgentTagDefinitionId__c"),
             ("CreatedDate", "ssot__CreatedDate__c")]},
    {"object": "AiAgentTag", "pk": "Id", "dmo": "ssot__AiAgentTag__dlm",
     "cols": ["Id", "AiAgentTagDefinitionId", "Value", "Description", "IsActive",
              "CreatedDate", "DataSourceId", "ExternalSourceId"],
     "datetimes": ["CreatedDate"],
     "map": [("Id", "ssot__Id__c"), ("ExternalSourceId", "ssot__ExternalSourceId__c"),
             ("AiAgentTagDefinitionId", "ssot__AiAgentTagDefinitionId__c"), ("Value", "ssot__Value__c"),
             ("Description", "ssot__Description__c"), ("CreatedDate", "ssot__CreatedDate__c")]},
    {"object": "AiAgentTagAssociation", "pk": "Id", "dmo": "ssot__AiAgentTagAssociation__dlm",
     # ValueText + SourceType mirror the real analyzer output: the tag-driven KPIs read
     # the denormalized ValueText__c (score value) + SourceType__c='PROMPT_TEMPLATE',
     # NOT the joined tag-row value. These two (+ AiAgentSessionStartTimestamp) map to
     # targets WITHOUT the ssot__ prefix (extension fields). If the mapping is create-only
     # and already has dependents, add these two field pairs by hand in the Data Cloud UI.
     "cols": ["Id", "AiAgentSessionId", "AiAgentMomentId", "AiAgentTagId",
              "AiAgentTagDefinitionAssociationId", "AssociationReasonText", "ValueText",
              "SourceType", "AiAgentSessionStartTimestamp", "CreatedDate", "DataSourceId", "ExternalSourceId"],
     "datetimes": ["AiAgentSessionStartTimestamp", "CreatedDate"],
     "map": [("Id", "ssot__Id__c"), ("ExternalSourceId", "ssot__ExternalSourceId__c"),
             ("AiAgentSessionId", "ssot__AiAgentSessionId__c"), ("AiAgentMomentId", "ssot__AiAgentMomentId__c"),
             ("AiAgentTagId", "ssot__AiAgentTagId__c"),
             ("AiAgentTagDefinitionAssociationId", "ssot__AiAgentTagDefinitionAssociationId__c"),
             ("AssociationReasonText", "ssot__AssociationReasonText__c"),
             ("ValueText", "ValueText__c"), ("SourceType", "SourceType__c"),
             ("AiAgentSessionStartTimestamp", "AiAgentSessionStartTimestamp__c"),
             ("CreatedDate", "ssot__CreatedDate__c")]},
]
