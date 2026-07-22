#!/usr/bin/env bash
# tags: e2e=skip

curl -sfL https://github.com/kubernetes-sigs/gateway-api-inference-extension/releases/download/${GAIE_VERSION}/v1-manifests.yaml -o /dev/null
