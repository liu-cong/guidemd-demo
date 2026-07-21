Apply the Kustomize overlay selected above (`KUSTOMIZE_DIR` — the same
variable tears the model server down in Cleanup):

<!-- step dry-run=skip -->
```bash
kubectl apply -n ${NAMESPACE} -k ${KUSTOMIZE_DIR}
```

<!-- step e2e=skip hide=true -->
```bash
kubectl kustomize ${KUSTOMIZE_DIR} > /dev/null
```

Model servers pull the model on first start, which can take a while. Wait for
all pods to become ready:

<!-- step dry-run=skip -->
```bash
kubectl wait --for=condition=Ready pod \
  -l llm-d.ai/inferenceServing=true \
  -n ${NAMESPACE} --timeout=1800s
```

<!-- when monitoring=on -->
#### Enable monitoring for model servers

- Install the [Monitoring stack](../../docs/operations/observability/setup.md)
  if not already present; `Prometheus Monitoring` was enabled on the router
  via `MONITORING_VALUES` above.

- Deploy the monitoring resources for model servers:

<!-- step dry-run=skip -->
```bash
kubectl apply -n ${NAMESPACE} -k ${REPO_ROOT}/guides/recipes/modelserver/components/monitoring
```

<!-- step e2e=skip hide=true -->
```bash
kubectl kustomize ${REPO_ROOT}/guides/recipes/modelserver/components/monitoring > /dev/null
```
<!-- end -->
