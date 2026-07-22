#!/usr/bin/env bash
# tags: e2e=skip

kubectl create namespace ${NAMESPACE} --dry-run=client -o yaml > /dev/null
