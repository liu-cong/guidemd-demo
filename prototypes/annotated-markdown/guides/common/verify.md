### 1. Get the IP of the Proxy

<!-- import get-router-ip.md gateway_name="{{ gateway_name }}" -->

### 2. Send a Test Request

Open a temporary interactive shell inside the cluster and send a completion
request (model-aware; `MODEL` is set in the environment section above). The
step **fails with a non-zero exit** unless the router returns an actual
completion — the same assertion gates the CI e2e run:

<!-- step dry-run=skip -->
```bash
kubectl run curl-test --rm -i --restart=Never \
  --image=${CURL_TEST_IMAGE} \
  --namespace="${NAMESPACE}" \
  --env="IP=${IP}" \
  --env="MODEL=${MODEL}" \
  -- /bin/sh -c 'RESP=$(curl -fsS -X POST "http://${IP}/v1/completions" -H "Content-Type: application/json" -d "{\"model\": \"${MODEL}\", \"prompt\": \"How are you today?\"}") && echo "${RESP}" && echo "${RESP}" | jq -e ".choices[0].text" > /dev/null && echo "verification passed"'
```

### 3. Debugging interactively (optional)

To poke around by hand instead, open a temporary interactive shell inside
the cluster (interactive — not part of the executable plan):

```console
kubectl run curl-debug --rm -it \
    --image=cfmanteiga/alpine-bash-curl-jq \
    --namespace="$NAMESPACE" \
    --env="IP=$IP" \
    --env="NAMESPACE=$NAMESPACE" \
    -- /bin/bash
```

then send a completion request (model-aware; set `model` to the name you
want to query, e.g. `Qwen/Qwen3-32B` or `openai/gpt-oss-120b`):

```console
curl -X POST http://${IP}/v1/completions \
    -H 'Content-Type: application/json' \
    -d '{
        "model": "Qwen/Qwen3-32B",
        "prompt": "How are you today?"
    }' | jq
```
