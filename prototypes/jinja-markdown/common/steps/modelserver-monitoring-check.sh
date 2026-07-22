#!/usr/bin/env bash
# tags: e2e=skip

kubectl kustomize ${REPO_ROOT}/guides/recipes/modelserver/components/monitoring > /dev/null
