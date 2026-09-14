/**
 * FirmwareRebootDemo
 * ------------------
 * DEMO-ONLY seeder that stages a burst of "reboot my Customer Panel to get the
 * latest firmware update" sessions where AVA can only ADVISE the customer (walk
 * them through it) but cannot perform the reboot/update itself — so the session
 * ends CONTAINED but UNRESOLVED. This drops the agent's Contact Resolution Rate
 * (resolved / contained) from its ~80% baseline toward ~60%, on demand.
 *
 * Each session also carries a CSAT tag of 3 (a mildly frustrated customer whose
 * problem wasn't actually fixed), so Customer Satisfaction dips alongside
 * resolution — a correlated, believable story.
 *
 * Scope: EVERY row is Demo_Identifier__c = 'FIRMWARE_REBOOT_DEMO'. wipe() deletes
 * ONLY that identifier, so it can never touch the base analytics seed
 * (AVA_ANALYTICS_SEED), the escalation demo (ESCALATION_ALERT_DEMO), Southwest
 * (SW_AI_ASSISTANT), or any other seed — no matter how many times the Reset
 * button is clicked. There is no unfiltered delete anywhere in this class.
 *
 * Sizing (from live DMO, 2026-09-09): agent had resolved=986 / contained=1260 =
 * 78.25%. To reach 60%: 986/(1260+U)=0.60 -> U~=383. DEFAULT_COUNT=380. Tune with
 * spikeN(count) and re-refresh: new_rate = 986 / (1260 + count).
 *
 * IMPORTANT: DMO is Path-4 / manual refresh. spike() only stages SDO rows; the
 * dashboard moves only after a Data Cloud Full Refresh. Dates are clustered in the
 * last ~14 days so the change shows in the card's rolling 30-day window.
 */
