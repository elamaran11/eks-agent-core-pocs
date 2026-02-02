variable "project_name" {
  description = "Project name prefix for all resources"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "network_mode" {
  description = "Network mode for Agent Core tools (PUBLIC, VPC, or SANDBOX)"
  type        = string
  default     = "PUBLIC"
}

variable "eks_oidc_provider" {
  description = "EKS OIDC provider for IRSA"
  type        = string
}

variable "enable_memory" {
  description = "Enable Agent Core Memory"
  type        = bool
  default     = true
}

variable "enable_browser" {
  description = "Enable Agent Core Browser"
  type        = bool
  default     = true
}

variable "enable_code_interpreter" {
  description = "Enable Agent Core Code Interpreter"
  type        = bool
  default     = true
}
