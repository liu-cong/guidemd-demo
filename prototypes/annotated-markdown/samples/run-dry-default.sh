#!/usr/bin/env bash
# optimized-baseline — generated from guides/optimized-baseline/guide.template.md
# assignment: {'infra_provider': 'base', 'router_mode': 'standalone', 'gateway_provider': 'none', 'accelerator': 'gpu', 'model_server': 'vllm', 'model': 'Qwen/Qwen3-32B', 'monitoring': 'off'}
set -euo pipefail

# --- step 1/13  (guides/common/prereqs.md:13) ---
export GUIDE_NAME=optimized-baseline
export NAMESPACE=llm-d-optimized-baseline
export HF_TOKEN=HF_TOKEN_PLACEHOLDER
export MODEL=Qwen/Qwen3-32B
export CURL_TEST_IMAGE=cfmanteiga/alpine-bash-curl-jq:latest
export BENCHMARK_REF=main
export HARNESS=inference-perf
export WORKLOAD=guide_optimized-baseline_1.yaml

# --- step 2/13  (guides/common/prereqs.md:31) ---
export REPO_ROOT=$(realpath $(git rev-parse --show-toplevel))
source ${REPO_ROOT}/guides/env.sh

# --- step 3/13  [e2e=skip]  (guides/common/prereqs.md:48) ---
curl -sfL https://github.com/kubernetes-sigs/gateway-api-inference-extension/releases/download/${GAIE_VERSION}/v1-manifests.yaml -o /dev/null

# --- step 4/13  [e2e=skip]  (guides/common/prereqs.md:60) ---
kubectl create namespace ${NAMESPACE} --dry-run=client -o yaml > /dev/null

# --- step 5/13  (guides/optimized-baseline/guide.template.md:153) ---
export ROUTER_VALUES="-f ${REPO_ROOT}/guides/${GUIDE_NAME}/router/${GUIDE_NAME}.values.yaml"

# --- step 6/13  (guides/common/install-router.md:4) ---
export ROUTER_BASE_VALUES="-f ${REPO_ROOT}/guides/recipes/router/base.values.yaml"

# --- step 7/13  (guides/common/install-router.md:10) ---
export MONITORING_VALUES=""

# --- step 8/13  [e2e=skip]  (guides/common/install-router.md:39) ---
helm template ${GUIDE_NAME} \
  ${ROUTER_STANDALONE_CHART} \
  ${ROUTER_BASE_VALUES} \
  ${MONITORING_VALUES} \
  ${ROUTER_VALUES} \
  --version ${ROUTER_CHART_VERSION} > /dev/null

# --- step 9/13  (guides/optimized-baseline/guide.template.md:176) ---
export KUSTOMIZE_DIR=${REPO_ROOT}/guides/${GUIDE_NAME}/modelserver/gpu/vllm/base/

# --- step 10/13  [e2e=skip]  (guides/common/install-modelserver.md:9) ---
kubectl kustomize ${KUSTOMIZE_DIR} > /dev/null

# --- step 11/13  (guides/common/benchmark.md:19) ---
curl -sSL https://raw.githubusercontent.com/llm-d/llm-d-benchmark/${BENCHMARK_REF}/install.sh | bash

# --- step 12/13  (guides/common/benchmark.md:24) ---
cd llm-d-benchmark
source .venv/bin/activate
llmdbenchmark --version

# --- step 13/13  (guides/common/benchmark.md:49) ---
export GATEWAY_CLASS="epponly"
