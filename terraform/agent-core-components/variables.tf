variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name prefix"
  type        = string
  default     = "agent-core-poc"
}

variable "eks_oidc_provider" {
  description = "EKS OIDC provider URL (without https://)"
  type        = string
}

variable "network_mode" {
  description = "Network mode for Agent Core tools (INTERNET or VPC)"
  type        = string
  default     = "INTERNET"
}
