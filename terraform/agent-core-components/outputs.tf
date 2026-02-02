output "memory_id" {
  description = "Memory ID"
  value       = var.enable_memory ? module.memory[0].memory_id : null
}

output "browser_id" {
  description = "Browser ID"
  value       = var.enable_browser ? module.browser[0].browser_id : null
}

output "browser_arn" {
  description = "Browser ARN"
  value       = var.enable_browser ? module.browser[0].browser_arn : null
}

output "code_interpreter_id" {
  description = "Code Interpreter ID"
  value       = var.enable_code_interpreter ? module.code_interpreter[0].code_interpreter_id : null
}

output "code_interpreter_arn" {
  description = "Code Interpreter ARN"
  value       = var.enable_code_interpreter ? module.code_interpreter[0].code_interpreter_arn : null
}

output "strands_agent_role_arn" {
  description = "IAM Role ARN for Strands Agent"
  value       = aws_iam_role.strands_agent_role.arn
}
