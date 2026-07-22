- Uninstall the llm-d router:

<!-- step dry-run=skip -->
```bash
helm uninstall ${GUIDE_NAME} -n ${NAMESPACE}
```

- Remove the model server resources (same `KUSTOMIZE_DIR` used to install):

<!-- step dry-run=skip -->
```bash
kubectl delete -n ${NAMESPACE} -k ${KUSTOMIZE_DIR} --ignore-not-found=true
```

<!-- when monitoring=on -->
- Remove the monitoring resources:

<!-- step dry-run=skip -->
```bash
kubectl delete -n ${NAMESPACE} -k ${REPO_ROOT}/guides/recipes/modelserver/components/monitoring --ignore-not-found=true
```
<!-- end -->

- Delete the namespace:

<!-- step dry-run=skip -->
```bash
kubectl delete namespace ${NAMESPACE}
```
