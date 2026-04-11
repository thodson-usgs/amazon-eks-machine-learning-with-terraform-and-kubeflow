# Claude AI Prompt Templates for EKS Model Inference

These prompt templates are designed to be used with the **Claude AI agent running on a machine with `kubectl` and `helm` access to an Amazon EKS cluster**. Copy and paste a prompt into the Claude AI agent's chat interface, and the agent will autonomously deploy the model, verify readiness, run inference tests, and report results.

**Prerequisites:**
- The Claude AI agent is running with the `amazon-eks-machine-learning-with-terraform-and-kubeflow` repository as its workspace
- `kubectl` is configured with access to the target EKS cluster
- `helm` is installed and configured
- The EKS cluster has GPU or Neuron nodes available (managed by Karpenter or node groups)
- EFS is available for shared storage (mounted at `/efs/`)
- FSx for Lustre is available for model storage (mounted at `/fsx/`)
- For gated models (e.g., Llama, Gemma): accept the model EULA on Hugging Face, and include your Hugging Face Access Token in the prompt so the agent can download the model to FSx

**How to use:**
1. Open the Claude AI agent with the repository as its workspace
2. Copy one of the prompt templates below
3. Fill in the placeholders (model ID, instance type, namespace, HF token for gated models)
4. Paste the prompt into the agent's chat
5. The agent will download the model, deploy via Helm, monitor pod readiness, and run inference tests

---

## Triton Inference Server — vLLM Backend (CUDA)

Single-node inference using Triton with vLLM backend on NVIDIA GPUs. To adapt the examples below, customize:
- The **model name** and **Helm release name**
- The **instance type** and **GPU count** based on model size
- The **tensor parallel size** to match the number of GPUs
- The **triton_server.yaml** values file for the specific model

| Hardware | Server | Backend | Examples |
|----------|--------|---------|----------|
| CUDA     | Triton Inference Server | vLLM | Llama 3 8B, Mistral 7B, DeepSeek R1 Distill, Qwen 3 |

### Example 1: Deploy Llama 3 8B Instruct (CUDA)

```
Read and analyze the serve.ipynb notebook at 
examples/inference/triton-inference-server/vllm_backend/llama3-8b-instruct/serve.ipynb
and the corresponding triton_server.yaml values file to understand the EKS 
inference deployment workflow. Also read the Helm chart at 
charts/machine-learning/serving/triton-inference-server/ to understand how 
values map to Kubernetes resources.

Confirm your understanding of the deployment pipeline, including Helm install,
pod scheduling, model loading, Triton readiness checks, and service exposure.

Then, deploy Meta Llama 3 8B Instruct on the EKS cluster using Triton 
Inference Server with vLLM backend.

Deployment details:
   - Server: Triton Inference Server
   - Backend: vLLM
   - Model: meta-llama/Meta-Llama-3-8B-Instruct
   - Model path on FSx: /fsx/pretrained-models/meta-llama/Meta-Llama-3-8B-Instruct
   - Instance type: g6.48xlarge
   - GPUs: 8
   - Tensor parallel size: 8
   - Namespace: kubeflow-user-example-com
   - Hugging Face token: <YOUR_HF_TOKEN>

IMPORTANT CONSTRAINTS:
- Do NOT modify any existing files in the repository
- Follow the workflow from the serve.ipynb notebook exactly
- If the model is not already on FSx, download it using huggingface-cli:
  huggingface-cli download meta-llama/Meta-Llama-3-8B-Instruct 
  --local-dir /fsx/pretrained-models/meta-llama/Meta-Llama-3-8B-Instruct
  --token <YOUR_HF_TOKEN>
- Use helm install with the triton_server.yaml values file
- Wait for all pods to be Running before testing
- Wait for Triton readiness probe to pass before sending requests
- Test with at least one inference request to verify the model works

WHAT TO REPORT:
1. Does the model deploy successfully? (Yes/No)
2. Pod status and scheduling details (node, GPU allocation)
3. Time from helm install to model ready
4. Inference test result (response from the model)
5. Any errors encountered (include root cause analysis)

CLEANUP:
- After testing, uninstall the Helm release to free resources
```

---

## Triton Inference Server — vLLM Backend (Neuron)

