#!/usr/bin/env bash
# tags: dry-run=skip

kubectl rollout status deployment -l app.kubernetes.io/instance=${GUIDE_NAME} \
  -n ${NAMESPACE} --timeout=300s
