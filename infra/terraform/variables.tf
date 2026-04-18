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
  default     = "app.backend.handler.handler"
}

variable "lambda_runtime" {
  description = "Lambda runtime version."
  type        = string
  default     = "python3.12"
}

variable "lambda_timeout_seconds" {
  description = "Lambda timeout in seconds."
  type        = number
  default     = 30
}

variable "lambda_memory_mb" {
  description = "Lambda memory size in MB."
  type        = number
  default     = 512
}

variable "lambda_artifact_path" {
  description = "Path to the Lambda zip artifact."
  type        = string
}

variable "lambda_log_retention_days" {
  description = "CloudWatch log retention in days for the Lambda log group."
  type        = number
  default     = 14
}

variable "enable_xray" {
  description = "Enable X-Ray tracing for the Lambda function."
  type        = bool
  default     = false
}

variable "conversation_table_name" {
  description = "DynamoDB table name for session and message persistence."
  type        = string
}

variable "memory_ttl_days" {
  description = "TTL in days for conversation/session records."
  type        = number
  default     = 7
}

variable "api_name" {
  description = "API Gateway HTTP API name."
  type        = string
}

variable "api_stage_name" {
  description = "API Gateway stage name."
  type        = string
  default     = "$default"
}

variable "create_docs_bucket" {
  description = "Create the docs bucket instead of referencing an existing one."
  type        = bool
  default     = false
}

variable "docs_bucket_name" {
  description = "Docs bucket name, either created by Terraform or reused if it already exists."
  type        = string
}

variable "docs_s3_prefix" {
  description = "S3 prefix where document knowledge assets are stored."
  type        = string
  default     = "phase1-kb/"
}

variable "opensearch_collection_endpoint" {
  description = "OpenSearch Serverless collection endpoint used by the fallback deployed architecture."
  type        = string
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
  description = "API key Terraform injects into the Lambda runtime as LLM_API_KEY."
  type        = string
  sensitive   = true
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
