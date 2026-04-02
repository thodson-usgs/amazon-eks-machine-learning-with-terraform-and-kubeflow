# Continual Pre-Training Qwen3-14B using PyTorch FSDP with Accelerate library

This example illustrates continual pre-training (CPT) of Qwen3-14B using PyTorch FSDP with [Hugging Face Accelerate](https://github.com/huggingface/accelerate) library. CPT performs full model training on unlabeled text data (all tokens are training targets), using the default `wikimedia/wikipedia` dataset.

## Prerequisites

Before proceeding, complete the [Prerequisites](../../../../README.md#prerequisites) and [Getting started](../../../../README.md#getting-started). See [What is in the YAML file](../../../../README.md#yaml-recipes) to understand the common fields in the Helm values files.

## Hugging Face Qwen3-14B pre-trained model weights

To download Hugging Face Qwen3-14B model weights, replace `YourHuggingFaceToken` with your Hugging Face token below, and execute:

    cd ~/amazon-eks-machine-learning-with-terraform-and-kubeflow
    helm install --debug accel-qwen3-14b-cpt     \
        charts/machine-learning/model-prep/hf-snapshot    \
        --set-json='env=[{"name":"HF_MODEL_ID","value":"Qwen/Qwen3-14B"},{"name":"HF_TOKEN","value":"YourHuggingFaceToken"}]' \
        -n kubeflow-user-example-com

Uninstall the Helm chart at completion:

    helm uninstall accel-qwen3-14b-cpt -n kubeflow-user-example-com

## Continual Pre-Training Qwen3-14B

The Helm values are defined in [cpt.yaml](./cpt.yaml).

To launch the CPT job, execute:

    cd ~/amazon-eks-machine-learning-with-terraform-and-kubeflow
    helm install --debug accel-qwen3-14b-cpt \
        charts/machine-learning/training/pytorchjob-distributed \
        -f examples/training/accelerate/qwen3-14b-cpt/cpt.yaml -n kubeflow-user-example-com

You can tail the logs using following command:

    kubectl logs -f pytorchjob-accel-qwen3-14b-cpt-worker-0 -n kubeflow-user-example-com

To uninstall the Helm chart for the CPT job, execute:

    helm uninstall accel-qwen3-14b-cpt -n kubeflow-user-example-com


## Output

To access the output stored on EFS and FSx for Lustre file-systems, execute following commands:

    cd ~/amazon-eks-machine-learning-with-terraform-and-kubeflow
    kubectl apply -f eks-cluster/utils/attach-pvc.yaml -n kubeflow
    kubectl exec -it -n kubeflow attach-pvc -- /bin/bash

This will put you in a pod attached to the EFS and FSx for Lustre file-systems, mounted at `/efs`, and `/fsx`, respectively. Type `exit` to exit the pod.

### Logs

Training `logs` are available in `/efs/home/accel-qwen3-14b-cpt/logs` folder.

### Output

Training `output` are available in `/efs/home/accel-qwen3-14b-cpt/output` folder.
