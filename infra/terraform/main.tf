locals {
  default_orders_table_name              = "agentic-commerce-orders-${var.environment}"
  default_order_tool_function            = "agentic-commerce-order-tool-${var.environment}"
  default_llm_api_key_secret             = "agentic-commerce-llm-api-key-${var.environment}"
  default_llm_embedding_api_key_secret   = "agentic-commerce-llm-embedding-api-key-${var.environment}"
  default_docs_bucket_name               = lower("agentic-commerce-docs-${var.environment}-${var.aws_region}-${data.aws_caller_identity.current.account_id}")
  default_ingestion_state_table          = "agentic-commerce-ingestion-state-${var.environment}"
  ingestion_lambda_function_name         = "agentic-commerce-ingestion-${var.environment}"
  effective_orders_table_name            = coalesce(var.orders_table_name, local.default_orders_table_name)
  effective_order_tool_function          = coalesce(var.order_tool_function_name, local.default_order_tool_function)
  effective_llm_api_key_secret           = coalesce(var.llm_api_key_secret_name, local.default_llm_api_key_secret)
  effective_llm_embedding_api_key_secret = coalesce(var.llm_embedding_api_key_secret_name, local.default_llm_embedding_api_key_secret)
  effective_docs_bucket_name             = coalesce(var.docs_bucket_name, local.default_docs_bucket_name)
  effective_ingestion_state_table        = coalesce(var.ingestion_state_table_name, local.default_ingestion_state_table)
  lambda_web_adapter_layer_name          = var.lambda_architecture == "arm64" ? "LambdaAdapterLayerArm64" : "LambdaAdapterLayerX86"
  lambda_web_adapter_layer_arn           = "arn:aws:lambda:${var.aws_region}:753240598075:layer:${local.lambda_web_adapter_layer_name}:${var.lambda_web_adapter_layer_version}"
  backend_response_streaming_invoke_uri  = "arn:${data.aws_partition.current.partition}:apigateway:${var.aws_region}:lambda:path/2021-11-15/functions/${aws_lambda_function.backend.arn}/response-streaming-invocations"

  base_tags = merge(
    {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
      Phase       = "phase3"
    },
    var.additional_tags,
  )

  docs_bucket_name = local.effective_docs_bucket_name

  lambda_environment = {
    APP_ENV                           = var.app_env
    MEMORY_BACKEND                    = "dynamodb"
    MEMORY_TTL_DAYS                   = tostring(var.memory_ttl_days)
    DYNAMODB_CONVERSATION_TABLE       = aws_dynamodb_table.conversation.name
    ORDER_TOOL_FUNCTION_NAME          = aws_lambda_function.order_tool.function_name
    DOCS_S3_BUCKET                    = local.docs_bucket_name
    DOCS_S3_PREFIX                    = var.docs_s3_prefix
    OPENSEARCH_COLLECTION_ENDPOINT    = aws_opensearchserverless_collection.knowledge.collection_endpoint
    OPENSEARCH_INDEX_NAME             = var.opensearch_index_name
    LLM_PROVIDER                      = var.llm_provider
    LLM_API_KEY_SECRET_NAME           = aws_secretsmanager_secret.llm_api_key.name
    LLM_BASE_URL                      = var.llm_base_url
    LLM_MODEL                         = var.llm_model
    LLM_EMBEDDING_BASE_URL            = coalesce(var.llm_embedding_base_url, var.llm_base_url)
    LLM_EMBEDDING_MODEL               = coalesce(var.llm_embedding_model, var.llm_model)
    LLM_EMBEDDING_DIMENSIONS          = tostring(var.llm_embedding_dimensions)
    LLM_EMBEDDING_API_KEY_SECRET_NAME = aws_secretsmanager_secret.llm_embedding_api_key.name
    LLM_TIMEOUT_SECONDS               = tostring(var.llm_timeout_seconds)
    PORT                              = "8080"
    AWS_LAMBDA_EXEC_WRAPPER           = "/opt/bootstrap"
    AWS_LWA_INVOKE_MODE               = "response_stream"
    AWS_LWA_READINESS_CHECK_PATH      = "/health"
  }

  order_tool_environment = {
    APP_ENV           = var.app_env
    ORDERS_TABLE_NAME = aws_dynamodb_table.orders.name
  }

  ingestion_lambda_environment = {
    APP_ENV                           = var.app_env
    DOCS_S3_BUCKET                    = local.docs_bucket_name
    DOCS_S3_PREFIX                    = var.docs_s3_prefix
    OPENSEARCH_COLLECTION_ENDPOINT    = aws_opensearchserverless_collection.knowledge.collection_endpoint
    OPENSEARCH_INDEX_NAME             = var.opensearch_index_name
    LLM_BASE_URL                      = var.llm_base_url
    LLM_MODEL                         = var.llm_model
    LLM_EMBEDDING_BASE_URL            = coalesce(var.llm_embedding_base_url, var.llm_base_url)
    LLM_EMBEDDING_MODEL               = coalesce(var.llm_embedding_model, var.llm_model)
    LLM_EMBEDDING_DIMENSIONS          = tostring(var.llm_embedding_dimensions)
    LLM_API_KEY_SECRET_NAME           = aws_secretsmanager_secret.llm_api_key.name
    LLM_EMBEDDING_API_KEY_SECRET_NAME = aws_secretsmanager_secret.llm_embedding_api_key.name
    INGESTION_STATE_TABLE_NAME        = aws_dynamodb_table.ingestion_state.name
  }

  docs_bucket_arn    = "arn:aws:s3:::${local.docs_bucket_name}"
  docs_bucket_prefix = trim(var.docs_s3_prefix, "/")
  docs_prefix_arn    = local.docs_bucket_prefix == "" ? local.docs_bucket_arn : "${local.docs_bucket_arn}/${local.docs_bucket_prefix}/*"
}
