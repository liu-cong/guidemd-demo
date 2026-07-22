#!/usr/bin/env bash
# tags: dry-run=skip

kubectl wait --for=condition=Programmed gateway/${GATEWAY_NAME} \
  -n ${NAMESPACE} --timeout=300s
