#!/usr/bin/env bash
# optimized-baseline — generated from guides/optimized-baseline/guide.template.md
# assignment: {'infra_provider': 'gke', 'router_mode': 'standalone', 'accelerator': 'tpu/v6', 'model_server': 'vllm', 'model': 'Qwen/Qwen3-32B', 'monitoring': 'off'}
set -euo pipefail

# --- step 1/23 ---
export GUIDE_NAME=optimized-baseline
export NAMESPACE=llm-d-optimized-baseline
export HF_TOKEN=HF_TOKEN_PLACEHOLDER
export MODEL=Qwen/Qwen3-32B
export CURL_TEST_IMAGE=cfmanteiga/alpine-bash-curl-jq:latest
export BENCHMARK_REF=main
export HARNESS=inference-perf
export WORKLOAD=guide_optimized-baseline_1.yaml

# --- step 2/23 ---
export REPO_ROOT=$(realpath $(git rev-parse --show-toplevel))
source ${REPO_ROOT}/guides/env.sh

# --- step 3/23  [dry-run=skip] ---
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api-inference-extension/releases/download/${GAIE_VERSION}/v1-manifests.yaml

# --- step 4/23 ---
kubectl create namespace ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -

# --- step 5/23 ---
export ROUTER_VALUES="-f ${REPO_ROOT}/guides/${GUIDE_NAME}/router/${GUIDE_NAME}.values.yaml"

# --- step 6/23 ---
export ROUTER_BASE_VALUES="-f ${REPO_ROOT}/guides/recipes/router/base.values.yaml"

# --- step 7/23 ---
export MONITORING_VALUES=""

# --- step 8/23  [dry-run=skip] ---
helm install ${GUIDE_NAME} \
  ${ROUTER_STANDALONE_CHART} \
  ${ROUTER_BASE_VALUES} \
  ${MONITORING_VALUES} \
  ${ROUTER_VALUES} \
  -n ${NAMESPACE} --version ${ROUTER_CHART_VERSION}

# --- step 9/23  [dry-run=skip] ---
kubectl rollout status deployment -l app.kubernetes.io/instance=${GUIDE_NAME} \
  -n ${NAMESPACE} --timeout=300s

# --- step 10/23 ---
export KUSTOMIZE_DIR=${REPO_ROOT}/guides/${GUIDE_NAME}/modelserver/tpu/v6/vllm/

# --- step 11/23  [dry-run=skip] ---
kubectl apply -n ${NAMESPACE} -k ${KUSTOMIZE_DIR}

# --- step 12/23  [dry-run=skip] ---
kubectl wait --for=condition=Ready pod \
  -l llm-d.ai/inferenceServing=true \
  -n ${NAMESPACE} --timeout=1800s

# --- step 13/23  [dry-run=skip] ---
export IP=$(kubectl get service ${GUIDE_NAME}-epp -n ${NAMESPACE} -o jsonpath='{.spec.clusterIP}')

# --- step 14/23  [dry-run=skip] ---
kubectl run curl-test --rm -i --restart=Never \
  --image=${CURL_TEST_IMAGE} \
  --namespace="${NAMESPACE}" \
  --env="IP=${IP}" \
  --env="MODEL=${MODEL}" \
  -- /bin/sh -c 'curl -sS -X POST "http://${IP}/v1/completions" -H "Content-Type: application/json" -d "{\"model\": \"${MODEL}\", \"prompt\": \"How are you today?\"}"'

# --- step 15/23 ---
curl -sSL https://raw.githubusercontent.com/llm-d/llm-d-benchmark/${BENCHMARK_REF}/install.sh | bash

# --- step 16/23 ---
cd llm-d-benchmark
source .venv/bin/activate
llmdbenchmark --version

# --- step 17/23  [dry-run=skip] ---
export IP=$(kubectl get service ${GUIDE_NAME}-epp -n ${NAMESPACE} -o jsonpath='{.spec.clusterIP}')

# --- step 18/23  [dry-run=skip] ---
export ENDPOINT_URL="http://${IP}"

# --- step 19/23 ---
export GATEWAY_CLASS="epponly"

# --- step 20/23  [dry-run=skip] ---
llmdbenchmark \
  --spec           guides/${GUIDE_NAME} \
  run \
  --endpoint-url   "${ENDPOINT_URL}" \
  --gateway-class  "${GATEWAY_CLASS}" \
  --model          "${MODEL}" \
  --namespace      "${NAMESPACE}" \
  --harness        "${HARNESS}" \
  --workload       "${WORKLOAD}" \
  --analyze

# --- step 21/23  [dry-run=skip] ---
helm uninstall ${GUIDE_NAME} -n ${NAMESPACE}

# --- step 22/23  [dry-run=skip] ---
kubectl delete -n ${NAMESPACE} -k ${KUSTOMIZE_DIR} --ignore-not-found=true

# --- step 23/23 ---
kubectl delete namespace ${NAMESPACE}
