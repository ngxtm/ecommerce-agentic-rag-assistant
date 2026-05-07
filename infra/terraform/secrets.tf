resource "aws_secretsmanager_secret" "llm_api_key" {
  name = local.effective_llm_api_key_secret

  tags = local.base_tags
}

resource "aws_secretsmanager_secret_version" "llm_api_key" {
  secret_id     = aws_secretsmanager_secret.llm_api_key.id
  secret_string = var.llm_api_key
}

resource "aws_secretsmanager_secret" "llm_embedding_api_key" {
  name = local.effective_llm_embedding_api_key_secret

  tags = local.base_tags
}

resource "aws_secretsmanager_secret_version" "llm_embedding_api_key" {
  secret_id     = aws_secretsmanager_secret.llm_embedding_api_key.id
  secret_string = coalesce(var.llm_embedding_api_key, var.llm_api_key)
}
