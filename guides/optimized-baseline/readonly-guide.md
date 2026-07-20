<!-- GENERATED FILE — DO NOT EDIT. Source: guide.template.md; regenerate with: guidemd.py render-md guide.template.md -->
# Optimized Baseline

[![E2E (AMD ROCM)](https://github.com/llm-d/llm-d/actions/workflows/consolidate-status-optimized-baseline-amd-acc-rocm-vllm-x.yaml/badge.svg)](https://github.com/llm-d/llm-d/actions/workflows/consolidate-status-optimized-baseline-amd-acc-rocm-vllm-x.yaml)
[![E2E (CKS GPU)](https://github.com/llm-d/llm-d/actions/workflows/consolidate-status-optimized-baseline-cks-acc-gpu-vllm-x.yaml/badge.svg)](https://github.com/llm-d/llm-d/actions/workflows/consolidate-status-optimized-baseline-cks-acc-gpu-vllm-x.yaml)
[![E2E (GKE GPU)](https://github.com/llm-d/llm-d/actions/workflows/consolidate-status-optimized-baseline-gke-acc-gpu-vllm-x.yaml/badge.svg)](https://github.com/llm-d/llm-d/actions/workflows/consolidate-status-optimized-baseline-gke-acc-gpu-vllm-x.yaml)
[![E2E (GKE TPU)](https://github.com/llm-d/llm-d/actions/workflows/consolidate-status-optimized-baseline-gke-acc-tpu-vllm-x.yaml/badge.svg)](https://github.com/llm-d/llm-d/actions/workflows/consolidate-status-optimized-baseline-gke-acc-tpu-vllm-x.yaml)
[![E2E (OCP GPU)](https://github.com/llm-d/llm-d/actions/workflows/consolidate-status-optimized-baseline-ibm-acc-gpu-vllm-x.yaml/badge.svg)](https://github.com/llm-d/llm-d/actions/workflows/consolidate-status-optimized-baseline-ibm-acc-gpu-vllm-x.yaml)
[![E2E (Intel XPU)](https://github.com/llm-d/llm-d/actions/workflows/consolidate-status-optimized-baseline-intel-acc-xpu-vllm-x.yaml/badge.svg)](https://github.com/llm-d/llm-d/actions/workflows/consolidate-status-optimized-baseline-intel-acc-xpu-vllm-x.yaml)

<!-- md-only -->
> [!TIP]
> **Reading this on GitHub?** This is the full guide; the default
> configuration is shown expanded and alternatives are collapsed — expand the
> *Alternative* sections that match your setup. For the interactive version
> with a configuration picker, see this guide on [llm-d.ai](https://llm-d.ai).
<!-- end -->

## Overview

This guide deploys the recommended out of the box
[configuration](https://github.com/llm-d/llm-d-router/blob/main/docs/architecture.md)
for most vLLM, SGLang, and TensorRT-LLM deployments, reducing tail latency and
increasing throughput through load-aware and prefix-cache aware balancing.

The optimized-baseline defaults to two main routing criteria:

- **Prefix-cache aware** using the [prefix cache scorer](https://github.com/llm-d/llm-d-router/tree/main/pkg/epp/framework/plugins/scheduling/scorer/prefix),
  which scores candidate endpoints by estimating prompt prefix cache reuse on
  each model server, complemented by the
  [`no-hit-lru-scorer`](https://github.com/llm-d/llm-d-router/tree/main/pkg/epp/framework/plugins/scheduling/scorer/nohitlru)
  that spreads cold requests (zero cache hits) evenly across endpoints to
  balance the "prefill" workload.

- **Load-aware** using both the
  [kv-cache utilization](https://github.com/llm-d/llm-d-router/tree/main/pkg/epp/framework/plugins/scheduling/scorer/kvcacheutilization)
  and the [queue size](https://github.com/llm-d/llm-d-router/tree/main/pkg/epp/framework/plugins/scheduling/scorer/queuedepth)
  scorers.

Both plugins are used with their built-in defaults — no per-deployment tuning
is required for this guide's reference setup (Qwen3-32B on H100 80&nbsp;GB,
TP=2). If you deploy a **different model or accelerator**, the
saturation-aware override gate keys off the `peakPrefillThroughput` of the
filter, which is hardware- and model-specific; measure your own with the
shared [calibration recipe](../recipes/router/calibration/README.md) and set
it on the filter. See
[Adapting to other hardware](#adapting-to-other-hardware) below.

## Configuration

| Parameter          | Default                                                 | Example                                                           |
| ------------------ | ------------------------------------------------------- | ----------------------------------------------------------------- |
| Model              | [Qwen/Qwen3-32B](https://huggingface.co/Qwen/Qwen3-32B) | [openai/gpt-oss-120b](https://huggingface.co/openai/gpt-oss-120b) |
| Replicas           | 8                                                       | 16                                                                |
| Tensor Parallelism | 2                                                       | 1                                                                 |
| GPUs per replica   | 2                                                       | 1                                                                 |
| Total GPUs         | 16                                                      | 16                                                                |

### Supported Hardware Backends

This guide includes configurations for the following accelerators:

| Backend        | Directory | Notes                                                           |
| -------------- | --------- | --------------------------------------------------------------- |
| NVIDIA GPU     | `gpu`     | Default configuration (`infra_provider` options: `base`, `gke`) |
| AMD GPU        | `amd`     | AMD GPU                                                         |
| Intel XPU      | `xpu`     | Intel Data Center GPU Max 1550+                                 |
| Google TPU v6e | `tpu/v6`  | GKE TPU                                                         |
| Google TPU v7  | `tpu/v7`  | GKE TPU                                                         |
| CPU            | `cpu`     | Intel/AMD, 64 cores + 64GB RAM per replica                      |

> [!NOTE]
> Some hardware variants use reduced configurations (fewer replicas, smaller
> models) to enable CI testing for compatibility and regression checks. These
> configurations are maintained by their respective hardware vendors and are
> not guaranteed as production-ready examples. Users deploying on non-default
> hardware should review and adjust the configurations for their environment.

## Prerequisites

- Have the [proper client tools installed on your local system](../../helpers/client-setup/README.md) to use this guide.

- Checkout the llm-d repo:

<!-- step ci=skip -->
```bash
export BRANCH=main # branch, tag, or commit hash
git clone https://github.com/llm-d/llm-d.git && cd llm-d && git checkout ${BRANCH}
```

- Set the guide specific environment variables:

<!-- step -->
```bash
export GUIDE_NAME=optimized-baseline
export NAMESPACE=llm-d-optimized-baseline
export HF_TOKEN=HF_TOKEN_PLACEHOLDER
export MODEL={{ model }}
export CURL_TEST_IMAGE=cfmanteiga/alpine-bash-curl-jq:latest
export BENCHMARK_REF=main
export HARNESS=inference-perf
export WORKLOAD=guide_optimized-baseline_1.yaml
```

> [!NOTE]
> `HF_TOKEN` must be a [valid HuggingFace token](../../helpers/hf-token.md);
> replace `HF_TOKEN_PLACEHOLDER` with your real token.

- Source the common guide environment variables:

<!-- step -->
```bash
export REPO_ROOT=$(realpath $(git rev-parse --show-toplevel))
source ${REPO_ROOT}/guides/env.sh
```

> [!NOTE]
> Some environment variables are common amongst guides; inspect the file
> sourced above so the rest of the guide makes sense.

- Install the Gateway API Inference Extension CRDs:

<!-- step -->
```bash
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api-inference-extension/releases/download/${GAIE_VERSION}/v1-manifests.yaml
```

- Create a target namespace for the installation:

<!-- step -->
```bash
kubectl create namespace ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -
```

- [Create the `llm-d-hf-token` secret in your target namespace with the key `HF_TOKEN` matching a valid HuggingFace token](../../helpers/hf-token.md) to pull models:

<!-- step ci=skip -->
```bash
kubectl create secret generic llm-d-hf-token \
  --from-literal="HF_TOKEN=${HF_TOKEN}" \
  --namespace "${NAMESPACE}" \
  --dry-run=client -o yaml | kubectl apply -f -
```

## Installation Instructions

### 1. Deploy the llm-d Router

- Define the guide-specific `helm` values file for the `llm-d` router:

<!-- when model_server=vllm|sglang -->
<!-- step -->
```bash
export ROUTER_VALUES="-f ${REPO_ROOT}/guides/${GUIDE_NAME}/router/${GUIDE_NAME}.values.yaml"
```

> [!NOTE]
> **vLLM and SGLang** share a values file, while **TensorRT-LLM**
> (`trtllm-serve`) has its own values file.
<!-- end -->
<!-- when model_server=trtllm -->
<details><summary><em>Alternative — Model server: trtllm</em></summary>

<!-- step -->
```bash
export ROUTER_VALUES="-f ${REPO_ROOT}/guides/${GUIDE_NAME}/router/${GUIDE_NAME}-trtllm.values.yaml"
```

</details>
<!-- end -->

- Define the base `helm` values for the `llm-d` router (guide-specific values
  in `ROUTER_VALUES` were set above):

<!-- step -->
```bash
export ROUTER_BASE_VALUES="-f ${REPO_ROOT}/guides/recipes/router/base.values.yaml"
```

<!-- when monitoring=off -->
<!-- step -->
```bash
export MONITORING_VALUES=""
```
<!-- end -->
<!-- when monitoring=on -->
<details><summary><em>Alternative — Prometheus monitoring: on</em></summary>

- Enable `Prometheus Monitoring` on the router (requires the
  [Monitoring stack](../../docs/operations/observability/setup.md)):

<!-- step -->
```bash
export MONITORING_VALUES="-f ${REPO_ROOT}/guides/recipes/router/features/monitoring.values.yaml"
```

</details>
<!-- end -->

<!-- when router_mode=standalone -->
This deploys the llm-d Router in
[Standalone Mode](../../docs/architecture/core/router/proxy.md):

<!-- step -->
```bash
helm install ${GUIDE_NAME} \
  ${ROUTER_STANDALONE_CHART} \
  ${ROUTER_BASE_VALUES} \
  ${MONITORING_VALUES} \
  ${ROUTER_VALUES} \
  -n ${NAMESPACE} --version ${ROUTER_CHART_VERSION}
```
<!-- end -->
<!-- when router_mode=gateway -->
<details><summary><em>Alternative — Router mode: gateway</em></summary>

This uses a Kubernetes Gateway managed proxy rather than the standalone
router. Set the Gateway provider, then install a Gateway implementation (see
the [gateway guides](../../docs/infrastructure/gateway) for provider
specifics) and create the Gateway:

<!-- step -->
```bash
export PROVIDER_NAME=gke # options: none, gke, agentgateway, istio
```

<!-- step -->
```bash
helm upgrade -i llm-d-inference-gateway ${REPO_ROOT}/guides/recipes/gateway/ \
  --set gateway.name=llm-d-inference-gateway \
  --set gateway.class=${PROVIDER_NAME} \
  -n ${NAMESPACE}
```

Wait for the Gateway to be programmed:

<!-- step -->
```bash
kubectl wait --for=condition=Programmed gateway/llm-d-inference-gateway \
  -n ${NAMESPACE} --timeout=300s
```

Then deploy the llm-d router and an HTTPRoute that connects it to the Gateway:

<!-- step -->
```bash
helm install ${GUIDE_NAME} \
  ${ROUTER_GATEWAY_CHART} \
  ${ROUTER_BASE_VALUES} \
  ${MONITORING_VALUES} \
  ${ROUTER_VALUES} \
  --set provider.name=${PROVIDER_NAME} \
  --set httpRoute.create=true \
  --set httpRoute.inferenceGatewayName=llm-d-inference-gateway \
  -n ${NAMESPACE} --version ${ROUTER_CHART_VERSION}
```

</details>
<!-- end -->

Wait for the router rollout to complete before continuing:

<!-- step -->
```bash
kubectl rollout status deployment -l app.kubernetes.io/instance=${GUIDE_NAME} \
  -n ${NAMESPACE} --timeout=300s
```

### 2. Deploy the Model Server ({{ accelerator }} / {{ model_server }})

- Select the Kustomize overlay for this configuration:

<!-- when accelerator=gpu model=Qwen/Qwen3-32B -->
<!-- step -->
```bash
export KUSTOMIZE_DIR=${REPO_ROOT}/guides/${GUIDE_NAME}/modelserver/gpu/{{ model_server }}/{{ infra_provider }}/
```
<!-- end -->
<!-- when model=openai/gpt-oss-120b -->
<details><summary><em>Alternative — Model: openai/gpt-oss-120b</em></summary>

<!-- step -->
```bash
export KUSTOMIZE_DIR=${REPO_ROOT}/guides/${GUIDE_NAME}/modelserver/gpu/vllm/gpt-oss/
```

</details>
<!-- end -->
<!-- when accelerator=amd|xpu|hpu|tpu/v6|tpu/v7|cpu -->
<details><summary><em>Alternative — Accelerator: amd|xpu|hpu|tpu/v6|tpu/v7|cpu</em></summary>

<!-- step -->
```bash
export KUSTOMIZE_DIR=${REPO_ROOT}/guides/${GUIDE_NAME}/modelserver/{{ accelerator }}/{{ model_server }}/
```

</details>
<!-- end -->

Apply the Kustomize overlay selected above (`KUSTOMIZE_DIR` — the same
variable tears the model server down in Cleanup):

<!-- step -->
```bash
kubectl apply -n ${NAMESPACE} -k ${KUSTOMIZE_DIR}
```

Model servers pull the model on first start, which can take a while. Wait for
all pods to become ready:

<!-- step -->
```bash
kubectl wait --for=condition=Ready pod \
  -l llm-d.ai/inferenceServing=true \
  -n ${NAMESPACE} --timeout=1800s
```

<!-- when monitoring=on -->
<details><summary><em>Alternative — Prometheus monitoring: on</em></summary>

#### Enable monitoring for model servers

- Install the [Monitoring stack](../../docs/operations/observability/setup.md)
  if not already present; `Prometheus Monitoring` was enabled on the router
  via `MONITORING_VALUES` above.

- Deploy the monitoring resources for model servers:

<!-- step -->
```bash
kubectl apply -n ${NAMESPACE} -k ${REPO_ROOT}/guides/recipes/modelserver/components/monitoring
```

</details>
<!-- end -->

## Adapting to other hardware

The routing plugins ship with defaults tuned for this guide's reference setup
(Qwen3-32B on H100 80&nbsp;GB, TP=2), so **no calibration is needed to run the
guide as written**.

The saturation-aware override gate in the `prefix-cache-affinity-filter` keys
off the filter's `peakPrefillThroughput` parameter, which is **hardware- and
model-specific** (the plugin default, `15928`, is the value measured for this
guide's setup). If you deploy a different model or accelerator, measure your
own value with the shared calibration recipe and set it on the filter:

```yaml
# guides/optimized-baseline/router/optimized-baseline.values.yaml
- type: prefix-cache-affinity-filter
  parameters:
    peakPrefillThroughput: <measured value>
```

The recipe (`calibrate.sh`) runs a short Kubernetes Job that measures true
prefill throughput against your live deployment and prints the value — it
does not modify any config. See the recipe's README for full usage:

- [`guides/recipes/router/calibration/README.md`](../recipes/router/calibration/README.md)

For reference values across the (model, accelerator) combinations shipped
under `guides/` — and which ones still need a calibration run — see the
[**configuration matrix**](../recipes/router/calibration/configuration-matrix.md).

## Verification

### 1. Get the IP of the Proxy

<!-- when router_mode=standalone -->
**Standalone Mode**

<!-- step -->
```bash
export IP=$(kubectl get service ${GUIDE_NAME}-epp -n ${NAMESPACE} -o jsonpath='{.spec.clusterIP}')
```
<!-- end -->
<!-- when router_mode=gateway -->
<details><summary><em>Alternative — Router mode: gateway</em></summary>

**Gateway Mode**

<!-- step -->
```bash
export IP=$(kubectl get gateway llm-d-inference-gateway -n ${NAMESPACE} -o jsonpath='{.status.addresses[0].value}')
```

</details>
<!-- end -->

### 2. Send a Test Request

Open a temporary interactive shell inside the cluster and send a completion
request (model-aware; `MODEL` is set in the environment section above):

<!-- step -->
```bash
kubectl run curl-test --rm -i --restart=Never \
  --image=${CURL_TEST_IMAGE} \
  --namespace="${NAMESPACE}" \
  --env="IP=${IP}" \
  --env="MODEL=${MODEL}" \
  -- /bin/sh -c 'curl -sS -X POST "http://${IP}/v1/completions" -H "Content-Type: application/json" -d "{\"model\": \"${MODEL}\", \"prompt\": \"How are you today?\"}"'
```

## Benchmarking

> [!TIP]
> `guide_optimized-baseline_1.yaml` (the `WORKLOAD` set in the environment
> section) is this guide's **dedicated** benchmark profile — it drives
> [`inference-perf`](https://github.com/kubernetes-sigs/inference-perf) with a
> shared-prefix synthetic workload, reproducing the load ladder used to
> generate the [reports below](#benchmarking-reports) (rates 3 to 60), and
> takes correspondingly long. To validate the path first (image pulls, PVC
> binding, etc.), substitute a generic sample profile such as
> `shared_prefix_synthetic.yaml` from the catalog in
> [`helpers/benchmark.md`](../../helpers/benchmark.md#available-workload-profiles).

This guide uses [`llmdbenchmark`](https://github.com/llm-d/llm-d-benchmark) —
the supported standard CLI for llm-d performance benchmarking. The CLI
automatically deploys a harness pod (`llmdbench-harness-launcher`) into your
namespace to drive the workload (the `HARNESS` and `WORKLOAD` set in the
environment section), collect the results, and tear itself down when
finished.

> [!IMPORTANT]
> A more in-depth explanation and features for benchmarking llm-d guides can
> be found at [`helpers/benchmark.md`](../../helpers/benchmark.md) — start
> there when something goes wrong. For even more details see
> [`llm-d-benchmark` on GitHub](https://github.com/llm-d/llm-d-benchmark).

### 1. Install the CLI

Automatically clone the benchmark repository into `./llm-d-benchmark/` and
create a virtualenv at `./llm-d-benchmark/.venv/` containing dependencies:

<!-- step -->
```bash
curl -sSL https://raw.githubusercontent.com/llm-d/llm-d-benchmark/${BENCHMARK_REF}/install.sh | bash
```

<!-- step -->
```bash
cd llm-d-benchmark
source .venv/bin/activate
llmdbenchmark --version
```

> [!NOTE]
> Subsequent `llmdbenchmark` commands assume you are inside the
> `llm-d-benchmark` repo directory with the `venv` activated. If you open a
> new shell, re-run the commands above.

### 2. Resolve the endpoint of the stack you just deployed

Get the proxy IP, then set the endpoint URL and the gateway class (which
tells the CLI which deployment topology the cluster is actually running):

<!-- when router_mode=standalone -->
**Standalone Mode**

<!-- step -->
```bash
export IP=$(kubectl get service ${GUIDE_NAME}-epp -n ${NAMESPACE} -o jsonpath='{.spec.clusterIP}')
```
<!-- end -->
<!-- when router_mode=gateway -->
<details><summary><em>Alternative — Router mode: gateway</em></summary>

**Gateway Mode**

<!-- step -->
```bash
export IP=$(kubectl get gateway llm-d-inference-gateway -n ${NAMESPACE} -o jsonpath='{.status.addresses[0].value}')
```

</details>
<!-- end -->

<!-- step -->
```bash
export ENDPOINT_URL="http://${IP}"
```

<!-- when router_mode=standalone -->
<!-- step -->
```bash
export GATEWAY_CLASS="epponly"
```
<!-- end -->
<!-- when router_mode=gateway -->
<details><summary><em>Alternative — Router mode: gateway</em></summary>

Match the provider you used when deploying the gateway:

<!-- step -->
```bash
export GATEWAY_CLASS="${PROVIDER_NAME}"
```

</details>
<!-- end -->

### 3. Run the benchmark profile

Benchmark results are copied to the `workspace` directory on the machine
running the CLI; by default the CLI auto-generates a timestamped workspace and
prints its full path in the logs. Pass `--workspace <DIR>` (before the `run`
subcommand) to choose where results land.

<!-- step -->
```bash
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
```

> [!NOTE]
> Depending on your cluster you may need to extend the default timeout values;
> `bind`, `access` and `wait-timeout` times of PVCs and pods can be arbitrarily
> slower on some systems — see `llmdbenchmark run --help` for the knobs.

## Cleanup

To remove the deployed components:

- Uninstall the llm-d router:

<!-- step -->
```bash
helm uninstall ${GUIDE_NAME} -n ${NAMESPACE}
```

- Remove the model server resources (same `KUSTOMIZE_DIR` used to install):

<!-- step -->
```bash
kubectl delete -n ${NAMESPACE} -k ${KUSTOMIZE_DIR} --ignore-not-found=true
```

<!-- when monitoring=on -->
<details><summary><em>Alternative — Prometheus monitoring: on</em></summary>

- Remove the monitoring resources:

<!-- step -->
```bash
kubectl delete -n ${NAMESPACE} -k ${REPO_ROOT}/guides/recipes/modelserver/components/monitoring --ignore-not-found=true
```

</details>
<!-- end -->

- Delete the namespace:

<!-- step -->
```bash
kubectl delete namespace ${NAMESPACE}
```

## Benchmarking Reports

Empirical benchmark reports comparing llm-d routing performance against a
standard Kubernetes Service under identical hardware configurations:

- [Qwen/Qwen3-32B on H100 and SGLang](./benchmark-results/sglang-qwen3-32b-h100/README.md)
- [Qwen/Qwen3-32B on H100 and vLLM](./benchmark-results/vllm-qwen3-32b-h100/README.md)
- [openai/gpt-oss-120b on H100 and vLLM](./benchmark-results/vllm-gpt-oss-120b-h100/README.md)
