#!/usr/bin/env bash
# optimized-baseline — generated from guides/optimized-baseline/guide.template.md
# assignment: {'infra_provider': 'base', 'router_mode': 'standalone', 'accelerator': 'gpu', 'model_server': 'vllm', 'model': 'Qwen/Qwen3-32B', 'monitoring': 'off'}
set -euo pipefail

# --- step 1/14 ---
export GUIDE_NAME=optimized-baseline
export NAMESPACE=llm-d-optimized-baseline
export HF_TOKEN=HF_TOKEN_PLACEHOLDER
export MODEL=Qwen/Qwen3-32B
export CURL_TEST_IMAGE=cfmanteiga/alpine-bash-curl-jq:latest
export BENCHMARK_REF=main
export HARNESS=inference-perf
export WORKLOAD=guide_optimized-baseline_1.yaml

# --- step 2/14 ---
export REPO_ROOT=$(realpath $(git rev-parse --show-toplevel))
source ${REPO_ROOT}/guides/env.sh

# --- step 3/14  [e2e=skip] ---
curl -sfL https://github.com/kubernetes-sigs/gateway-api-inference-extension/releases/download/${GAIE_VERSION}/v1-manifests.yaml -o /dev/null

# --- step 4/14 ---
kubectl create namespace ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -

# --- step 5/14 ---
export ROUTER_VALUES="-f ${REPO_ROOT}/guides/${GUIDE_NAME}/router/${GUIDE_NAME}.values.yaml"

# --- step 6/14 ---
export ROUTER_BASE_VALUES="-f ${REPO_ROOT}/guides/recipes/router/base.values.yaml"

# --- step 7/14 ---
export MONITORING_VALUES=""

# --- step 8/14  [e2e=skip] ---
helm template ${GUIDE_NAME} \
  ${ROUTER_STANDALONE_CHART} \
  ${ROUTER_BASE_VALUES} \
  ${MONITORING_VALUES} \
  ${ROUTER_VALUES} \
  --version ${ROUTER_CHART_VERSION} > /dev/null

# --- step 9/14 ---
export KUSTOMIZE_DIR=${REPO_ROOT}/guides/${GUIDE_NAME}/modelserver/gpu/vllm/base/

# --- step 10/14  [e2e=skip] ---
kubectl kustomize ${KUSTOMIZE_DIR} > /dev/null

# --- step 11/14 ---
curl -sSL https://raw.githubusercontent.com/llm-d/llm-d-benchmark/${BENCHMARK_REF}/install.sh | bash

# --- step 12/14 ---
cd llm-d-benchmark
source .venv/bin/activate
llmdbenchmark --version

# --- step 13/14 ---
export GATEWAY_CLASS="epponly"

# --- step 14/14 ---
kubectl delete namespace ${NAMESPACE}
