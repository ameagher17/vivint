public with sharing class CSATNotificationController {
    // Developer name of the Custom Notification Type deployed alongside this class.
    private static final String NOTIF_TYPE = 'CSAT_Alert';

    /**
     * Fires an in-app (bell) custom notification to the current user. Invoked by the
     * "CSAT notification" button on the CSAT_Notification Visualforce page; sends
     * synchronously so the notification appears the instant the button is clicked.
     */
    public PageReference sendNotification() {
        try {
            CustomNotificationType nt = [
                SELECT Id FROM CustomNotificationType
                WHERE DeveloperName = :NOTIF_TYPE LIMIT 1
            ];

            Messaging.CustomNotification notification = new Messaging.CustomNotification();
            notification.setTitle('CSAT Increase Detected');
            notification.setBody('AVA Voice Agent increased CSAT by 3% last week. Click to see the full report.');
            notification.setNotificationTypeId(nt.Id);
            // Target the current user's record so the notification is clickable. Repoint
            // this to a report/dashboard record Id if a specific destination is desired.
            notification.setTargetId(UserInfo.getUserId());

            notification.send(new Set<String>{ UserInfo.getUserId() });

            ApexPages.addMessage(new ApexPages.Message(
                ApexPages.Severity.CONFIRM, 'Notification sent.'));
        } catch (Exception e) {
            ApexPages.addMessage(new ApexPages.Message(
                ApexPages.Severity.ERROR, 'Could not send notification: ' + e.getMessage()));
        }
        return null;
    }

    /**
     * Fires five fresh in-app (bell) notifications to the current user, each carrying a
     * REAL object icon (not the custom-notification lightning bolt) by driving them off
     * standard record activity:
     *
     *   - 3 Case notifications (engineering / IT bugs & feature requests). Custom
     *     notifications always render the bolt, so instead we post a Chatter feed item
     *     on a Case the running user follows. Chatter never notifies you of your OWN
     *     post, so each post is authored by a separate "reporter" user (CreatedById is
     *     set explicitly). A post from someone else on a record you follow rings the
     *     bell with the Case object icon.
     *
     *   - 2 Task notifications (planning deadline, quarterly budget). Tasks owned by the
     *     current user with a reminder set to fire immediately surface in the bell with
     *     the activity icon; reminders fire for the owner regardless of who created them.
     *
     * Triggering this pushes any older read notification down out of the way.
     */
    public PageReference addFiveNotifications() {
        try {
            Id me = UserInfo.getUserId();

            // A "reporter" other than the running user, so their Chatter posts notify us.
            Id reporterId = pickReporter(me);
            if (reporterId == null) {
                ApexPages.addMessage(new ApexPages.Message(ApexPages.Severity.ERROR,
                    'No second active user available to author the Case posts.'));
                return null;
            }

            // --- 3 Cases: engineering / IT bugs & feature requests --------------------
            // {subjectMarker, feedBody}
            List<List<String>> caseItems = new List<List<String>>{
                new List<String>{
                    'Bug: SSO login intermittently fails on Android app (v4.2.1)',
                    'Three field techs reported SSO login on the Android app failing intermittently after the v4.2.1 update. Can engineering triage today?' },
                new List<String>{
                    'Feature Request: Bulk CSV export on the Analytics dashboard',
                    'Ops is requesting a bulk CSV export button on the Analytics dashboard. Flagging for engineering prioritization this sprint.' },
                new List<String>{
                    'Bug: Data Cloud ingestion job times out on large batches',
                    'The nightly Data Cloud ingestion job is timing out on batches over 100k rows. Needs an engineering fix before month-end close.' }
            };

            Integer caseCount = 0;
            for (List<String> ci : caseItems) {
                Id caseId = findOrCreateCase(ci[0], reporterId);
                ensureFollowing(me, caseId);
                // Fresh post each click -> a fresh bell notification.
                FeedItem fi = new FeedItem(
                    ParentId    = caseId,
                    Body        = ci[1],
                    CreatedById = reporterId   // author != current user, so it notifies us
                );
                insert fi;
                caseCount++;
            }

            // --- 2 Tasks: upcoming planning deadlines / quarterly budget --------------
            List<String> taskSubjects = new List<String>{
                'Q3 budget proposal due Friday',
                'Sprint 24 planning – finalize scope by end of day'
            };

            List<Task> tasks = new List<Task>();
            for (String subj : taskSubjects) {
                tasks.add(new Task(
                    OwnerId          = me,
                    Subject          = subj,
                    Status           = 'Not Started',
                    Priority         = 'High',
                    ActivityDate     = Date.today(),
                    IsReminderSet    = true,
                    // Fire immediately (reminder time already in the past by a minute).
                    ReminderDateTime = DateTime.now().addMinutes(-1)
                ));
            }
            insert tasks;

            ApexPages.addMessage(new ApexPages.Message(ApexPages.Severity.CONFIRM,
                caseCount + ' Case notifications + ' + tasks.size() +
                ' Task reminders fired. Check the bell (🔔) icon.'));
        } catch (Exception e) {
            ApexPages.addMessage(new ApexPages.Message(
                ApexPages.Severity.ERROR, 'Could not send notifications: ' + e.getMessage()));
        }
        return null;
    }

    /** Reuses a Case with the given subject if present, else creates one owned by the reporter. */
    private Id findOrCreateCase(String subject, Id reporterId) {
        List<Case> existing = [SELECT Id FROM Case WHERE Subject = :subject LIMIT 1];
        if (!existing.isEmpty()) {
            return existing[0].Id;
        }
        Case c = new Case(
            Subject  = subject,
            Status   = 'New',
            Origin   = 'Web',
            Priority = 'High',
            OwnerId  = reporterId
        );
        insert c;
        return c.Id;
    }

    /** Makes the given user follow the record (idempotent). */
    private void ensureFollowing(Id subscriberId, Id parentId) {
        List<EntitySubscription> subs = [
            SELECT Id FROM EntitySubscription
            WHERE SubscriberId = :subscriberId AND ParentId = :parentId LIMIT 1
        ];
        if (subs.isEmpty()) {
            insert new EntitySubscription(SubscriberId = subscriberId, ParentId = parentId);
        }
    }

    /** Picks an active user other than the current one to author Case posts. */
    private Id pickReporter(Id me) {
        List<User> svc = [
            SELECT Id FROM User
            WHERE IsActive = true AND Id != :me AND Profile.Name = 'SDO-Service'
            LIMIT 1
        ];
        if (!svc.isEmpty()) {
            return svc[0].Id;
        }
        List<User> others = [
            SELECT Id FROM User
            WHERE IsActive = true AND Id != :me AND UserType = 'Standard'
            LIMIT 1
        ];
        return others.isEmpty() ? null : others[0].Id;
    }
}
