output "api_url" {
  description = "Base URL for the deployed API Gateway REST API."
  value       = "https://${aws_api_gateway_rest_api.rest.id}.execute-api.${var.aws_region}.amazonaws.com/${aws_api_gateway_stage.default.stage_name}"
}

output "lambda_function_name" {
  description = "Backend Lambda function name."
  value       = aws_lambda_function.backend.function_name
}

output "conversation_table_name" {
  description = "DynamoDB table name for conversation persistence."
  value       = aws_dynamodb_table.conversation.name
}

output "orders_table_name" {
  description = "DynamoDB table name for verified order lookups."
  value       = aws_dynamodb_table.orders.name
}

output "order_tool_function_name" {
  description = "Order tool Lambda function name."
  value       = aws_lambda_function.order_tool.function_name
}

output "llm_api_key_secret_name" {
  description = "Secrets Manager secret name used for the LLM API key."
  value       = aws_secretsmanager_secret.llm_api_key.name
}

output "docs_bucket_name" {
  description = "S3 docs bucket name used by the deployed backend."
  value       = local.docs_bucket_name
}

output "docs_s3_prefix" {
  description = "S3 prefix used for document ingestion uploads."
  value       = var.docs_s3_prefix
}

output "ingestion_lambda_function_name" {
  description = "Ingestion Lambda function name."
  value       = aws_lambda_function.ingestion.function_name
}

output "ingestion_state_table_name" {
  description = "DynamoDB table name that tracks document ingestion state."
  value       = aws_dynamodb_table.ingestion_state.name
}

output "aws_region" {
  description = "AWS region used by this deployment."
  value       = var.aws_region
}

output "opensearch_collection_name" {
  description = "OpenSearch Serverless collection name used by the deployed backend."
  value       = aws_opensearchserverless_collection.knowledge.name
}

output "opensearch_collection_arn" {
  description = "ARN of the OpenSearch Serverless collection."
  value       = aws_opensearchserverless_collection.knowledge.arn
}

output "opensearch_collection_endpoint" {
  description = "Collection endpoint for OpenSearch Serverless."
  value       = aws_opensearchserverless_collection.knowledge.collection_endpoint
}

output "opensearch_dashboard_endpoint" {
  description = "Dashboard endpoint for OpenSearch Serverless."
  value       = aws_opensearchserverless_collection.knowledge.dashboard_endpoint
}
