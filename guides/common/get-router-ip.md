<!-- when router_mode=standalone -->
**Standalone Mode**

<!-- step -->
```bash
export IP=$(kubectl get service ${GUIDE_NAME}-epp -n ${NAMESPACE} -o jsonpath='{.spec.clusterIP}')
```
<!-- end -->
<!-- when router_mode=gateway -->
**Gateway Mode**

<!-- step -->
```bash
export IP=$(kubectl get gateway llm-d-inference-gateway -n ${NAMESPACE} -o jsonpath='{.status.addresses[0].value}')
```
<!-- end -->
