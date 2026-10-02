#!/usr/bin/env bash
set -euo pipefail

operation="${1:?usage: platform-addons.sh install|destroy}"
cluster_name="${PROJECT_NAME}-${OWNER}-${TARGET_ENVIRONMENT}"
namespace="retail-${TARGET_ENVIRONMENT}"

configure_kubectl() {
  aws eks update-kubeconfig --name "$cluster_name" --region "$AWS_REGION" >/dev/null
}

install_addons() {
  local certificate_arn domain_name vpc_id lbc_role_arn external_dns_role_arn
  certificate_arn="$(terraform -chdir="$TF_DIR" output -raw storefront_certificate_arn)"
  domain_name="$(terraform -chdir="$TF_DIR" output -raw storefront_domain_name)"
  vpc_id="$(terraform -chdir="$TF_DIR" output -raw vpc_id)"
  lbc_role_arn="$(terraform -chdir="$TF_DIR" output -raw load_balancer_controller_role_arn)"
  external_dns_role_arn="$(terraform -chdir="$TF_DIR" output -raw external_dns_role_arn)"

  configure_kubectl
  kubectl create namespace "$namespace" --dry-run=client -o yaml | kubectl apply -f - >/dev/null

  # Terraform installs the managed CoreDNS add-on with Fargate scheduling.
  # Require DNS readiness before installing controllers that depend on it.
  kubectl rollout status deployment/coredns --namespace kube-system --timeout=5m

  helm repo add eks https://aws.github.io/eks-charts --force-update
  helm upgrade --install aws-load-balancer-controller eks/aws-load-balancer-controller \
    --namespace kube-system --version 1.14.0 --wait --timeout 5m \
    --set clusterName="$cluster_name" --set region="$AWS_REGION" --set vpcId="$vpc_id" \
    --set serviceAccount.create=true --set serviceAccount.name=aws-load-balancer-controller \
    --set "serviceAccount.annotations.eks\\.amazonaws\\.com/role-arn=$lbc_role_arn"

  helm repo add external-dns https://kubernetes-sigs.github.io/external-dns/ --force-update
  helm upgrade --install external-dns external-dns/external-dns \
    --namespace kube-system --version 1.22.0 --wait --timeout 5m \
    --set provider.name=aws --set policy=sync --set registry=txt --set interval=30s \
    --set txtOwnerId="$cluster_name" --set-string "domainFilters[0]=$domain_name" \
    --set serviceAccount.create=true --set serviceAccount.name=external-dns \
    --set "serviceAccount.annotations.eks\\.amazonaws\\.com/role-arn=$external_dns_role_arn" \
    --set-string extraArgs.aws-zone-type=public

  kubectl rollout status deployment/aws-load-balancer-controller -n kube-system --timeout=180s
  kubectl rollout status deployment/external-dns -n kube-system --timeout=180s
  sed -e "s|__DOMAIN_NAME__|$domain_name|g" \
      -e "s|__CERTIFICATE_ARN__|$certificate_arn|g" \
      -e "s|__NAMESPACE__|$namespace|g" \
      -e "s|__ENVIRONMENT__|$TARGET_ENVIRONMENT|g" \
      terraform/modules/edge/storefront-ingress.yaml.template | kubectl apply -f -
}

destroy_addons() {
  if ! aws eks describe-cluster --name "$cluster_name" --region "$AWS_REGION" >/dev/null 2>&1; then
    return
  fi

  configure_kubectl
  if kubectl get namespace "$namespace" >/dev/null 2>&1; then
    kubectl delete ingress storefront --namespace "$namespace" --ignore-not-found --wait=true --timeout=5m
    sleep 40
  fi

  for release in external-dns aws-load-balancer-controller; do
    if helm status "$release" --namespace kube-system >/dev/null 2>&1; then
      helm uninstall "$release" --namespace kube-system --wait
    fi
  done
}

case "$operation" in
  install) install_addons ;;
  destroy) destroy_addons ;;
  *) echo "Unsupported operation: $operation" >&2; exit 2 ;;
esac
