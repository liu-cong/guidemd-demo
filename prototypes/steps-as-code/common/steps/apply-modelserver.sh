#!/usr/bin/env bash
# tags: dry-run=skip

kubectl apply -n ${NAMESPACE} -k ${KUSTOMIZE_DIR}
