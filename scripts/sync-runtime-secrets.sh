#!/usr/bin/env bash
set -euo pipefail

validate_secrets() {
  for secret_name in CLOUDFLARE_ACCOUNT_ID CLOUDFLARE_API_TOKEN GEMINI_API_KEY; do
    if [[ -z "${!secret_name:-}" ]]; then
      echo "::error::Missing GitHub Actions secret: ${secret_name}"
      exit 1
    fi
  done
}

sync_secrets() {
  validate_secrets
  umask 077

  local base namespace
  base="${PROJECT_NAME}-${OWNER}-${TARGET_ENVIRONMENT}"
  namespace="retail-${TARGET_ENVIRONMENT}"
  runtime_temp_dir="$(mktemp -d "${RUNNER_TEMP:-/tmp}/runtime-secrets.XXXXXX")"
  trap 'rm -rf "$runtime_temp_dir"' EXIT

  jq -n --arg account "$CLOUDFLARE_ACCOUNT_ID" --arg token "$CLOUDFLARE_API_TOKEN" \
    '{CLOUDFLARE_ACCOUNT_ID: $account, CLOUDFLARE_API_TOKEN: $token}' > "$runtime_temp_dir/cloudflare.json"
  jq -n --arg key "$GEMINI_API_KEY" '{GEMINI_API_KEY: $key}' > "$runtime_temp_dir/gemini.json"

  aws secretsmanager put-secret-value --secret-id "${base}/services/trip-planner/cloudflare" \
    --secret-string "file://$runtime_temp_dir/cloudflare.json" --region "$AWS_REGION" >/dev/null
  aws secretsmanager put-secret-value --secret-id "${base}/services/trip-planner/gemini" \
    --secret-string "file://$runtime_temp_dir/gemini.json" --region "$AWS_REGION" >/dev/null

  aws eks update-kubeconfig --name "$base" --region "$AWS_REGION" >/dev/null
  kubectl create namespace "$namespace" --dry-run=client -o yaml | kubectl apply -f - >/dev/null
  sync_kubernetes_secret "${base}/services/trip-planner/cloudflare" cloudflare-ai-credentials \
    '"CLOUDFLARE_API_TOKEN=" + .CLOUDFLARE_API_TOKEN, "CLOUDFLARE_ACCOUNT_ID=" + .CLOUDFLARE_ACCOUNT_ID'
  sync_kubernetes_secret "${base}/services/trip-planner/gemini" gemini-ai-credentials \
    '"GEMINI_API_KEY=" + .GEMINI_API_KEY'

  echo "Synced trip-planner credentials into Secrets Manager and namespace ${namespace}."
}

sync_kubernetes_secret() {
  local secret_id kubernetes_name jq_filter env_file
  secret_id="$1"
  kubernetes_name="$2"
  jq_filter="$3"
  env_file="$(mktemp "$runtime_temp_dir/secret.XXXXXX.env")"

  aws secretsmanager get-secret-value --secret-id "$secret_id" --query SecretString \
    --output text --region "$AWS_REGION" | jq -r "$jq_filter" > "$env_file"
  kubectl create secret generic "$kubernetes_name" --namespace "$namespace" \
    --from-env-file="$env_file" --dry-run=client -o yaml | kubectl apply -f - >/dev/null
}

case "${1:-}" in
  validate) validate_secrets ;;
  sync) sync_secrets ;;
  *) echo "usage: sync-runtime-secrets.sh validate|sync" >&2; exit 2 ;;
esac
