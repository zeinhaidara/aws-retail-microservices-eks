# Website email notifications

1. Enter an email address in the cart and select **Verify email**.
2. Open the AWS SES verification email (check spam) and confirm its link.
3. Return to the website and select **Check verification**.
4. Reserve a trip. Order details travel through EventBridge, SQS, and the
   notification service, which sends an SES email to the order's address.

An already SES-verified address is ready immediately. Blank email keeps the
existing reservation-without-email flow. Verification is checked on the backend
before inventory is reserved, not just in the browser. No fixed demo recipient
is used for website orders.

Deploy the Terraform notification-role permissions before the application CD.
The SES sender/domain must be verified and account sending enabled. Verification
does not remove SES sandbox sending quotas or request production access.

Demo safeguards: one verification request per address per minute, at most ten
requests per minute and 100 per hour per notification process; random browser
session tokens expire after 24 hours. Status checks are cached for five seconds.
These limits and tokens are in memory: pod restarts require starting verification
again, and replicas do not share limits or sessions. Keep the demo at one replica.
Before public production use, add shared durable rate limits/session storage and
bot protection. SES identity verification is not website user authentication.

SES identities created by visitor requests are runtime-managed, not Terraform
resources. Monitor identity quotas and clean up unused identities when the demo
is finished; verification does not guarantee inbox delivery.
