#!/usr/bin/env bash
set -uo pipefail
failed=0

echo '::group::Pod status and deployed image versions'
kubectl get pods -n retail-dev -l app.kubernetes.io/part-of=retail -o wide || failed=1
kubectl get deployments retail-notification retail-order -n retail-dev -o json |
  jq '.items[] | {name: .metadata.name, image: .spec.template.spec.containers[0].image,
    serviceAccount: .spec.template.spec.serviceAccountName,
    configuration: [.spec.template.spec.containers[0].env[] | select(
      .name == "ORDER_SERVICE_URL" or .name == "ORDER_EVENTS_QUEUE_URL" or
      .name == "SES_FROM_ADDRESS" or .name == "AWS_REGION" or
      .name == "MYSQL_HOST" or .name == "MYSQL_PORT" or .name == "EVENT_BUS_NAME")]}' || failed=1
echo '::endgroup::'

for service in notification order; do
  echo "::group::$service retained logs (health checks excluded)"
  kubectl logs -n retail-dev -l "app.kubernetes.io/name=$service" \
    --all-containers=true --prefix=true --timestamps=true --since=24h --tail=-1 |
    awk '
      /"GET \/(health|ready) HTTP\// { next }
      { lines[count % 500] = $0; count++ }
      END {
        if (count == 0) print "No non-health-check entries retained. Deleted-pod logs cannot be recovered here."
        start = count > 500 ? count - 500 : 0
        for (i = start; i < count; i++) print lines[i % 500]
      }' || failed=1
  echo '::endgroup::'
done

echo '::group::Service ports and ready endpoints'
kubectl get services retail-order retail-notification -n retail-dev -o wide || failed=1
kubectl get endpointslices -n retail-dev -l kubernetes.io/service-name=retail-order -o wide || failed=1
kubectl get endpointslices -n retail-dev -l kubernetes.io/service-name=retail-notification -o wide || failed=1
echo '::endgroup::'

echo '::group::SES sender and sending status'
sender=$(kubectl get deployment retail-notification -n retail-dev \
  -o 'jsonpath={.spec.template.spec.containers[0].env[?(@.name=="SES_FROM_ADDRESS")].value}') || failed=1
if [[ -n "$sender" ]]; then
  aws sesv2 get-email-identity --email-identity "${sender##*@}" \
    --query '{Verified:VerifiedForSendingStatus,Dkim:DkimAttributes.Status}' || failed=1
else
  echo '::error::Sender configuration is missing.'
  failed=1
fi
aws sesv2 get-account \
  --query '{SendingEnabled:SendingEnabled,ProductionAccess:ProductionAccessEnabled,Quota:SendQuota}' || failed=1
echo '::endgroup::'

echo '::group::Main queue and dead-letter queue (counts only, no message reception)'
queue_url=$(kubectl get deployment retail-notification -n retail-dev \
  -o 'jsonpath={.spec.template.spec.containers[0].env[?(@.name=="ORDER_EVENTS_QUEUE_URL")].value}') || failed=1
if [[ -n "$queue_url" ]]; then
  if attributes=$(aws sqs get-queue-attributes --queue-url "$queue_url" \
      --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible RedrivePolicy); then
    printf '%s\n' "$attributes"
    dlq_arn=$(jq -r '.Attributes.RedrivePolicy | fromjson | .deadLetterTargetArn' <<< "$attributes")
    if dlq_url=$(aws sqs get-queue-url --queue-name "${dlq_arn##*:}" --query QueueUrl --output text); then
      aws sqs get-queue-attributes --queue-url "$dlq_url" \
        --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible || failed=1
    else
      failed=1
    fi
  else
    failed=1
  fi
fi
echo '::endgroup::'

echo '::group::Order fetch from inside the notification pod'
pod=$(kubectl get pods -n retail-dev -l app.kubernetes.io/name=notification -o json |
  jq -r '[.items[] | select(.metadata.deletionTimestamp == null and .status.phase == "Running")][0].metadata.name // empty') || failed=1
if [[ -n "$pod" ]]; then
  kubectl exec -i -n retail-dev "$pod" -c notification -- python - "${ORDER_ID:-}" <<'PY' || failed=1
import json
import sys
import uuid
from urllib.request import urlopen
import app

def main():
    order_id = sys.argv[1]
    print("Order service URL:", app.ORDER_SERVICE_URL)
    with urlopen(f"{app.ORDER_SERVICE_URL}/health", timeout=5) as response:
        print("Notification -> order health HTTP status:", response.status)
    if not order_id:
        print("No order UUID supplied. Run again with an existing order ID to test database lookup.")
        return
    uuid.UUID(order_id)
    order = app.order_details(order_id)
    print(json.dumps({"orderFound": bool(order), "hasRecipient": bool(order.get("email")),
                      "itemCount": len(order.get("items", [])), "totalType": type(order.get("total")).__name__}))
    if order.get("email"):
        client = app.ses_client()
        try:
            result = client.get_email_identity(EmailIdentity=order["email"])
            print("Saved order recipient SES verified:", result.get("VerifiedForSendingStatus", False))
        except client.exceptions.NotFoundException:
            print("Saved order recipient is not an SES identity in the pod's configured region.")
    print("No send_email call made; no order or queue message changed.")

if __name__ == "__main__":
    main()
PY
else
  echo '::error::No running notification pod found.'
  failed=1
fi
echo '::endgroup::'
echo 'Diagnostics never rebuild, deploy, send email, receive SQS messages, delete, purge, or redrive.'
exit "$failed"
