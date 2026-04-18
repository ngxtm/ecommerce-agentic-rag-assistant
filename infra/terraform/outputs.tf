output "api_url" {
  description = "Base URL for the deployed API Gateway HTTP API."
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "lambda_function_name" {
  description = "Backend Lambda function name."
  value       = aws_lambda_function.backend.function_name
}

output "conversation_table_name" {
  description = "DynamoDB table name for conversation persistence."
  value       = aws_dynamodb_table.conversation.name
}

output "docs_bucket_name" {
  description = "S3 docs bucket name used by the deployed backend."
  value       = local.docs_bucket_name
}

output "aws_region" {
  description = "AWS region used by this deployment."
  value       = var.aws_region
}
