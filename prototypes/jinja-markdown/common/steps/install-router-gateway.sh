#!/usr/bin/env bash
# tags: dry-run=skip

helm install ${GUIDE_NAME} \
  ${ROUTER_GATEWAY_CHART} \
  ${ROUTER_BASE_VALUES} \
  ${MONITORING_VALUES} \
  ${ROUTER_VALUES} \
  --set provider.name=${GATEWAY_PROVIDER} \
  --set httpRoute.create=true \
  --set httpRoute.inferenceGatewayName=${GATEWAY_NAME} \
  -n ${NAMESPACE} --version ${ROUTER_CHART_VERSION}
