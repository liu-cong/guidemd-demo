#!/usr/bin/env bash
# tags: e2e=skip

helm template ${GUIDE_NAME} \
  ${ROUTER_GATEWAY_CHART} \
  ${ROUTER_BASE_VALUES} \
  ${MONITORING_VALUES} \
  ${ROUTER_VALUES} \
  --set provider.name=${GATEWAY_PROVIDER} \
  --set httpRoute.create=true \
  --set httpRoute.inferenceGatewayName=${GATEWAY_NAME} \
  --version ${ROUTER_CHART_VERSION} > /dev/null
