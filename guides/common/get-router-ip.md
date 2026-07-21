<!-- when router_mode=standalone -->
**Standalone Mode**

<!-- step dry-run=skip -->
```bash
export IP=$(kubectl get service ${GUIDE_NAME}-epp -n ${NAMESPACE} -o jsonpath='{.spec.clusterIP}')
```
<!-- end -->
<!-- when router_mode=gateway -->
**Gateway Mode**

<!-- step dry-run=skip -->
```bash
export IP=$(kubectl get gateway {{ gateway_name }} -n ${NAMESPACE} -o jsonpath='{.status.addresses[0].value}')
```
<!-- end -->
