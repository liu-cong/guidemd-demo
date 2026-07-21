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

<!-- step dry-run=skip -->
```bash
helm install ${GUIDE_NAME} \
  ${ROUTER_STANDALONE_CHART} \
  ${ROUTER_BASE_VALUES} \
  ${MONITORING_VALUES} \
  ${ROUTER_VALUES} \
  -n ${NAMESPACE} --version ${ROUTER_CHART_VERSION}
```

<!-- step e2e=skip hide=true -->
```bash
helm template ${GUIDE_NAME} \
  ${ROUTER_STANDALONE_CHART} \
  ${ROUTER_BASE_VALUES} \
  ${MONITORING_VALUES} \
  ${ROUTER_VALUES} \
  --version ${ROUTER_CHART_VERSION} > /dev/null
```
<!-- end -->
<!-- when router_mode=gateway -->
This uses a Kubernetes Gateway managed proxy rather than the standalone
router, with the **{{ gateway_provider }}** Gateway implementation (your
pick in the configuration above; see the
[gateway guides](../../docs/infrastructure/gateway) for provider specifics).
Install the Gateway:

<!-- step dry-run=skip -->
```bash
helm upgrade -i {{ gateway_name }} ${REPO_ROOT}/guides/recipes/gateway/ \
  --set gateway.name={{ gateway_name }} \
  --set gateway.class={{ gateway_provider }} \
  -n ${NAMESPACE}
```

<!-- step e2e=skip hide=true -->
```bash
helm template {{ gateway_name }} ${REPO_ROOT}/guides/recipes/gateway/ \
  --set gateway.name={{ gateway_name }} \
  --set gateway.class={{ gateway_provider }} > /dev/null
```

Wait for the Gateway to be programmed:

<!-- step dry-run=skip -->
```bash
kubectl wait --for=condition=Programmed gateway/{{ gateway_name }} \
  -n ${NAMESPACE} --timeout=300s
```

Then deploy the llm-d router and an HTTPRoute that connects it to the Gateway:

<!-- step dry-run=skip -->
```bash
helm install ${GUIDE_NAME} \
  ${ROUTER_GATEWAY_CHART} \
  ${ROUTER_BASE_VALUES} \
  ${MONITORING_VALUES} \
  ${ROUTER_VALUES} \
  --set provider.name={{ gateway_provider }} \
  --set httpRoute.create=true \
  --set httpRoute.inferenceGatewayName={{ gateway_name }} \
  -n ${NAMESPACE} --version ${ROUTER_CHART_VERSION}
```

<!-- step e2e=skip hide=true -->
```bash
helm template ${GUIDE_NAME} \
  ${ROUTER_GATEWAY_CHART} \
  ${ROUTER_BASE_VALUES} \
  ${MONITORING_VALUES} \
  ${ROUTER_VALUES} \
  --set provider.name={{ gateway_provider }} \
  --set httpRoute.create=true \
  --set httpRoute.inferenceGatewayName={{ gateway_name }} \
  --version ${ROUTER_CHART_VERSION} > /dev/null
```
<!-- end -->

Wait for the router rollout to complete before continuing:

<!-- step dry-run=skip -->
```bash
kubectl rollout status deployment -l app.kubernetes.io/instance=${GUIDE_NAME} \
  -n ${NAMESPACE} --timeout=300s
```
