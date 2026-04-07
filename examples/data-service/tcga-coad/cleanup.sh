#!/bin/bash
# Cleanup TCGA preprocessing job and optionally remove data

set -e

RELEASE_NAME="${RELEASE_NAME:-tcga-brca-coad-prad}"
NAMESPACE="${NAMESPACE:-kubeflow-user-example-com}"
REMOVE_DATA="${REMOVE_DATA:-false}"

echo "=========================================="
echo "TCGA Preprocessing Cleanup"
echo "=========================================="
echo "Release Name: ${RELEASE_NAME}"
echo "Namespace: ${NAMESPACE}"
echo "Remove Data: ${REMOVE_DATA}"
echo "=========================================="
echo ""

# Uninstall Helm release
if helm list -n "${NAMESPACE}" | grep -q "${RELEASE_NAME}"; then
    echo "Uninstalling Helm release ${RELEASE_NAME}..."
    helm uninstall "${RELEASE_NAME}" -n "${NAMESPACE}"
    echo "✓ Helm release uninstalled"
else
    echo "Helm release ${RELEASE_NAME} not found"
fi

# Optionally remove data
if [ "${REMOVE_DATA}" = "true" ]; then
    echo ""
    echo "WARNING: Removing processed data..."
    echo "This will delete /efs/home/${RELEASE_NAME}/"
    echo ""
    read -p "Are you sure? (yes/no): " -r
    if [[ $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        # Create a temporary pod to remove data
        kubectl run cleanup-pod-${RANDOM} \
            --image=busybox \
            --namespace="${NAMESPACE}" \
            --restart=Never \
            --rm -i \
            --overrides='
{
  "spec": {
    "containers": [{
      "name": "cleanup",
      "image": "busybox",
      "command": ["sh", "-c", "rm -rf /efs/home/'${RELEASE_NAME}'"],
      "volumeMounts": [{
        "name": "efs",
        "mountPath": "/efs"
      }]
    }],
    "volumes": [{
      "name": "efs",
      "persistentVolumeClaim": {
        "claimName": "pv-efs"
      }
    }]
  }
}'
        echo "✓ Data removed"
    else
        echo "Data removal cancelled"
    fi
fi

echo ""
echo "=========================================="
echo "Cleanup complete!"
echo "=========================================="
