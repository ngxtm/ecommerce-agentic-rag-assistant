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
