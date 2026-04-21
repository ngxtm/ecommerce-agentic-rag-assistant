resource "aws_secretsmanager_secret" "llm_api_key" {
  name = var.llm_api_key_secret_name

  tags = local.base_tags
}

resource "aws_secretsmanager_secret_version" "llm_api_key" {
  secret_id     = aws_secretsmanager_secret.llm_api_key.id
  secret_string = var.llm_api_key
}
