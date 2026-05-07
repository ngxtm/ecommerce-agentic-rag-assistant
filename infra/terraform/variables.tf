variable "project_name" {
  description = "Project name used for resource tagging and defaults."
  type        = string
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
}

variable "aws_region" {
  description = "AWS region for all deployed resources."
  type        = string
  default     = "us-east-1"
}

variable "additional_tags" {
  description = "Additional resource tags."
  type        = map(string)
  default     = {}
}

variable "app_env" {
  description = "Application environment value injected into Lambda."
  type        = string
  default     = "cloud"
}

variable "lambda_function_name" {
  description = "Lambda function name."
  type        = string
}

variable "lambda_handler" {
  description = "Lambda handler path."
  type        = string
  default     = "run.sh"
}

variable "lambda_runtime" {
  description = "Lambda runtime version."
  type        = string
  default     = "python3.12"
}

variable "lambda_architecture" {
  description = "CPU architecture used by Lambda functions."
  type        = string
  default     = "x86_64"

  validation {
    condition     = contains(["x86_64", "arm64"], var.lambda_architecture)
    error_message = "lambda_architecture must be x86_64 or arm64."
  }
}

variable "lambda_timeout_seconds" {
  description = "Lambda timeout in seconds."
  type        = number
  default     = 60
}

variable "lambda_memory_mb" {
  description = "Lambda memory size in MB."
  type        = number
  default     = 1024
}

variable "lambda_artifact_path" {
  description = "Path to the Lambda zip artifact."
  type        = string
}

variable "ingestion_lambda_handler" {
  description = "Lambda handler path for the ingestion worker."
  type        = string
  default     = "app.backend.ingestion_handler.handler"
}

variable "ingestion_lambda_timeout_seconds" {
  description = "Ingestion Lambda timeout in seconds."
  type        = number
  default     = 120
}

variable "ingestion_lambda_memory_mb" {
  description = "Ingestion Lambda memory size in MB."
  type        = number
  default     = 1024
}

variable "lambda_log_retention_days" {
  description = "CloudWatch log retention in days for the Lambda log group."
  type        = number
  default     = 14
}

variable "enable_xray" {
  description = "Enable X-Ray tracing for the Lambda function."
  type        = bool
  default     = true
}

variable "conversation_table_name" {
  description = "DynamoDB table name for session and message persistence."
  type        = string
}

variable "orders_table_name" {
  description = "DynamoDB table name for verified order lookups."
  type        = string
  default     = null
  nullable    = true
}

variable "order_tool_function_name" {
  description = "Lambda function name for the order status tool."
  type        = string
  default     = null
  nullable    = true
}

variable "order_tool_handler" {
  description = "Lambda handler path for the order status tool."
  type        = string
  default     = "app.backend.order_tool_handler.handler"
}

variable "order_tool_timeout_seconds" {
  description = "Order status tool Lambda timeout in seconds."
  type        = number
  default     = 15
}

variable "order_tool_memory_mb" {
  description = "Order status tool Lambda memory size in MB."
  type        = number
  default     = 256
}

variable "memory_ttl_days" {
  description = "TTL in days for conversation/session records."
  type        = number
  default     = 7
}

variable "api_name" {
  description = "API Gateway REST API name."
  type        = string
}

variable "api_stage_name" {
  description = "API Gateway stage name."
  type        = string
  default     = "prod"
}

variable "lambda_web_adapter_layer_version" {
  description = "Published Lambda Web Adapter layer version to attach to the backend Lambda."
  type        = number
  default     = 25
}

variable "create_docs_bucket" {
  description = "Create the docs bucket as part of the Terraform-managed stack."
  type        = bool
  default     = true
}

variable "docs_bucket_name" {
  description = "Optional override for the docs bucket name. If unset, Terraform derives a globally unique name."
  type        = string
  default     = null
  nullable    = true
}

variable "docs_s3_prefix" {
  description = "S3 prefix where document knowledge assets are stored."
  type        = string
  default     = "phase1-kb/"
}

variable "ingestion_state_table_name" {
  description = "Optional override for the DynamoDB table that tracks document ingestion state."
  type        = string
  default     = null
  nullable    = true
}

variable "ingestion_state_ttl_days" {
  description = "TTL in days for ingestion state records."
  type        = number
  default     = 30
}

variable "enable_docs_ingestion_trigger" {
  description = "Enable S3 event notifications that invoke the ingestion Lambda when documents are uploaded."
  type        = bool
  default     = true
}

variable "docs_ingestion_suffixes" {
  description = "Object suffixes that should trigger document ingestion."
  type        = list(string)
  default     = [".pdf", ".md", ".txt", ".docx"]
}

variable "opensearch_collection_name" {
  description = "OpenSearch Serverless collection name managed by Terraform."
  type        = string
}

variable "opensearch_collection_type" {
  description = "OpenSearch Serverless collection type."
  type        = string
  default     = "SEARCH"

  validation {
    condition     = contains(["SEARCH", "TIMESERIES", "VECTORSEARCH"], var.opensearch_collection_type)
    error_message = "opensearch_collection_type must be SEARCH, TIMESERIES, or VECTORSEARCH."
  }
}

variable "opensearch_allow_public_access" {
  description = "Allow public network access to the OpenSearch Serverless collection."
  type        = bool
  default     = true
}

variable "opensearch_additional_principal_arns" {
  description = "Additional IAM principal ARNs allowed to access the OpenSearch Serverless collection for local indexing or admin operations."
  type        = list(string)
  default     = []
}

variable "opensearch_local_iam_user_names" {
  description = "IAM user names that should also receive identity-based AOSS API permissions for local indexing workflows."
  type        = list(string)
  default     = []
}

variable "opensearch_index_name" {
  description = "OpenSearch index name that stores chunked documents."
  type        = string
  default     = "policy-faq-chunks"
}

variable "llm_provider" {
  description = "LLM provider used by the deployed fallback architecture."
  type        = string
  default     = "openai_compatible"
}

variable "llm_api_key" {
  description = "API key stored in AWS Secrets Manager for the deployed Lambda runtime."
  type        = string
  sensitive   = true
}

variable "llm_api_key_secret_name" {
  description = "Secrets Manager secret name that stores the LLM API key as a plain string."
  type        = string
  default     = null
  nullable    = true
}

variable "llm_base_url" {
  description = "Base URL for the OpenAI-compatible generation endpoint."
  type        = string
}

variable "llm_model" {
  description = "Model identifier for grounded generation."
  type        = string
}

variable "llm_timeout_seconds" {
  description = "Timeout for the external generation request in seconds."
  type        = number
  default     = 30
}
