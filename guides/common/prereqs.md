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
export GUIDE_NAME={{ guide_name }}
export NAMESPACE=llm-d-{{ guide_name }}
export HF_TOKEN=HF_TOKEN_PLACEHOLDER
export MODEL={{ model }}
export CURL_TEST_IMAGE=cfmanteiga/alpine-bash-curl-jq:latest
export BENCHMARK_REF=main
export HARNESS=inference-perf
export WORKLOAD={{ workload }}
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
