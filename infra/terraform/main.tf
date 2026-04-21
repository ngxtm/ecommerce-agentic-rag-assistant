locals {
  base_tags = merge(
    {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
      Phase       = "phase3"
    },
    var.additional_tags,
  )

  docs_bucket_name = var.docs_bucket_name

  lambda_environment = {
    APP_ENV                        = var.app_env
    MEMORY_BACKEND                 = "dynamodb"
    MEMORY_TTL_DAYS                = tostring(var.memory_ttl_days)
    DYNAMODB_CONVERSATION_TABLE    = aws_dynamodb_table.conversation.name
    ORDER_TOOL_FUNCTION_NAME       = aws_lambda_function.order_tool.function_name
    DOCS_S3_BUCKET                 = local.docs_bucket_name
    DOCS_S3_PREFIX                 = var.docs_s3_prefix
    OPENSEARCH_COLLECTION_ENDPOINT = aws_opensearchserverless_collection.knowledge.collection_endpoint
    OPENSEARCH_INDEX_NAME          = var.opensearch_index_name
    LLM_PROVIDER                   = var.llm_provider
    LLM_API_KEY_SECRET_NAME        = aws_secretsmanager_secret.llm_api_key.name
    LLM_BASE_URL                   = var.llm_base_url
    LLM_MODEL                      = var.llm_model
    LLM_TIMEOUT_SECONDS            = tostring(var.llm_timeout_seconds)
  }

  order_tool_environment = {
    APP_ENV           = var.app_env
    ORDERS_TABLE_NAME = aws_dynamodb_table.orders.name
  }

  docs_bucket_arn    = "arn:aws:s3:::${local.docs_bucket_name}"
  docs_bucket_prefix = trim(var.docs_s3_prefix, "/")
  docs_prefix_arn    = local.docs_bucket_prefix == "" ? local.docs_bucket_arn : "${local.docs_bucket_arn}/${local.docs_bucket_prefix}/*"
}
