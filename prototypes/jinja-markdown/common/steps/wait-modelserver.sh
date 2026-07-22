#!/usr/bin/env bash
# tags: dry-run=skip

kubectl wait --for=condition=Ready pod \
  -l llm-d.ai/inferenceServing=true \
  -n ${NAMESPACE} --timeout=1800s
