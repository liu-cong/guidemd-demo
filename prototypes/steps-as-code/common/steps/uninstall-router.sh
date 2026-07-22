#!/usr/bin/env bash
# tags: dry-run=skip

helm uninstall ${GUIDE_NAME} -n ${NAMESPACE}
