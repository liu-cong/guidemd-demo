- Uninstall the llm-d router:

<!-- step -->
```bash
helm uninstall ${GUIDE_NAME} -n ${NAMESPACE}
```

- Remove the model server resources (same `KUSTOMIZE_DIR` used to install):

<!-- step -->
```bash
kubectl delete -n ${NAMESPACE} -k ${KUSTOMIZE_DIR} --ignore-not-found=true
```

<!-- when monitoring=on -->
- Remove the monitoring resources:

<!-- step -->
```bash
kubectl delete -n ${NAMESPACE} -k ${REPO_ROOT}/guides/recipes/modelserver/components/monitoring --ignore-not-found=true
```
<!-- end -->

- Delete the namespace:

<!-- step -->
```bash
kubectl delete namespace ${NAMESPACE}
```
