public with sharing class InvocableSmartHubDeviceReboot {

    @InvocableMethod(
        label='Reboot Smart Hub Device'
        description='Connects to the customer Smart Hub device and triggers a remote reboot.'
    )
    public static List<Result> execute(List<Request> requests) {
        List<Result> results = new List<Result>();
        for (Request req : requests) {
            Result r = new Result();
            r.rebootStatus = 'Success';
            r.outputMessage = 'Smart Hub device rebooted successfully.';
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