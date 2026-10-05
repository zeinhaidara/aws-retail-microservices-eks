#!/usr/bin/env bash
set -uo pipefail

# Read-only diagnostics. Do not receive, delete, purge, or redrive queue messages.
failed=0
echo '::group::Notification pods'
kubectl get pods -n retail-dev -l app.kubernetes.io/name=notification -o wide || failed=1
echo '::endgroup::'

echo '::group::Notification worker logs (last 24 hours, up to 200 lines per pod)'
kubectl logs -n retail-dev -l app.kubernetes.io/name=notification \
  --all-containers=true --prefix=true --timestamps=true --since=24h --tail=200 || failed=1
echo '::endgroup::'

echo '::group::Order service logs (last 24 hours, up to 100 lines per pod)'
kubectl logs -n retail-dev -l app.kubernetes.io/name=order \
  --all-containers=true --prefix=true --timestamps=true --since=24h --tail=100 || failed=1
echo '::endgroup::'

echo '::group::SES sender verification and account status'
sender=$(kubectl get deployment retail-notification -n retail-dev \
  -o 'jsonpath={.spec.template.spec.containers[0].env[?(@.name=="SES_FROM_ADDRESS")].value}') || failed=1
if [[ -n "$sender" ]]; then
  domain="${sender##*@}"
  aws sesv2 get-email-identity --email-identity "$domain" \
    --query '{Verified:VerifiedForSendingStatus,Dkim:DkimAttributes.Status}' || failed=1
else
  echo '::error::Notification sender is missing or deployment could not be read.'
  failed=1
fi
aws sesv2 get-account \
  --query '{SendingEnabled:SendingEnabled,ProductionAccess:ProductionAccessEnabled,Quota:SendQuota}' || failed=1
echo '::endgroup::'

echo '::group::Order queue status'
queue_url=$(kubectl get deployment retail-notification -n retail-dev \
  -o 'jsonpath={.spec.template.spec.containers[0].env[?(@.name=="ORDER_EVENTS_QUEUE_URL")].value}') || failed=1
if [[ -n "$queue_url" ]]; then
  aws sqs get-queue-attributes --queue-url "$queue_url" \
    --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible RedrivePolicy || failed=1
fi
echo '::endgroup::'

echo 'Look for: Order event failed; SQS will retry it, MessageRejected, AccessDenied, or order-fetch HTTP errors.'
exit "$failed"
