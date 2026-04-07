#!/bin/bash
# Deploy TCGA preprocessing for COAD project

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHART_DIR="$(cd "${SCRIPT_DIR}/../../../charts/data-service/tcga" && pwd)"
VALUES_FILE="${SCRIPT_DIR}/values.yaml"

RELEASE_NAME="${RELEASE_NAME:-tcga-coad}"
NAMESPACE="${NAMESPACE:-kubeflow-user-example-com}"

echo "=========================================="
echo "TCGA Preprocessing Deployment"
echo "=========================================="
echo "Release Name: ${RELEASE_NAME}"
echo "Namespace: ${NAMESPACE}"
echo "Chart: ${CHART_DIR}"
echo "Values: ${VALUES_FILE}"
echo "=========================================="
echo ""

# Check if namespace exists
if ! kubectl get namespace "${NAMESPACE}" &> /dev/null; then
    echo "Creating namespace ${NAMESPACE}..."
    kubectl create namespace "${NAMESPACE}"
fi

# Check if PVCs exist
echo "Checking for required PVCs..."
if ! kubectl get pvc pv-efs -n "${NAMESPACE}" &> /dev/null; then
    echo "WARNING: PVC 'pv-efs' not found in namespace ${NAMESPACE}"
    echo "Please ensure EFS PVC is created before running this job"
fi

if ! kubectl get pvc pv-fsx -n "${NAMESPACE}" &> /dev/null; then
    echo "WARNING: PVC 'pv-fsx' not found in namespace ${NAMESPACE}"
    echo "FSx PVC is optional but recommended for better performance"
fi

echo ""
echo "Deploying Helm chart..."
helm upgrade --install "${RELEASE_NAME}" "${CHART_DIR}" \
    --namespace "${NAMESPACE}" \
    --values "${VALUES_FILE}" \
    --wait \
    --timeout 10m

echo ""
echo "=========================================="
echo "Deployment complete!"
echo "=========================================="
echo ""
echo "Monitor job status:"
echo "  kubectl get jobs -n ${NAMESPACE} -l app.kubernetes.io/instance=${RELEASE_NAME}"
echo ""
echo "View logs:"
echo "  kubectl logs -n ${NAMESPACE} -l app.kubernetes.io/instance=${RELEASE_NAME} --follow"
echo ""
echo "Check job details:"
echo "  kubectl describe job -n ${NAMESPACE} ${RELEASE_NAME}-tcga"
echo ""
echo "Delete job when complete:"
echo "  helm uninstall ${RELEASE_NAME} -n ${NAMESPACE}"
echo ""
