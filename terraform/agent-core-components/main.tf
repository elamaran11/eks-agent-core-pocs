provider "aws" {
  region = var.aws_region
}

# Agent Core Memory
resource "aws_bedrockagent_knowledge_base" "agent_memory" {
  name     = "${var.project_name}-memory"
  role_arn = aws_iam_role.agent_memory_role.arn

  knowledge_base_configuration {
    type = "VECTOR"
    vector_knowledge_base_configuration {
      embedding_model_arn = "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.titan-embed-text-v1"
    }
  }

  storage_configuration {
    type = "OPENSEARCH_SERVERLESS"
    opensearch_serverless_configuration {
      collection_arn    = aws_opensearchserverless_collection.memory_collection.arn
      vector_index_name = "agent-memory-index"
      field_mapping {
        vector_field   = "embedding"
        text_field     = "text"
        metadata_field = "metadata"
      }
    }
  }
}

resource "aws_opensearchserverless_security_policy" "encryption_policy" {
  name = "${var.project_name}-encryption-policy"
  type = "encryption"
  policy = jsonencode({
    Rules = [{
      ResourceType = "collection"
      Resource     = ["collection/${var.project_name}-memory-collection"]
    }]
    AWSOwnedKey = true
  })
}

resource "aws_opensearchserverless_collection" "memory_collection" {
  name = "${var.project_name}-memory-collection"
  type = "VECTORSEARCH"
  depends_on = [aws_opensearchserverless_security_policy.encryption_policy]
}

resource "aws_iam_role" "agent_memory_role" {
  name = "${var.project_name}-agent-memory-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "bedrock.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy" "agent_memory_policy" {
  role = aws_iam_role.agent_memory_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "aoss:APIAccessAll"
        ]
        Resource = aws_opensearchserverless_collection.memory_collection.arn
      },
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel"
        ]
        Resource = "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.titan-embed-text-v1"
      }
    ]
  })
}

# Agent Core Code Interpreter
resource "aws_bedrockagentcore_code_interpreter" "code_interpreter" {
  name        = "${replace(var.project_name, "-", "_")}_code_interpreter"
  description = "Code interpreter for ${var.project_name} agent"

  network_configuration {
    network_mode = var.network_mode
  }

  tags = {
    Name    = "${var.project_name}-code-interpreter"
    Project = var.project_name
  }
}

# Agent Core Browser
resource "aws_bedrockagentcore_browser" "browser" {
  name        = "${replace(var.project_name, "-", "_")}_browser"
  description = "Browser for ${var.project_name} agent"

  network_configuration {
    network_mode = var.network_mode
  }

  tags = {
    Name    = "${var.project_name}-browser"
    Project = var.project_name
  }
}

# IAM Role for EKS Pod to invoke Agent Core components
resource "aws_iam_role" "strands_agent_role" {
  name = "${var.project_name}-strands-agent-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Federated = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/${var.eks_oidc_provider}"
      }
      Condition = {
        StringEquals = {
          "${var.eks_oidc_provider}:sub" = "system:serviceaccount:default:strands-agent-sa"
          "${var.eks_oidc_provider}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "strands_agent_policy" {
  role = aws_iam_role.strands_agent_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeAgentCoreTool"
        ]
        Resource = [
          "arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:agent-core-tool/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "bedrock:Retrieve",
          "bedrock:RetrieveAndGenerate"
        ]
        Resource = aws_bedrockagent_knowledge_base.agent_memory.arn
      },
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel"
        ]
        Resource = "arn:aws:bedrock:${var.aws_region}::foundation-model/*"
      }
    ]
  })
}

data "aws_caller_identity" "current" {}
