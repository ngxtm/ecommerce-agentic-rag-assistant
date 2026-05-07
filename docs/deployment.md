# Deployment Guide

This document is a short runbook for packaging, deploying, verifying, and reindexing the current cloud backend.

Current deployed backend path:

- `FastAPI` on `AWS Lambda` through `Mangum`
- `API Gateway HTTP API`
- `DynamoDB` for session and message persistence
- `OpenSearch Serverless` for retrieval
- `OpenAI-compatible API` for answer generation

## Prerequisites

- Terraform installed
- valid AWS credentials available in the current shell, or a named `AWS_PROFILE`
- `infra/terraform/terraform.tfvars` configured for your environment
- Python virtual environment available if you package or reindex from local

Default Lambda artifact path:

- `artifacts/backend-lambda.zip`

## Package The Backend

Run:

```powershell
python scripts/package_lambda.py
```

Expected output artifact:

- `artifacts/backend-lambda.zip`

If packaging fails on Windows because `build/lambda` is locked, clear the stale build directory or package into a clean temporary directory before redeploying.

## Terraform Deploy

Initialize and validate:

```powershell
terraform -chdir=infra/terraform init
terraform -chdir=infra/terraform validate
```

Apply:

```powershell
terraform -chdir=infra/terraform apply
```

If you use a named AWS profile:

```powershell
$env:AWS_PROFILE='minh-duykhanh'
terraform -chdir=infra/terraform apply
```

Capture outputs:

```powershell
terraform -chdir=infra/terraform output -json
```

Useful outputs include:

- `api_url`
- `lambda_function_name`
- `opensearch_collection_endpoint`
- `conversation_table_name`

## Important Inputs

The main Terraform inputs for the backend deploy are:

- `lambda_artifact_path`
- `llm_api_key`
- `llm_base_url`
- `llm_model`
- `opensearch_collection_name`
- `opensearch_index_name`
- `docs_bucket_name`

Terraform variables are infrastructure inputs. Lambda environment variables are the runtime values injected by Terraform.

Examples:

- `TF_VAR_llm_api_key` -> `LLM_API_KEY`
- `TF_VAR_opensearch_collection_name` -> Terraform-managed collection -> `OPENSEARCH_COLLECTION_ENDPOINT`
- `TF_VAR_docs_bucket_name` -> `DOCS_S3_BUCKET`

## Post-Deploy Verification

### Health endpoint

```powershell
Invoke-RestMethod -Uri '<API_URL>/health'
```

Expected response:

```json
{"status":"ok"}
```

### Grounded knowledge query

```powershell
$body = @{ session_id='deploy-kb-001'; message="What does Amazon's business focus on?" } | ConvertTo-Json
Invoke-RestMethod -Uri '<API_URL>/chat' -Method Post -ContentType 'application/json' -Body $body | ConvertTo-Json -Depth 8
```

Check that the response includes:

- `intent = KNOWLEDGE_QA`
- a grounded answer
- a short `sources` list

### Conservative fallback query

```powershell
$body = @{ session_id='deploy-kb-002'; message='What is the return policy?' } | ConvertTo-Json
Invoke-RestMethod -Uri '<API_URL>/chat' -Method Post -ContentType 'application/json' -Body $body | ConvertTo-Json -Depth 8
```

Check that the answer does not fabricate unsupported information.

### Order workflow query

```powershell
$body = @{ session_id='deploy-order-001'; message='Where is my order?' } | ConvertTo-Json
Invoke-RestMethod -Uri '<API_URL>/chat' -Method Post -ContentType 'application/json' -Body $body | ConvertTo-Json -Depth 8
```

Check that the response asks for verification fields instead of returning order data immediately.

## Reindex Corpus

Run:

```powershell
.venv\Scripts\python.exe scripts/index_sample_docs.py
```

If you use a named AWS profile:

```powershell
$env:AWS_PROFILE='minh-duykhanh'
.venv\Scripts\python.exe scripts/index_sample_docs.py
```

If indexing from a local machine, make sure the local IAM user or role is allowed by both:

- the OpenSearch Serverless data access policy
- any required identity-based `aoss:APIAccessAll` permission

When chunking logic or `INDEX_SCHEMA_VERSION` changes, always do both:

- rebuild and redeploy Lambda artifact
- reindex or reupload documents so new chunks are written with the new `index_version`

Until reindex completes, retrieval will intentionally ignore older chunks that were written under the previous schema version.

## Evidence Map

Deployment and verification artifacts currently live under `evidence/phase3/`.

Useful files include:

- `terraform-output.json`
- `health.json`
- `knowledge-success.json`
- `knowledge-fallback.json`
- `order-success.json`
- `dynamodb-query.json`
- `cloudwatch-snippet.txt`
- `frontend-cloud.html`

## Troubleshooting

### No valid credential sources found

- export or set `AWS_PROFILE`
- confirm the active shell can access AWS credentials

### Terraform state file lock or partial lock

- wait for the current apply to finish
- rerun `terraform output -json` or `terraform apply` after the lock clears

### Lambda packaging fails on Windows

- clear stale build output under `build/lambda`
- retry packaging from a clean directory if a previous Python process locked files

### Knowledge retrieval returns no useful results

- confirm `OPENSEARCH_COLLECTION_ENDPOINT` is correct
- confirm the deployed Lambda role can access AOSS
- confirm the target index was created and the corpus was reindexed

### Local indexing fails but deployed retrieval works

- confirm your local IAM user or role is included in the AOSS access policy
- confirm your local principal has any required identity-based AOSS permissions
