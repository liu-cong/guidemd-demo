#!/usr/bin/env bash
# tags: dry-run=skip

helm upgrade -i ${GATEWAY_NAME} ${REPO_ROOT}/guides/recipes/gateway/ \
  --set gateway.name=${GATEWAY_NAME} \
  --set gateway.class=${GATEWAY_PROVIDER} \
  -n ${NAMESPACE}
