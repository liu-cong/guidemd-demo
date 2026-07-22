#!/usr/bin/env bash
# tags: e2e=skip

helm template ${GUIDE_NAME} \
  ${ROUTER_STANDALONE_CHART} \
  ${ROUTER_BASE_VALUES} \
  ${MONITORING_VALUES} \
  ${ROUTER_VALUES} \
  --version ${ROUTER_CHART_VERSION} > /dev/null
