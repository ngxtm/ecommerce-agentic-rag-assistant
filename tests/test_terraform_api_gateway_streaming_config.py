from pathlib import Path


def test_terraform_backend_keeps_lambda_web_adapter_in_response_stream_mode() -> None:
    main_tf = Path("infra/terraform/main.tf").read_text(encoding="utf-8")

    assert 'AWS_LWA_INVOKE_MODE               = "response_stream"' in main_tf


def test_terraform_health_and_chat_use_response_streaming_integration() -> None:
    apigateway_tf = Path("infra/terraform/apigateway.tf").read_text(encoding="utf-8")

    assert apigateway_tf.count('uri                     = local.backend_response_streaming_invoke_uri') == 3
    assert apigateway_tf.count('response_transfer_mode  = "STREAM"') == 3
    assert 'uri                     = aws_lambda_function.backend.invoke_arn' not in apigateway_tf
