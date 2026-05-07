from pathlib import Path

def test_terraform_main_injects_embedding_provider_env_into_backend_and_ingestion() -> None:
    main_tf = Path("infra/terraform/main.tf").read_text(encoding="utf-8")

    assert 'LLM_EMBEDDING_BASE_URL' in main_tf
    assert 'LLM_EMBEDDING_MODEL' in main_tf
    assert 'LLM_EMBEDDING_DIMENSIONS' in main_tf
    assert 'LLM_EMBEDDING_API_KEY_SECRET_NAME' in main_tf

def test_terraform_variables_define_embedding_provider_inputs() -> None:
    variables_tf = Path("infra/terraform/variables.tf").read_text(encoding="utf-8")

    assert 'variable "llm_embedding_base_url"' in variables_tf
    assert 'variable "llm_embedding_model"' in variables_tf
    assert 'variable "llm_embedding_dimensions"' in variables_tf
    assert 'variable "llm_embedding_api_key"' in variables_tf
    assert 'variable "llm_embedding_api_key_secret_name"' in variables_tf

def test_terraform_creates_embedding_secret_resource() -> None:
    secrets_tf = Path("infra/terraform/secrets.tf").read_text(encoding="utf-8")

    assert 'resource "aws_secretsmanager_secret" "llm_embedding_api_key"' in secrets_tf
    assert 'resource "aws_secretsmanager_secret_version" "llm_embedding_api_key"' in secrets_tf

def test_terraform_iam_allows_backend_and_ingestion_to_read_embedding_secret() -> None:
    iam_tf = Path("infra/terraform/iam.tf").read_text(encoding="utf-8")

    assert 'aws_secretsmanager_secret.llm_embedding_api_key.arn' in iam_tf

def test_terraform_examples_lock_openrouter_qwen_embedding_defaults() -> None:
    tfvars_example = Path("infra/terraform/terraform.tfvars.example").read_text(encoding="utf-8")

    assert 'llm_embedding_base_url    = "https://openrouter.ai/api/v1"' in tfvars_example
    assert 'llm_embedding_model       = "qwen/qwen3-embedding-8b"' in tfvars_example
    assert 'llm_embedding_dimensions  = 4096' in tfvars_example
