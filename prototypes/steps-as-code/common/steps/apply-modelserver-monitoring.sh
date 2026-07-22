#!/usr/bin/env bash
# tags: dry-run=skip

kubectl apply -n ${NAMESPACE} -k ${REPO_ROOT}/guides/recipes/modelserver/components/monitoring
