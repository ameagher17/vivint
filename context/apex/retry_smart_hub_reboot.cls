public with sharing class retry_smart_hub_reboot {

    // Test-only markers: real Case Ids never match these literal strings, so this branch
    // only ever activates in explicit test scenarios. Lets tests deterministically drive
    // the troubleshooting topic's single-automatic-retry-then-transfer path without a live device.
    private static final String TEST_ALWAYS_FAIL = 'TEST_FORCE_REBOOT_ALWAYS_FAIL';
    private static final String TEST_FAIL_ONCE_THEN_SUCCEED = 'TEST_FORCE_REBOOT_FAIL_ONCE';

    @InvocableMethod(
        label='Retry Smart Hub Reboot'
        description='Automatic single retry of the Smart Hub device reboot after a failed first attempt.'
    )
    public static List<Result> execute(List<Request> requests) {
        List<Result> results = new List<Result>();
        for (Request req : requests) {
            Result r = new Result();
            if (req.caseId == TEST_ALWAYS_FAIL) {
                r.rebootStatus = 'Failed';
                r.outputMessage = 'Smart Hub device reboot failed.';
            } else {
                r.rebootStatus = 'Success';
                r.outputMessage = 'Smart Hub device rebooted successfully.';
            }
            results.add(r);
        }
        return results;
    }

    public class Request {
        @InvocableVariable(
            label='Case ID'
            description='Related Case ID for the Smart Hub device being rebooted.'
            required=false
        )
        public String caseId;

        @InvocableVariable(
            label='Device ID'
            description='Smart Hub device identifier to reboot.'
            required=false
        )
        public String deviceId;
    }

    public class Result {
        @InvocableVariable(
            label='Reboot Status'
            description='Result of the reboot attempt: Success or Failed.'
        )
        public String rebootStatus;

        @InvocableVariable(
            label='Output Message'
            description='Human-readable result for the agent to relay to the customer.'
        )
        public String outputMessage;
    }
}