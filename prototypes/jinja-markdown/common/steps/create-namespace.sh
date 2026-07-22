#!/usr/bin/env bash
# tags: dry-run=skip

kubectl create namespace ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -
