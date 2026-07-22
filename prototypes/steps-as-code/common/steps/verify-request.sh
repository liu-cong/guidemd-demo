#!/usr/bin/env bash
# tags: dry-run=skip

kubectl run curl-test --rm -i --restart=Never \
  --image=${CURL_TEST_IMAGE} \
  --namespace="${NAMESPACE}" \
  --env="IP=${IP}" \
  --env="MODEL=${MODEL}" \
  -- /bin/sh -c 'RESP=$(curl -fsS -X POST "http://${IP}/v1/completions" -H "Content-Type: application/json" -d "{\"model\": \"${MODEL}\", \"prompt\": \"How are you today?\"}") && echo "${RESP}" && echo "${RESP}" | jq -e ".choices[0].text" > /dev/null && echo "verification passed"'