Single-node inference on AWS Inferentia2 or Trainium chips. Neuron models require compilation on first run. To adapt, customize:
- The **instance type** (`inf2.48xlarge`, `trn1.32xlarge`, etc.)
- The **Neuron device count** and **tensor parallel size**
- The **max model length** and **batch size** (affects compilation time and memory)

| Hardware | Server | Backend | Examples |
|----------|--------|---------|----------|
| Neuron   | Triton Inference Server | vLLM | Llama 3 8B, Mistral 7B, DeepSeek R1 Distill |

### Example 2: Deploy Llama 3 8B Instruct (Neuron)

```
Read and analyze the serve.ipynb notebook at 
examples/inference/triton-inference-server/vllm_backend/llama3-8b-instruct-neuron/serve.ipynb
and the corresponding triton_server.yaml values file to understand the Neuron 
inference deployment workflow. Note the differences from CUDA: neuron-scheduler,
Neuron device requests, compilation environment variables, and longer startup times.

Confirm your understanding of the deployment pipeline.

Then, deploy Meta Llama 3 8B Instruct on the EKS cluster using Triton 
Inference Server with vLLM backend on Inferentia2.

Deployment details:
   - Server: Triton Inference Server
   - Backend: vLLM
   - Model: meta-llama/Meta-Llama-3-8B-Instruct
   - Model path on FSx: /fsx/pretrained-models/meta-llama/Meta-Llama-3-8B-Instruct
   - Instance type: inf2.48xlarge
   - Neuron devices: 4
   - Tensor parallel size: 8
   - Namespace: kubeflow-user-example-com
   - Hugging Face token: <YOUR_HF_TOKEN>

IMPORTANT CONSTRAINTS:
- Do NOT modify any existing files in the repository
- Follow the workflow from the serve.ipynb notebook exactly
- If the model is not already on FSx, download it using huggingface-cli:
  huggingface-cli download meta-llama/Meta-Llama-3-8B-Instruct 
  --local-dir /fsx/pretrained-models/meta-llama/Meta-Llama-3-8B-Instruct
  --token <YOUR_HF_TOKEN>
- Use helm install with the triton_server.yaml values file
- First run requires Neuron model compilation (30-60 minutes)
- Wait for Triton readiness probe to pass before sending requests
- Test with at least one inference request to verify the model works

WHAT TO REPORT:
1. Does the model deploy successfully? (Yes/No)
2. Pod status and scheduling details
3. Compilation time (if first run)
4. Time from helm install to model ready
5. Inference test result
6. Any errors encountered (include root cause analysis)

NOTE: First run on Neuron requires model compilation which may take 30-60 minutes.
Compiled artifacts are cached on EFS for subsequent deployments.

CLEANUP:
- After testing, uninstall the Helm release to free resources
```

---

## Triton Inference Server — Ray vLLM Backend (Multi-Node)

Multi-node inference using LeaderWorkerSet (LWS) with Ray cluster for pipeline parallelism across nodes. Used for large models that don't fit on a single node. To adapt, customize:
- The **LWS size** (number of nodes)
- The **pipeline parallel size** to match the number of nodes
- The **Helm chart** (`triton-inference-server-lws` instead of `triton-inference-server`)

| Hardware | Server | Backend | Examples |
|----------|--------|---------|----------|
| CUDA     | Triton Inference Server (LWS) | Ray + vLLM | DeepSeek R1, Mixtral 8x22B |

### Example 3: Deploy Mixtral 8x22B (Multi-Node)

