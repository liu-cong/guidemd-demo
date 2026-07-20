- Define the base `helm` values for the `llm-d` router (guide-specific values
  in `ROUTER_VALUES` were set above):

<!-- step -->
```bash
export ROUTER_BASE_VALUES="-f ${REPO_ROOT}/guides/recipes/router/base.values.yaml"
```

<!-- when monitoring=off -->
<!-- step -->
```bash
export MONITORING_VALUES=""
```
<!-- end -->
<!-- when monitoring=on -->
- Enable `Prometheus Monitoring` on the router (requires the
  [Monitoring stack](../../docs/operations/observability/setup.md)):

<!-- step -->
```bash
export MONITORING_VALUES="-f ${REPO_ROOT}/guides/recipes/router/features/monitoring.values.yaml"
```
<!-- end -->

<!-- when router_mode=standalone -->
This deploys the llm-d Router in
[Standalone Mode](../../docs/architecture/core/router/proxy.md):

<!-- step -->
```bash
helm install ${GUIDE_NAME} \
  ${ROUTER_STANDALONE_CHART} \
  ${ROUTER_BASE_VALUES} \
  ${MONITORING_VALUES} \
  ${ROUTER_VALUES} \
  -n ${NAMESPACE} --version ${ROUTER_CHART_VERSION}
```
<!-- end -->
<!-- when router_mode=gateway -->
This uses a Kubernetes Gateway managed proxy rather than the standalone
router. Set the Gateway provider, then install a Gateway implementation (see
the [gateway guides](../../docs/infrastructure/gateway) for provider
specifics) and create the Gateway:

<!-- step -->
```bash
export PROVIDER_NAME=gke # options: none, gke, agentgateway, istio
```

<!-- step -->
```bash
helm upgrade -i {{ gateway_name }} ${REPO_ROOT}/guides/recipes/gateway/ \
  --set gateway.name={{ gateway_name }} \
  --set gateway.class=${PROVIDER_NAME} \
  -n ${NAMESPACE}
```

Wait for the Gateway to be programmed:

<!-- step -->
```bash
kubectl wait --for=condition=Programmed gateway/{{ gateway_name }} \
  -n ${NAMESPACE} --timeout=300s
```

Then deploy the llm-d router and an HTTPRoute that connects it to the Gateway:

<!-- step -->
```bash
helm install ${GUIDE_NAME} \
  ${ROUTER_GATEWAY_CHART} \
  ${ROUTER_BASE_VALUES} \
  ${MONITORING_VALUES} \
  ${ROUTER_VALUES} \
  --set provider.name=${PROVIDER_NAME} \
  --set httpRoute.create=true \
  --set httpRoute.inferenceGatewayName={{ gateway_name }} \
  -n ${NAMESPACE} --version ${ROUTER_CHART_VERSION}
```
<!-- end -->

Wait for the router rollout to complete before continuing:

<!-- step -->
```bash
kubectl rollout status deployment -l app.kubernetes.io/instance=${GUIDE_NAME} \
  -n ${NAMESPACE} --timeout=300s
```
