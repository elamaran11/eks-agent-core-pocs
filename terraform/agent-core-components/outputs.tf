output "agent_memory_kb_id" {
  description = "Agent Core Memory Knowledge Base ID"
  value       = aws_bedrockagent_knowledge_base.agent_memory.id
}

output "agent_memory_kb_arn" {
  description = "Agent Core Memory Knowledge Base ARN"
  value       = aws_bedrockagent_knowledge_base.agent_memory.arn
}

output "code_interpreter_arn" {
  description = "Code Interpreter ARN"
  value       = aws_bedrockagentcore_code_interpreter.code_interpreter.arn
}

output "code_interpreter_id" {
  description = "Code Interpreter ID"
  value       = aws_bedrockagentcore_code_interpreter.code_interpreter.id
}

output "browser_arn" {
  description = "Browser ARN"
  value       = aws_bedrockagentcore_browser.browser.arn
}

output "browser_id" {
  description = "Browser ID"
  value       = aws_bedrockagentcore_browser.browser.id
}

output "strands_agent_role_arn" {
  description = "IAM Role ARN for Strands Agent"
  value       = aws_iam_role.strands_agent_role.arn
}
