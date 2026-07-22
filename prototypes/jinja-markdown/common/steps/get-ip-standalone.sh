#!/usr/bin/env bash
# tags: dry-run=skip
# group: router-ip

export IP=$(kubectl get service ${GUIDE_NAME}-epp -n ${NAMESPACE} -o jsonpath='{.spec.clusterIP}')
