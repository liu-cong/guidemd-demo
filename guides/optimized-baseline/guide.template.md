---
guide:
  name: optimized-baseline
  title: Optimized Baseline
  # Declaration order = pick order. The options available for each dimension
  # are narrowed by the picks above it (see rules). First value = default.
  dimensions:
    infra_provider:
      label: Infra provider
      values: [base, gke]
    router_mode:
      label: Router mode
      values: [standalone, gateway]
    accelerator:
      label: Accelerator
      values: [gpu, amd, xpu, hpu, tpu/v6, tpu/v7, cpu]
    model_server:
      label: Model server
      values: [vllm, sglang, trtllm]
    model:
      label: Model
      values: [Qwen/Qwen3-32B, openai/gpt-oss-120b]
    monitoring:
      label: Prometheus monitoring
      values: ["off", "on"]
  # Constraints instead of an exhaustive list: `when` (earlier dims) narrows
  # `allow` (later dims). Anything not restricted stays available.
  rules:
    - when:  { infra_provider: base }
      allow: { accelerator: [gpu, amd, xpu, hpu, cpu] }
    - when:  { infra_provider: gke }
      allow: { accelerator: [gpu, tpu/v6, tpu/v7] }
    - when:  { accelerator: [amd, xpu, hpu, tpu/v6, tpu/v7, cpu] }
      allow: { model_server: [vllm], model: [Qwen/Qwen3-32B] }
    - when:  { model_server: [sglang, trtllm] }
      allow: { model: [Qwen/Qwen3-32B] }
  # The tested matrix (mirrors the E2E badges). Every row is a complete,
  # flattened assignment of ALL dimensions — what you read is what CI runs.
  ci:
    - { infra_provider: base, router_mode: standalone, accelerator: gpu,    model_server: vllm,   model: Qwen/Qwen3-32B, monitoring: "off" }
    - { infra_provider: base, router_mode: standalone, accelerator: gpu,    model_server: vllm,   model: Qwen/Qwen3-32B, monitoring: "on"  }
    - { infra_provider: base, router_mode: gateway,    accelerator: gpu,    model_server: vllm,   model: Qwen/Qwen3-32B, monitoring: "off" }
    - { infra_provider: gke,  router_mode: standalone, accelerator: gpu,    model_server: vllm,   model: Qwen/Qwen3-32B, monitoring: "off" }
    - { infra_provider: gke,  router_mode: standalone, accelerator: tpu/v6, model_server: vllm,   model: Qwen/Qwen3-32B, monitoring: "off" }
    - { infra_provider: base, router_mode: standalone, accelerator: amd,    model_server: vllm,   model: Qwen/Qwen3-32B, monitoring: "off" }
    - { infra_provider: base, router_mode: standalone, accelerator: xpu,    model_server: vllm,   model: Qwen/Qwen3-32B, monitoring: "off" }
    - { infra_provider: base, router_mode: standalone, accelerator: gpu,    model_server: sglang, model: Qwen/Qwen3-32B, monitoring: "off" }
---

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

<!-- import ../common/prereqs.md guide_name=optimized-baseline workload=guide_optimized-baseline_1.yaml -->

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
<!-- step -->
```bash
export ROUTER_VALUES="-f ${REPO_ROOT}/guides/${GUIDE_NAME}/router/${GUIDE_NAME}-trtllm.values.yaml"
```
<!-- end -->

<!-- import ../common/install-router.md gateway_name=llm-d-inference-gateway -->

### 2. Deploy the Model Server ({{ accelerator }} / {{ model_server }})

- Select the Kustomize overlay for this configuration:

<!-- when accelerator=gpu model=Qwen/Qwen3-32B -->
<!-- step -->
```bash
export KUSTOMIZE_DIR=${REPO_ROOT}/guides/${GUIDE_NAME}/modelserver/gpu/{{ model_server }}/{{ infra_provider }}/
```
<!-- end -->
<!-- when model=openai/gpt-oss-120b -->
<!-- step -->
```bash
export KUSTOMIZE_DIR=${REPO_ROOT}/guides/${GUIDE_NAME}/modelserver/gpu/vllm/gpt-oss/
```
<!-- end -->
<!-- when accelerator=amd|xpu|hpu|tpu/v6|tpu/v7|cpu -->
<!-- step -->
```bash
export KUSTOMIZE_DIR=${REPO_ROOT}/guides/${GUIDE_NAME}/modelserver/{{ accelerator }}/{{ model_server }}/
```
<!-- end -->

<!-- import ../common/install-modelserver.md -->

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

<!-- import ../common/verify.md -->

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

<!-- import ../common/benchmark.md -->

## Cleanup

To remove the deployed components:

<!-- import ../common/cleanup.md -->

## Benchmarking Reports

Empirical benchmark reports comparing llm-d routing performance against a
standard Kubernetes Service under identical hardware configurations:

- [Qwen/Qwen3-32B on H100 and SGLang](./benchmark-results/sglang-qwen3-32b-h100/README.md)
- [Qwen/Qwen3-32B on H100 and vLLM](./benchmark-results/vllm-qwen3-32b-h100/README.md)
- [openai/gpt-oss-120b on H100 and vLLM](./benchmark-results/vllm-gpt-oss-120b-h100/README.md)
