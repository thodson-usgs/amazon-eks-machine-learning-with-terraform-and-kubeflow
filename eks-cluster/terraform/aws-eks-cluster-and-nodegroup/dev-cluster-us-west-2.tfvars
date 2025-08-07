# Default USGS dev cluster configuration

# AWS Configuration
region = "us-west-2"
# credentials = "~/.aws/credentials"
profile = "dev"

# Cluster Configuration
cluster_name = "thodson-argo"
# k8s_version = "1.33"

# VPC Configuration - Use existing private VPC
aws_vpc = {
  default    = false
  id         = "vpc-0af42fd592a1efc5b"
  subnet_ids = [
    "subnet-0f29464029b7f677c",  # us-west-2a
    "subnet-026849aecd639aa56",  # us-west-2b
    "subnet-0bcd68692d4d2279d"   # us-west-2c
  ]
}

# Availability Zones - Will be auto-detected if not specified
# azs = ["us-west-2a", "us-west-2b", "us-west-2c"]

# CIDR Ranges (only used when creating new VPC)
# cidr_vpc = "192.168.0.0/16"
# cidr_private = ["192.168.64.0/18", "192.168.128.0/18", "192.168.192.0/18"]
# cidr_public = ["192.168.0.0/24", "192.168.1.0/24", "192.168.2.0/24"]

# Special Availability Zones
# neuron_az = "none"
# cuda_efa_az = "none"

# AWS Tags
aws_tags = {
  "wma:project_id"     = "uncertainty_ts"
  "wma:application_id" = "dev-cluster"
  "wma:contact"        = "thodson@usgs.gov"
}

# IAM Permissions Boundary
permissions_boundary = "arn:aws:iam::807615458658:policy/csr-Developer-Permissions-Boundary"

# ArgoCD Configuration
argocd_admin_password = "$2y$10$4yPTKC/Xk8txCeweej3CfOkBbnKUAv7L098bY4KU5HHkP4tHiz6Au"

# EFS Configuration
# efs_performance_mode = "generalPurpose"
# efs_throughput_mode = "bursting"

# FSX Configuration
# import_path = ""
# fsx_storage_capacity = 1200

# EC2 Configuration
# key_pair = ""
# node_volume_size = 200
# system_volume_size = 200

# Node Group Configuration
# node_group_desired = 0
# node_group_max = 32
# node_group_min = 0
# system_group_desired = 8
# system_group_max = 32
# system_group_min = 8

# Capacity Type
# capacity_type = "ON_DEMAND"
# system_capacity_type = "ON_DEMAND"

# Instance Types
# nvidia_instances = ["g6.2xlarge", "g6.48xlarge", "p4d.24xlarge"]
# system_instances = ["t3a.large", "t3a.xlarge", "t3a.2xlarge", "m5.large", "m5.xlarge", "m5.2xlarge", "m5.4xlarge", "m5a.large", "m5a.xlarge", "m5a.2xlarge", "m5a.4xlarge", "m7a.large", "m7a.xlarge", "m7a.2xlarge", "m7a.4xlarge"]
# neuron_instances = ["inf2.xlarge", "inf2.48xlarge", "trn1.32xlarge"]

# EFA Configuration
# efa_enabled = {
#   "p4d.24xlarge" = 4
#   "p4de.24xlarge" = 4
#   "p5.48xlarge" = 32
#   "p5e.48xlarge" = 32
#   "p5en.48xlarge" = 32
#   "trn1.32xlarge" = 8
#   "trn1n.32xlarge" = 16
#   "trn2.48xlarge" = 32
# }

# Custom Taints
# custom_taints = []

# Namespace Configuration
# auth_namespace = "auth"
# ingress_namespace = "ingress"
# kubeflow_namespace = "kubeflow"

# User Configuration
# static_email = "user@example.com"
# static_username = "user"

# Kueue Configuration
# kueue_enabled = false
# kueue_namespace = "kueue-system"
# kueue_version = "0.11.4"

# Karpenter Configuration
# karpenter_enabled = true
karpenter_enabled = true
# karpenter_namespace = "kube-system"
# karpenter_version = "1.5.0"
# karpenter_capacity_type = "on-demand"
# karpenter_consolidate_after = "600s"
# karpenter_max_pods = 20

# Prometheus Configuration
# prometheus_enabled = true
# prometheus_namespace = "kube-system"
# prometheus_version = "60.3.0"

# NVIDIA Plugin Configuration
# nvidia_plugin_version = "v0.14.3"

# Chart Configuration
# local_helm_repo = "../../../charts"

# Ingress Configuration
# ingress_scheme = "internal"
# ingress_cidrs = "0.0.0.0/0"
# ingress_gateway = "ingress-gateway"

# Certificate Configuration
# cluster_issuer = "ca-self-signing-issuer"

# Platform Component Flags
# Platform Component Flags
kubeflow_platform_enabled = true
# ack_sagemaker_enabled = false
# kserve_enabled = false
# kserve_namespace = "kserve"
# kserve_version = "v0.15.1"
# airflow_enabled = false
# airflow_namespace = "airflow"
# airflow_version = "1.16.0"
# dcgm_exporter_enabled = false

# Slurm Configuration
# slurm_enabled = false
# slurm_namespace = "slurm"
# slurm_root_ssh_authorized_keys = []
# slurm_login_enabled = false
# slurm_storage_type = "efs"
# slurm_storage_capacity = "1200Gi"
# slurm_db_max_capacity = 16.0

# MLFlow Configuration
# mlflow_enabled = false
# mlflow_namespace = "mlflow"
# mlflow_version = "0.17.2"
# mlflow_force_destroy_bucket = false
# mlflow_admin_username = "admin"
# mlflow_db_max_capacity = 16.0