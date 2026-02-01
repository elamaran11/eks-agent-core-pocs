# Architecture Overview

## Component Interaction Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Developer Workflow                          │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   │ git push
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         GitHub Repository                           │
│                    (Infrastructure as Code)                         │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   │ monitors
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         EKS Dev Cluster                             │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │                        FluxCD                                 │ │
│  │  - Monitors Git repository                                    │ │
│  │  - Syncs Kubernetes manifests                                │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                   │                                 │
│                                   │ triggers                        │
│                                   ▼                                 │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │                    Tofu Controller                            │ │
│  │  - Reads Terraform CRDs                                       │ │
│  │  - Executes Terraform/OpenTofu                               │ │
│  │  - Stores outputs in Kubernetes Secrets                      │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                   │                                 │
│                                   │ provisions                      │
│                                   ▼                                 │
└───────────────────────────────────┼─────────────────────────────────┘
                                    │
                                    │ creates AWS resources
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         AWS us-west-2                               │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │              Agent Core Memory (Bedrock KB)                   │ │
│  │  - OpenSearch Serverless Collection                          │ │
│  │  - Vector embeddings for context storage                     │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │         Agent Core Code Interpreter (Lambda)                  │ │
│  │  - Executes Python code dynamically                          │ │
│  │  - Returns execution results                                 │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │            Agent Core Browser (Lambda)                        │ │
│  │  - Web scraping and browsing                                 │ │
│  │  - Returns page content                                      │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │                 IAM Roles                                     │ │
│  │  - Strands Agent Role (IRSA)                                 │ │
│  │  - Lambda Execution Roles                                    │ │
│  │  - Bedrock Access Roles                                      │ │
│  └──────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ invokes via AWS SDK
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         EKS Dev Cluster                             │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │                   Strands Agent Pod                           │ │
│  │                                                               │ │
│  │  ┌────────────────────────────────────────────────────────┐  │ │
│  │  │  ServiceAccount: strands-agent-sa                      │  │ │
│  │  │  IAM Role: agent-core-poc-strands-agent-role (IRSA)   │  │ │
│  │  └────────────────────────────────────────────────────────┘  │ │
│  │                                                               │ │
│  │  ┌────────────────────────────────────────────────────────┐  │ │
│  │  │  Environment Variables (from Secret):                  │  │ │
│  │  │  - AGENT_MEMORY_KB_ID                                 │  │ │
│  │  │  - CODE_INTERPRETER_NAME                              │  │ │
│  │  │  - BROWSER_NAME                                       │  │ │
│  │  └────────────────────────────────────────────────────────┘  │ │
│  │                                                               │ │
│  │  ┌────────────────────────────────────────────────────────┐  │ │
│  │  │  Agent Logic:                                          │  │ │
│  │  │  1. Retrieve from Memory (Bedrock KB)                 │  │ │
│  │  │  2. Execute Code (Lambda)                             │  │ │
│  │  │  3. Browse Web (Lambda)                               │  │ │
│  │  │  4. Invoke LLM (Bedrock Runtime)                      │  │ │
│  │  └────────────────────────────────────────────────────────┘  │ │
│  └──────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Technologies

- **FluxCD**: GitOps continuous delivery for Kubernetes
- **Tofu Controller**: Terraform/OpenTofu controller for Kubernetes
- **Amazon Bedrock**: LLM and Knowledge Base services
- **AWS Lambda**: Serverless compute for Code Interpreter and Browser
- **OpenSearch Serverless**: Vector database for Agent Memory
- **IRSA**: IAM Roles for Service Accounts (secure AWS access from pods)

## Security Model

1. **IRSA (IAM Roles for Service Accounts)**: Pod assumes IAM role without static credentials
2. **Least Privilege**: Each component has minimal required permissions
3. **Secrets Management**: Terraform outputs stored in Kubernetes Secrets
4. **Network Isolation**: Agent runs in EKS with VPC security groups

## Data Flow Example (Weather Agent)

1. **User Request** → Strands Agent receives task
2. **Memory Retrieval** → Agent queries Bedrock Knowledge Base for context
3. **Code Execution** → Agent invokes Code Interpreter Lambda to fetch weather data
4. **Web Browsing** → Agent invokes Browser Lambda to scrape weather website
5. **LLM Processing** → Agent sends context to Bedrock LLM for response generation
6. **Response** → Agent returns formatted weather information
