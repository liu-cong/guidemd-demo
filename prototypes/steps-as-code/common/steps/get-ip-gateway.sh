#!/usr/bin/env bash
# tags: dry-run=skip
# group: router-ip

export IP=$(kubectl get gateway ${GATEWAY_NAME} -n ${NAMESPACE} -o jsonpath='{.status.addresses[0].value}')
