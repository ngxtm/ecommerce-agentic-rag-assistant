data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${var.lambda_function_name}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = local.base_tags
}

resource "aws_iam_role" "order_tool" {
  name               = "${local.effective_order_tool_function}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = local.base_tags
}

resource "aws_iam_role" "ingestion" {
  name               = "${local.ingestion_lambda_function_name}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = local.base_tags
}

data "aws_iam_policy_document" "lambda_access" {
  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.lambda.arn}:*"]
  }

  statement {
    sid    = "DynamoDBConversationAccess"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
    ]
    resources = [aws_dynamodb_table.conversation.arn]
  }

  statement {
    sid    = "ReadKnowledgeDocsBucket"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:ListBucket",
    ]
    resources = [
      local.docs_bucket_arn,
      local.docs_prefix_arn,
    ]
  }

  statement {
    sid    = "InvokeOrderTool"
    effect = "Allow"
    actions = [
      "lambda:InvokeFunction",
    ]
    resources = [aws_lambda_function.order_tool.arn]
  }

  statement {
    sid    = "ReadLLMApiKeySecret"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
    ]
    resources = [aws_secretsmanager_secret.llm_api_key.arn]
  }

  # AOSS auth can still fail if the OpenSearch Serverless data access policy
  # does not also trust this Lambda role principal.
  statement {
    sid    = "AOSSQueryAccess"
    effect = "Allow"
    actions = [
      "aoss:APIAccessAll",
      "aoss:DashboardsAccessAll",
    ]
    resources = ["*"]
  }

  dynamic "statement" {
    for_each = var.enable_xray ? [1] : []
    content {
      sid    = "XRayWrite"
      effect = "Allow"
      actions = [
        "xray:PutTraceSegments",
        "xray:PutTelemetryRecords",
      ]
      resources = ["*"]
    }
  }
}

resource "aws_iam_role_policy" "lambda_access" {
  name   = "${var.lambda_function_name}-access"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_access.json
}

data "aws_iam_policy_document" "order_tool_access" {
  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.order_tool.arn}:*"]
  }

  statement {
    sid    = "ReadOrdersTable"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
    ]
    resources = [aws_dynamodb_table.orders.arn]
  }

  dynamic "statement" {
    for_each = var.enable_xray ? [1] : []
    content {
      sid    = "XRayWrite"
      effect = "Allow"
      actions = [
        "xray:PutTraceSegments",
        "xray:PutTelemetryRecords",
      ]
      resources = ["*"]
    }
  }
}

resource "aws_iam_role_policy" "order_tool_access" {
  name   = "${local.effective_order_tool_function}-access"
  role   = aws_iam_role.order_tool.id
  policy = data.aws_iam_policy_document.order_tool_access.json
}

data "aws_iam_policy_document" "ingestion_access" {
  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.ingestion.arn}:*"]
  }

  statement {
    sid    = "ReadDocsBucket"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:ListBucket",
    ]
    resources = [
      local.docs_bucket_arn,
      local.docs_prefix_arn,
    ]
  }

  statement {
    sid    = "IngestionStateAccess"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
    ]
    resources = [aws_dynamodb_table.ingestion_state.arn]
  }

  statement {
    sid    = "AOSSIngestionAccess"
    effect = "Allow"
    actions = [
      "aoss:APIAccessAll",
      "aoss:DashboardsAccessAll",
    ]
    resources = ["*"]
  }

  dynamic "statement" {
    for_each = var.enable_xray ? [1] : []
    content {
      sid    = "XRayWrite"
      effect = "Allow"
      actions = [
        "xray:PutTraceSegments",
        "xray:PutTelemetryRecords",
      ]
      resources = ["*"]
    }
  }
}

resource "aws_iam_role_policy" "ingestion_access" {
  name   = "${local.ingestion_lambda_function_name}-access"
  role   = aws_iam_role.ingestion.id
  policy = data.aws_iam_policy_document.ingestion_access.json
}
