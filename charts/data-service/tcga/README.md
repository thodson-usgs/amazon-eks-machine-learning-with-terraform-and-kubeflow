# TCGA Data Preprocessing Helm Chart

A Kubernetes-native Helm chart for preprocessing TCGA (The Cancer Genome Atlas) open-access data into analysis-ready Parquet files.

## Overview

This chart deploys a Kubernetes Job that:
- Downloads raw TCGA data from AWS Open Data Registry (`s3://tcga-2-open`)
- Fetches clinical metadata from the NCI GDC API
- Processes gene expression, mutations, copy number, and miRNA data
- Outputs clean, rectangular Parquet tables organized by cancer type

## Prerequisites

- Kubernetes cluster with EFS and/or FSx persistent volumes
- PVCs named `pv-efs` and `pv-fsx` (or customize in values)
- Network access to `s3://tcga-2-open` and `https://api.gdc.cancer.gov`
- Sufficient storage (50GB for a few projects, 500GB+ for all 33)

## Installation

### Process all 33 TCGA projects

```bash
helm install tcga-full charts/data-service/tcga \
  --namespace kubeflow \
  --create-namespace
```

### Process specific cancer types

```bash
helm install tcga-breast charts/data-service/tcga \
  --namespace kubeflow \
  --set tcga.projects="{TCGA-BRCA,TCGA-COAD,TCGA-PRAD}"
```

### Use custom output directory

```bash
helm install tcga-custom charts/data-service/tcga \
  --namespace kubeflow \
  --set tcga.outputDir=/efs/data/tcga_processed \
  --set tcga.rawDir=/fsx/data/tcga_raw
```

### Skip download (reprocess existing data)

```bash
helm install tcga-reprocess charts/data-service/tcga \
  --namespace kubeflow \
  --set tcga.skipDownload=true \
  --set tcga.rawDir=/efs/data/tcga_raw
```

### Skip expression processing (faster)

```bash
helm install tcga-fast charts/data-service/tcga \
  --namespace kubeflow \
  --set tcga.skipExpression=true
```

## Configuration

### Key Values

| Parameter | Description | Default |
|-----------|-------------|---------|
| `image` | Python container image | `python:3.11-slim` |
| `tcga.projects` | List of TCGA project IDs to process | `[]` (all 33) |
| `tcga.outputDir` | Output directory for Parquet files | `/efs/home/{{ .Release.Name }}/tcga_processed` |
| `tcga.rawDir` | Directory for raw S3 downloads | `/efs/home/{{ .Release.Name }}/tcga_raw` |
| `tcga.skipDownload` | Skip S3 download, use existing raw data | `false` |
| `tcga.skipExpression` | Skip gene expression processing | `false` |
| `resources.requests.memory` | Memory request | `8Gi` |
| `resources.requests.cpu` | CPU request | `4` |
| `resources.limits.memory` | Memory limit | `16Gi` |
| `resources.limits.cpu` | CPU limit | `8` |
| `job.backoffLimit` | Job retry limit | `2` |
| `job.ttlSecondsAfterFinished` | Time to keep completed jobs | `86400` (24h) |

### TCGA Project IDs

Available projects (33 total):
- `TCGA-BRCA` - Breast Invasive Carcinoma
- `TCGA-COAD` - Colon Adenocarcinoma
- `TCGA-PRAD` - Prostate Adenocarcinoma
- `TCGA-LUAD` - Lung Adenocarcinoma
- `TCGA-LUSC` - Lung Squamous Cell Carcinoma
- ... and 28 more

See [TCGA documentation](https://gdc.cancer.gov/resources-tcga-users/tcga-code-tables/tcga-study-abbreviations) for complete list.

## Output Structure

```
{outputDir}/
├── TCGA-BRCA/
│   ├── clinical.parquet
│   ├── expression_matrix.parquet
│   ├── mutations.parquet
│   ├── copy_number.parquet
│   ├── mirna_expression.parquet
│   └── file_manifest.parquet
├── TCGA-COAD/
│   └── ...
└── metadata/
    ├── projects.parquet
    ├── gene_id_mapping.parquet
    ├── sample_type_codes.parquet
    └── processing_log.json
```

## Monitoring

Check job status:
```bash
kubectl get jobs -n kubeflow -l app.kubernetes.io/name=tcga
```

View logs:
```bash
kubectl logs -n kubeflow -l app.kubernetes.io/name=tcga --follow
```

## Cleanup

Delete the job and associated resources:
```bash
helm uninstall tcga-full -n kubeflow
```

## Advanced Configuration

### Target specific node types

```yaml
nodeSelector:
  node.kubernetes.io/instance-type: m5.2xlarge
```

### Add tolerations

```yaml
tolerations:
  - key: "workload-type"
    operator: "Equal"
    value: "data-processing"
    effect: "NoSchedule"
```

### Use FSx for high-performance storage

```yaml
tcga:
  outputDir: /fsx/data/tcga_processed
  rawDir: /fsx/data/tcga_raw
```

## Troubleshooting

### Job fails with OOMKilled
Increase memory limits:
```bash
--set resources.limits.memory=32Gi
```

### Slow download from S3
Use FSx for Lustre with S3 integration, or increase CPU:
```bash
--set resources.requests.cpu=8
```

### Network timeout errors
The job will automatically retry failed API requests. Check network policies and security groups.

## License

See [LICENSE](../../../LICENSE) file.
