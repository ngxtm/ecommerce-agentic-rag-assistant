resource "aws_api_gateway_rest_api" "rest" {
  name = var.api_name

  tags = local.base_tags
}

resource "aws_api_gateway_resource" "health" {
  rest_api_id = aws_api_gateway_rest_api.rest.id
  parent_id   = aws_api_gateway_rest_api.rest.root_resource_id
  path_part   = "health"
}

resource "aws_api_gateway_resource" "chat" {
  rest_api_id = aws_api_gateway_rest_api.rest.id
  parent_id   = aws_api_gateway_rest_api.rest.root_resource_id
  path_part   = "chat"
}

resource "aws_api_gateway_resource" "chat_stream" {
  rest_api_id = aws_api_gateway_rest_api.rest.id
  parent_id   = aws_api_gateway_resource.chat.id
  path_part   = "stream"
}

resource "aws_api_gateway_method" "health" {
  rest_api_id   = aws_api_gateway_rest_api.rest.id
  resource_id   = aws_api_gateway_resource.health.id
  http_method   = "GET"
  authorization = "NONE"
}

resource "aws_api_gateway_method" "chat" {
  rest_api_id   = aws_api_gateway_rest_api.rest.id
  resource_id   = aws_api_gateway_resource.chat.id
  http_method   = "POST"
  authorization = "NONE"
}

resource "aws_api_gateway_method" "chat_stream" {
  rest_api_id   = aws_api_gateway_rest_api.rest.id
  resource_id   = aws_api_gateway_resource.chat_stream.id
  http_method   = "POST"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "health" {
  rest_api_id             = aws_api_gateway_rest_api.rest.id
  resource_id             = aws_api_gateway_resource.health.id
  http_method             = aws_api_gateway_method.health.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = local.backend_response_streaming_invoke_uri
  response_transfer_mode  = "STREAM"
  timeout_milliseconds    = min(var.lambda_timeout_seconds * 1000, 900000)
}

resource "aws_api_gateway_integration" "chat" {
  rest_api_id             = aws_api_gateway_rest_api.rest.id
  resource_id             = aws_api_gateway_resource.chat.id
  http_method             = aws_api_gateway_method.chat.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = local.backend_response_streaming_invoke_uri
  response_transfer_mode  = "STREAM"
  timeout_milliseconds    = min(var.lambda_timeout_seconds * 1000, 900000)
}

resource "aws_api_gateway_integration" "chat_stream" {
  rest_api_id             = aws_api_gateway_rest_api.rest.id
  resource_id             = aws_api_gateway_resource.chat_stream.id
  http_method             = aws_api_gateway_method.chat_stream.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = local.backend_response_streaming_invoke_uri
  response_transfer_mode  = "STREAM"
  timeout_milliseconds    = min(var.lambda_timeout_seconds * 1000, 900000)
}

resource "aws_api_gateway_deployment" "current" {
  rest_api_id = aws_api_gateway_rest_api.rest.id

  triggers = {
    redeployment = sha1(
      jsonencode(
        [
          aws_api_gateway_resource.health.id,
          aws_api_gateway_resource.chat.id,
          aws_api_gateway_resource.chat_stream.id,
          aws_api_gateway_method.health.id,
          aws_api_gateway_method.chat.id,
          aws_api_gateway_method.chat_stream.id,
          aws_api_gateway_integration.health.id,
          aws_api_gateway_integration.chat.id,
          aws_api_gateway_integration.chat_stream.id,
          aws_lambda_function.backend.source_code_hash,
        ]
      )
    )
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [
    aws_api_gateway_integration.health,
    aws_api_gateway_integration.chat,
    aws_api_gateway_integration.chat_stream,
  ]
}

resource "aws_api_gateway_stage" "default" {
  rest_api_id          = aws_api_gateway_rest_api.rest.id
  deployment_id        = aws_api_gateway_deployment.current.id
  stage_name           = var.api_stage_name
  xray_tracing_enabled = var.enable_xray

  tags = local.base_tags
}

resource "aws_api_gateway_method_settings" "all" {
  rest_api_id = aws_api_gateway_rest_api.rest.id
  stage_name  = aws_api_gateway_stage.default.stage_name
  method_path = "*/*"

  settings {
    metrics_enabled        = true
    throttling_burst_limit = 100
    throttling_rate_limit  = 50
  }
}

resource "aws_lambda_permission" "apigateway_invoke" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.backend.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.rest.execution_arn}/*"
}
