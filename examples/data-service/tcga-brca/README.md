# TCGA Preprocessing Example: BRCA

This example demonstrates how to preprocess TCGA (The Cancer Genome Atlas) data for Breast Invasive Carcinoma using the TCGA Helm chart.

- **TCGA-BRCA**: Breast Invasive Carcinoma

## What This Does

The preprocessing pipeline:

1. **Downloads** raw data from AWS Open Data Registry (`s3://tcga-2-open`)
2. **Fetches** clinical metadata from NCI GDC API
3. **Processes** multiple data types:
   - Clinical metadata (demographics, diagnosis, survival)
   - Gene expression matrices (RNA-Seq)
   - Somatic mutations (MAF files)
   - Copy number alterations
   - miRNA expression
4. **Outputs** analysis-ready Parquet files organized by project

## Prerequisites

- EKS cluster with EFS persistent volume
- PVC named `pv-efs` in the `kubeflow` namespace
- Network access to S3 and GDC API
- Sufficient storage (~20-30 GB for BRCA project)

## Quick Start

### 1. Deploy the preprocessing job

```bash
cd examples/data-service/tcga-brca
bash deploy.sh
```

Or with custom settings:

```bash
RELEASE_NAME=my-tcga-job NAMESPACE=default bash deploy.sh
```

### 2. Monitor progress

```bash
# Watch job status
kubectl get jobs -n kubeflow -l app.kubernetes.io/instance=tcga-brca -w

# View logs
kubectl logs -n kubeflow -l app.kubernetes.io/instance=tcga-brca --follow

# Check pod status
kubectl get pods -n kubeflow -l app.kubernetes.io/instance=tcga-brca
```

### 3. Access processed data

Once complete, data will be available at:
```
/fsx/home/tcga-brca/tcga_processed/
├── TCGA-BRCA/
│   ├── clinical.parquet
│   ├── expression_matrix.parquet
│   ├── mutations.parquet
│   ├── copy_number.parquet
│   └── mirna_expression.parquet
└── metadata/
    ├── projects.parquet
    ├── gene_id_mapping.parquet
    └── processing_log.json
```

### 4. Cleanup

```bash
# Remove job only (keep data)
bash cleanup.sh

# Remove job and data
REMOVE_DATA=true bash cleanup.sh
```

## Manual Deployment

If you prefer to use Helm directly:

```bash
helm install tcga-brca ../../../charts/data-service/tcga \
  --namespace kubeflow \
  --values values.yaml
```

## Configuration Options

Edit `values.yaml` to customize:

### Process different projects

```yaml
tcga:
  projects:
    - TCGA-COAD  # Colon Adenocarcinoma
    - TCGA-PRAD  # Prostate Adenocarcinoma
```

### Use custom output directory

```yaml
tcga:
  outputDir: /efs/data/my-tcga-output
  rawDir: /fsx/data/my-tcga-raw
```

### Skip download (reprocess existing data)

```yaml
tcga:
  skipDownload: true
  rawDir: /efs/data/existing-tcga-raw
```

### Skip expression processing (faster)

```yaml
tcga:
  skipExpression: true
```

### Adjust resources

```yaml
resources:
  requests:
    memory: "16Gi"
    cpu: "8"
  limits:
    memory: "32Gi"
    cpu: "16"
```

### Target specific node types

```yaml
nodeSelector:
  node.kubernetes.io/instance-type: m5.4xlarge
```

## Expected Runtime

- **Download**: ~5-10 minutes (depends on network speed)
- **Processing**: ~10-20 minutes (depends on CPU/memory)
- **Total**: ~15-30 minutes for BRCA project

## Output Data Schema

### Clinical Data (`clinical.parquet`)

One row per patient with demographics, diagnosis, staging, survival:

```python
import pandas as pd
clinical = pd.read_parquet("/fsx/home/tcga-brca/tcga_processed/TCGA-BRCA/clinical.parquet")
print(clinical.columns)
# ['case_id', 'submitter_id', 'demographic_gender', 'demographic_age_at_index',
#  'diagnosis_tumor_stage', 'os_time', 'os_event', ...]
```

### Expression Matrix (`expression_matrix.parquet`)

Genes × samples matrix with raw read counts:

```python
expr = pd.read_parquet("/fsx/home/tcga-brca/tcga_processed/TCGA-BRCA/expression_matrix.parquet")
print(expr.shape)  # (60000 genes, 1200 samples)
```

### Mutations (`mutations.parquet`)

Long-format somatic variants:

```python
mutations = pd.read_parquet("/fsx/home/tcga-brca/tcga_processed/TCGA-BRCA/mutations.parquet")
print(mutations.columns)
# ['Hugo_Symbol', 'Chromosome', 'Start_Position', 'Variant_Classification',
#  'Tumor_Sample_Barcode', 'HGVSp_Short', 'IMPACT', ...]
```

## Using the Data

### Example: Load and analyze

```python
import pandas as pd

# Load clinical data
clinical = pd.read_parquet("/fsx/home/tcga-brca/tcga_processed/TCGA-BRCA/clinical.parquet")

# Filter for Stage III patients
stage3 = clinical[clinical['diagnosis_ajcc_pathologic_stage'].str.contains('Stage III', na=False)]

# Load expression for specific gene
expr = pd.read_parquet("/fsx/home/tcga-brca/tcga_processed/TCGA-BRCA/expression_matrix.parquet")
genes = pd.read_parquet("/fsx/home/tcga-brca/tcga_processed/metadata/gene_id_mapping.parquet")

# Get BRCA1 expression
brca1_id = genes[genes['gene_name'] == 'BRCA1']['gene_id'].iloc[0]
brca1_expr = expr.loc[brca1_id]

# Load mutations
mutations = pd.read_parquet("/fsx/home/tcga-brca/tcga_processed/TCGA-BRCA/mutations.parquet")
tp53_muts = mutations[mutations['Hugo_Symbol'] == 'TP53']
```

## Troubleshooting

### Job fails with OOMKilled

Increase memory limits in `values.yaml`:

```yaml
resources:
  limits:
    memory: "32Gi"
```

### Network timeout errors

The pipeline automatically retries failed requests. Check:
- Security groups allow outbound HTTPS
- Network policies allow external access
- NAT gateway is functioning

### PVC not found

Ensure EFS PVC exists:

```bash
kubectl get pvc pv-efs -n kubeflow
```

Create if missing (see main README for EFS setup).

### Slow download

Consider using FSx for Lustre with S3 integration:

```yaml
tcga:
  rawDir: /fsx/data/tcga_raw
```

## Next Steps

- See [parent TCGA documentation](../tcga/README.md) for detailed data schema
- Process additional cancer types by modifying `tcga.projects`
- Use processed data for ML training, survival analysis, or genomic studies

## References

- [TCGA Program](https://www.cancer.gov/tcga)
- [GDC Data Portal](https://portal.gdc.cancer.gov/)
- [AWS Open Data Registry](https://registry.opendata.aws/tcga/)
