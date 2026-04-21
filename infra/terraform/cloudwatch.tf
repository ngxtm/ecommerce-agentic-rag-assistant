resource "aws_cloudwatch_metric_alarm" "backend_lambda_errors" {
  alarm_name          = "${var.lambda_function_name}-errors"
  alarm_description   = "Alarm when the backend Lambda reports errors."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 0

  dimensions = {
    FunctionName = aws_lambda_function.backend.function_name
  }

  tags = local.base_tags
}

resource "aws_cloudwatch_metric_alarm" "order_tool_lambda_errors" {
  alarm_name          = "${var.order_tool_function_name}-errors"
  alarm_description   = "Alarm when the order tool Lambda reports errors."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 0

  dimensions = {
    FunctionName = aws_lambda_function.order_tool.function_name
  }

  tags = local.base_tags
}

resource "aws_cloudwatch_metric_alarm" "backend_lambda_duration" {
  alarm_name          = "${var.lambda_function_name}-duration-p95"
  alarm_description   = "Alarm when the backend Lambda p95 duration is high."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = 300
  extended_statistic  = "p95"
  threshold           = 20000

  dimensions = {
    FunctionName = aws_lambda_function.backend.function_name
  }

  tags = local.base_tags
}

resource "aws_cloudwatch_metric_alarm" "api_gateway_5xx" {
  alarm_name          = "${var.api_name}-5xx"
  alarm_description   = "Alarm when API Gateway returns 5XX responses."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "5xx"
  namespace           = "AWS/ApiGateway"
  period              = 300
  statistic           = "Sum"
  threshold           = 0

  dimensions = {
    ApiId = aws_apigatewayv2_api.http.id
    Stage = aws_apigatewayv2_stage.default.name
  }

  tags = local.base_tags
}
