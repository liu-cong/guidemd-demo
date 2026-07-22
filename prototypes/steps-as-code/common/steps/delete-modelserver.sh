#!/usr/bin/env bash
# tags: dry-run=skip

kubectl delete -n ${NAMESPACE} -k ${KUSTOMIZE_DIR} --ignore-not-found=true