```
Read and analyze the serve.ipynb notebook at 
examples/inference/triton-inference-server/ray_vllm_backend/mixtral-8x22b-instruct-v01/serve.ipynb
and the corresponding triton_server.yaml values file to understand the multi-node 
inference deployment workflow. Also read the LWS Helm chart at 
charts/machine-learning/serving/triton-inference-server-lws/ to understand how 
LeaderWorkerSet manages multi-node deployments.

Confirm your understanding of the deployment pipeline, including LWS leader/worker 
pod topology, Ray cluster formation, and pipeline parallel inference.

Then, deploy Mixtral 8x22B Instruct v0.1 on the EKS cluster using Triton 
Inference Server with Ray vLLM backend across 2 nodes.

Deployment details:
   - Server: Triton Inference Server (LWS)
   - Backend: Ray + vLLM
   - Model: mistralai/Mixtral-8x22B-Instruct-v0.1
   - Model path on FSx: /fsx/pretrained-models/mistralai/Mixtral-8x22B-Instruct-v0.1
   - Instance type: p4d.24xlarge
   - Nodes: 2 (LWS size)
   - GPUs per node: 8
   - Tensor parallel size: 8
   - Pipeline parallel size: 2
   - Namespace: kubeflow-user-example-com

IMPORTANT CONSTRAINTS:
- Do NOT modify any existing files in the repository
- Follow the workflow from the serve.ipynb notebook exactly
- If the model is not already on FSx, download it using huggingface-cli:
  huggingface-cli download mistralai/Mixtral-8x22B-Instruct-v0.1 
  --local-dir /fsx/pretrained-models/mistralai/Mixtral-8x22B-Instruct-v0.1
- Use the triton-inference-server-lws Helm chart (not the single-node chart)
- Wait for both leader and worker pods to be Running
- Wait for Ray cluster to form before checking Triton readiness
- Test with at least one inference request to verify the model works

WHAT TO REPORT:
1. Does the model deploy successfully? (Yes/No)
2. Leader and worker pod status
3. Ray cluster formation status
4. Time from helm install to model ready
5. Inference test result
6. Any errors encountered (include root cause analysis)

CLEANUP:
- After testing, uninstall the Helm release to free resources
```

---

## Ray Serve with vLLM

Single-node and multi-node inference using Ray Serve with vLLM. To adapt, customize:
- The **model name** and **Ray Serve deployment configuration**
- The **instance type** and parallelism settings
- The **Helm chart** (`rayserve` for single-node, or LWS-based for multi-node)

| Hardware | Server | Backend | Examples |
|----------|--------|---------|----------|
| CUDA     | Ray Serve | vLLM | Llama 3 8B, Qwen 3 32B, DeepSeek R1, Pixtral 12B |
| Neuron   | Ray Serve | vLLM | Llama 3 8B |

### Example 4: Deploy Qwen 3 32B with Ray Serve

```
Read and analyze the serve.ipynb notebook at 
examples/inference/rayserve/qwen3-32B-vllm/serve.ipynb
and the corresponding values file to understand the Ray Serve deployment workflow.

Confirm your understanding of the deployment pipeline.

Then, deploy Qwen 3 32B on the EKS cluster using Ray Serve with vLLM.

Deployment details:
   - Server: Ray Serve
   - Backend: vLLM
   - Model: Qwen/Qwen3-32B
   - Model path on FSx: /fsx/pretrained-models/Qwen/Qwen3-32B
   - Instance type: p4d.24xlarge
   - GPUs: 8
   - Tensor parallel size: 8
   - Namespace: kubeflow-user-example-com

IMPORTANT CONSTRAINTS:
- Do NOT modify any existing files in the repository
- Follow the workflow from the serve.ipynb notebook exactly
- If the model is not already on FSx, download it using huggingface-cli:
  huggingface-cli download Qwen/Qwen3-32B 
  --local-dir /fsx/pretrained-models/Qwen/Qwen3-32B
- Wait for all pods to be Running before testing
- Test with at least one inference request to verify the model works

WHAT TO REPORT:
1. Does the model deploy successfully? (Yes/No)
2. Pod status and scheduling details
3. Time from helm install to model ready
4. Inference test result
5. Any errors encountered (include root cause analysis)

CLEANUP:
- After testing, uninstall the Helm release to free resources
```

---

## Supported Configurations

### Inference Servers
- **Triton Inference Server**: Single-node with vLLM, TensorRT-LLM, or Python backends
- **Triton Inference Server (LWS)**: Multi-node with Ray + vLLM via LeaderWorkerSet
- **Ray Serve**: Single and multi-node with vLLM

### Hardware
- **NVIDIA GPUs** (CUDA): g5, g6, p4d, p4de, p5 instance types
- **AWS Neuron** (Inferentia2/Trainium): inf2, trn1 instance types

### Helm Charts
| Chart | Path | Use Case |
|-------|------|----------|
| triton-inference-server | `charts/machine-learning/serving/triton-inference-server/` | Single-node Triton (vLLM, TensorRT-LLM, Python) |
| triton-inference-server-lws | `charts/machine-learning/serving/triton-inference-server-lws/` | Multi-node Triton with Ray + LWS |
| rayserve | `charts/machine-learning/serving/rayserve/` | Ray Serve deployments |

---
