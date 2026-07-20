### 1. Get the IP of the Proxy

<!-- import get-router-ip.md -->

### 2. Send a Test Request

Open a temporary interactive shell inside the cluster and send a completion
request (model-aware; `MODEL` is set in the environment section above):

<!-- step dry-run=skip -->
```bash
kubectl run curl-test --rm -i --restart=Never \
  --image=${CURL_TEST_IMAGE} \
  --namespace="${NAMESPACE}" \
  --env="IP=${IP}" \
  --env="MODEL=${MODEL}" \
  -- /bin/sh -c 'curl -sS -X POST "http://${IP}/v1/completions" -H "Content-Type: application/json" -d "{\"model\": \"${MODEL}\", \"prompt\": \"How are you today?\"}"'
```
