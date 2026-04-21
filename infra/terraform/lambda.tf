resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.lambda_function_name}"
  retention_in_days = var.lambda_log_retention_days

  tags = local.base_tags
}

resource "aws_lambda_function" "backend" {
  function_name = var.lambda_function_name
  role          = aws_iam_role.lambda.arn
  runtime       = var.lambda_runtime
  handler       = var.lambda_handler
  timeout       = var.lambda_timeout_seconds
  memory_size   = var.lambda_memory_mb

  filename         = var.lambda_artifact_path
  source_code_hash = filebase64sha256(var.lambda_artifact_path)

  environment {
    variables = local.lambda_environment
  }

  tracing_config {
    mode = var.enable_xray ? "Active" : "PassThrough"
  }

  depends_on = [aws_cloudwatch_log_group.lambda]

  tags = local.base_tags
}

resource "aws_cloudwatch_log_group" "order_tool" {
  name              = "/aws/lambda/${var.order_tool_function_name}"
  retention_in_days = var.lambda_log_retention_days

  tags = local.base_tags
}

resource "aws_lambda_function" "order_tool" {
  function_name = var.order_tool_function_name
  role          = aws_iam_role.order_tool.arn
  runtime       = var.lambda_runtime
  handler       = var.order_tool_handler
  timeout       = var.order_tool_timeout_seconds
  memory_size   = var.order_tool_memory_mb

  filename         = var.lambda_artifact_path
  source_code_hash = filebase64sha256(var.lambda_artifact_path)

  environment {
    variables = local.order_tool_environment
  }

  tracing_config {
    mode = var.enable_xray ? "Active" : "PassThrough"
  }

  depends_on = [aws_cloudwatch_log_group.order_tool]

  tags = local.base_tags
}
