#!/usr/bin/env bash
# tags: e2e=skip

helm template ${GATEWAY_NAME} ${REPO_ROOT}/guides/recipes/gateway/ \
  --set gateway.name=${GATEWAY_NAME} \
  --set gateway.class=${GATEWAY_PROVIDER} > /dev/null