public with sharing class FirmwareRebootDemo {

    public static final String DEMO_TAG          = 'FIRMWARE_REBOOT_DEMO';
    public static final String AGENT_API_NAME    = 'AVA';
    public static final String AGENT_LABEL       = 'AVA (Vivint Automated Assistant)';
    public static final String TEMPLATE_API_NAME = 'QuickASA__QuickASA';
    public static final String CHANNEL_TYPE      = 'PSTN';
    public static final String STEP_UNRESOLVED   = 'end_session'; // contained, not resolved
    public static final String END_TYPE          = 'deflected';
    public static final String CSAT_DEF_ID        = 'Customer_Satisfaction_Score';
    private static final String NOT_SET          = 'NOT_SET';

    private static final Integer DEFAULT_COUNT = 380;

    @AuraEnabled
    public static String spike() { return spikeN(DEFAULT_COUNT); }

    @AuraEnabled
    public static String spikeN(Integer count) {
        if (count == null || count <= 0) count = DEFAULT_COUNT;
        if (count > 500) count = 500; // one sync transaction

        String versionApiName     = resolveVersionApiName();
        String agentParticipantId = versionApiName == null ? AGENT_API_NAME : versionApiName;

        List<SDO_Analytics_AIAgentSession_v2__c>          sessions     = new List<SDO_Analytics_AIAgentSession_v2__c>();
        List<SDO_Analytics_AIAgentSessionParticipa_v2__c> participants = new List<SDO_Analytics_AIAgentSessionParticipa_v2__c>();
        List<SDO_Analytics_AiAgentInteraction_v2__c>      interactions = new List<SDO_Analytics_AiAgentInteraction_v2__c>();
        List<SDO_Analytics_AIAgentInteractionStep_v2__c>  steps        = new List<SDO_Analytics_AIAgentInteractionStep_v2__c>();
        List<SDO_Analytics_AIAgentTag_v2__c>              tags         = new List<SDO_Analytics_AIAgentTag_v2__c>();
        List<SDO_Analytics_AIAgentTagAssociation_v2__c>   assocs       = new List<SDO_Analytics_AIAgentTagAssociation_v2__c>();

        for (Integer i = 0; i < count; i++) {
            String sUuid   = uuid();
            String iUuid   = uuid();
            String tagUuid = uuid();

            // Spread across the last ~14 days so it lands in the card's 30-day window.
            Integer dayOff    = -Math.mod(i, 14);
            Integer startSecs = 8 * 3600 + Math.mod(i * 53, 9 * 3600);   // 08:00..17:00
            Integer durSecs   = 7 * 60 + (Math.mod(i, 5) - 2) * 20;      // ~7 min +/- spread
            if (durSecs < 60) durSecs = 60;

            sessions.add(new SDO_Analytics_AIAgentSession_v2__c(
                External_ID__c = sUuid, Name = AGENT_LABEL.left(80),
                Demo_Identifier__c = DEMO_TAG,
                AI_Agent_Channel_Type__c = CHANNEL_TYPE,
                AI_Agent_Session_End_Type__c = END_TYPE,
                Start_Days__c = dayOff, Start_Time__c = hhmmss(startSecs),
                End_Timestamp__c = DateTime.now().addDays(dayOff),
                Individual__c = NOT_SET, Session_Owner_Object__c = NOT_SET,
                Variable__c = NOT_SET, Previous_Session_Id__c = NOT_SET));

            participants.add(new SDO_Analytics_AIAgentSessionParticipa_v2__c(
                External_ID__c = uuid(), Name = 'AGENT'.left(80),
                Demo_Identifier__c = DEMO_TAG,
                AI_Agent_Session__c = sUuid,
                AI_Agent_Session_Participant_Role__c = 'AGENT',
                AI_Agent_Api_Name__c = AGENT_API_NAME,
                AI_Agent_Template_Api_Name__c = TEMPLATE_API_NAME,
                AI_Agent_Version_Api_Name__c = versionApiName,
                AI_Agent_Type__c = 'EinsteinServiceAgent',
                Participant__c = agentParticipantId,
                Participant_Object__c = 'GenAiPlannerDefinition',
                Individual__c = NOT_SET,
                Start_Days__c = dayOff, Start_Time__c = hhmmss(startSecs)));

            interactions.add(new SDO_Analytics_AiAgentInteraction_v2__c(
                External_ID__c = iUuid, Name = 'CUSTOMER_PANEL_REBOOT'.left(80),
                Demo_Identifier__c = DEMO_TAG,
                AI_Agent_Session__c = sUuid,
                Ai_Agent_Interaction_Type__c = 'CONVERSATION',
                Topic_API_Name__c = 'firmware_update',
                Telemetry_Trace__c = uuid(), Telemetry_Trace_Span__c = uuid(),
                Start_Days__c = dayOff, Start_Time__c = hhmmss(startSecs),
                End_Days__c = dayOff, End_Time__c = hhmmss(startSecs + durSecs)));

            steps.add(new SDO_Analytics_AIAgentInteractionStep_v2__c(
                External_ID__c = uuid(), Name = 'SESSION_END'.left(80),
                Demo_Identifier__c = DEMO_TAG,
                AI_Agent_Interaction__c = iUuid,
                Ai_Agent_Interaction_Step_Type__c = 'SESSION_END',
                Name__c = STEP_UNRESOLVED,
                Telemetry_Trace_Span_Id__c = uuid(),
                Start_Days__c = dayOff, Start_Time__c = hhmmss(startSecs + durSecs - 5),
                End_Days__c = dayOff, End_Time__c = hhmmss(startSecs + durSecs)));

            // Frustrated-but-not-fixed customer -> CSAT 3.
            tags.add(new SDO_Analytics_AIAgentTag_v2__c(
                External_ID__c = tagUuid, Name = 'CSAT'.left(80),
                Demo_Identifier__c = DEMO_TAG,
                AI_Agent_Tag_Definition_Id__c = CSAT_DEF_ID,
                Value__c = '3', Is_Active__c = true,
                Created_Days__c = dayOff, Created_Time__c = hhmmss(startSecs + durSecs)));

            assocs.add(new SDO_Analytics_AIAgentTagAssociation_v2__c(
                External_ID__c = uuid(),
                Demo_Identifier__c = DEMO_TAG,
                AI_Agent_Session_Id__c = sUuid,
                AI_Agent_Tag_Id__c = tagUuid,
                Association_Reason__c = 'POST_CALL_SURVEY',
                Created_Days__c = dayOff, Created_Time__c = hhmmss(startSecs + durSecs)));
        }

        insert sessions;
        insert participants;
        insert interactions;
        insert steps;
        insert tags;
        insert assocs;

        return 'Staged ' + count + ' firmware-reboot (contained/unresolved) sessions '
             + '(Demo_Identifier__c=' + DEMO_TAG + '). Run a Data Cloud Full Refresh; '
             + 'Contact Resolution drops toward ~60%.';
    }

    /**
     * Reset: deletes ONLY this demo's rows (Demo_Identifier__c='FIRMWARE_REBOOT_DEMO').
     * Scoped every object; never an unfiltered delete; safe to click repeatedly.
     */
    @AuraEnabled
    public static String wipe() {
        Integer removed = 0;
        removed += deleteScoped([SELECT Id FROM SDO_Analytics_AIAgentTagAssociation_v2__c   WHERE Demo_Identifier__c = :DEMO_TAG]);
        removed += deleteScoped([SELECT Id FROM SDO_Analytics_AIAgentTag_v2__c              WHERE Demo_Identifier__c = :DEMO_TAG]);
        removed += deleteScoped([SELECT Id FROM SDO_Analytics_AIAgentInteractionStep_v2__c  WHERE Demo_Identifier__c = :DEMO_TAG]);
        removed += deleteScoped([SELECT Id FROM SDO_Analytics_AiAgentInteraction_v2__c      WHERE Demo_Identifier__c = :DEMO_TAG]);
        removed += deleteScoped([SELECT Id FROM SDO_Analytics_AIAgentSessionParticipa_v2__c WHERE Demo_Identifier__c = :DEMO_TAG]);
        removed += deleteScoped([SELECT Id FROM SDO_Analytics_AIAgentSession_v2__c          WHERE Demo_Identifier__c = :DEMO_TAG]);
        return 'Removed ' + removed + ' ' + DEMO_TAG + ' rows. Re-run a Full Refresh to restore the ~80% baseline.';
    }

    /** Count of firmware-reboot sessions currently staged (for the UI). */
    @AuraEnabled
    public static Integer stagedCount() {
        return [SELECT COUNT() FROM SDO_Analytics_AIAgentSession_v2__c WHERE Demo_Identifier__c = :DEMO_TAG];
    }

    // ---- helpers -----------------------------------------------------------
    private static Integer deleteScoped(List<SObject> rows) {
        if (rows.isEmpty()) return 0;
        delete rows;
        return rows.size();
    }

    private static String resolveVersionApiName() {
        // Pick the highest numeric version of THIS agent only. A coarse LIKE match can
        // pull in similarly-prefixed bundles (e.g. 'AVA' vs 'AVA_Voice_Vivint_Assistant'),
        // so require the exact 'AGENT_API_NAME + _v' prefix with a purely numeric suffix.
        Integer best = -1;
        String prefix = AGENT_API_NAME + '_v';
        for (GenAiPlannerDefinition p : [
                SELECT DeveloperName FROM GenAiPlannerDefinition
                WHERE DeveloperName LIKE :(AGENT_API_NAME + '%')]) {
            if (p.DeveloperName == null || !p.DeveloperName.startsWith(prefix)) continue;
            String tail = p.DeveloperName.substring(prefix.length());
            if (tail.isNumeric()) {
                Integer v = Integer.valueOf(tail);
                if (v > best) best = v;
            }
        }
        return best >= 0 ? 'v' + best : null;
    }

    private static String hhmmss(Integer secs) {
        Integer h = secs / 3600;
        Integer m = Math.mod(secs, 3600) / 60;
        Integer s = Math.mod(secs, 60);
        return pad(h) + ':' + pad(m) + ':' + pad(s);
    }
    private static String pad(Integer v) { return (v < 10 ? '0' : '') + String.valueOf(v); }

    private static String uuid() {
        String h = EncodingUtil.convertToHex(Crypto.generateAesKey(128));
        return h.substring(0, 8) + '-' + h.substring(8, 12) + '-' + h.substring(12, 16)
             + '-' + h.substring(16, 20) + '-' + h.substring(20, 32);
    }
}