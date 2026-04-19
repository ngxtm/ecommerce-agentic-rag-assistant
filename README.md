# Agentic Commerce Assistant

Agentic conversational assistant for internal knowledge Q&A and verified order status support, built for the Cloud Kinetics Data/AI Solution Architect Intern assignment.

The system supports grounded document answers, a multi-turn order verification workflow, and session memory. The backend has been deployed and verified live on AWS. The current deployed cloud path uses `Lambda + API Gateway + DynamoDB + OpenSearch Serverless + OpenAI-compatible generation`.

## Current Delivery Status
- Phase 1: complete on deployed fallback path
- Phase 2: complete
- Phase 3: complete and deployed
- Phase 4: submission polish in progress

## Assignment Scope
- answer knowledge questions from internal documents via RAG
- handle an order status workflow with required user verification
- maintain multi-turn session context
- demonstrate a credible AWS deployment, observability, and IaC path

## Deployment Scope
Phase 3 is a minimum viable cloud deployment for the assignment: deployable, testable, and interview-defensible. It is not full production hardening, so items like multi-environment rollout strategy, WAF, advanced secrets rotation, and a full monitoring stack are intentionally deferred.

## Target Architecture
- Frontend: `Streamlit`
- API entry: `Amazon API Gateway`
- Backend orchestration: `AWS Lambda`
- RAG: `Amazon Bedrock Knowledge Bases`
- Document store: `Amazon S3`
- Vector store: `S3 Vectors`
- Memory: `DynamoDB`
- Observability: `CloudWatch Logs`, `CloudWatch Metrics`, optional `X-Ray`

## Deployed Fallback Architecture
- Frontend: `Streamlit`
- API entry: `Amazon API Gateway HTTP API`
- Backend orchestration: `AWS Lambda`
- Lambda adapter: `Mangum`
- Retrieval: `Amazon OpenSearch Serverless`
- Grounded generation: `OpenAI-compatible API`
- Document store: `Amazon S3`
- Memory: `DynamoDB`
- Observability: `CloudWatch Logs`, optional `X-Ray`

## Known Architecture Delta
- Target architecture: `Bedrock Knowledge Bases + S3 + S3 Vectors`
- Deployed fallback architecture: `OpenSearch Serverless retrieval + OpenAI-compatible generation`
- Reason: repeated Bedrock throttling, quota, and reliability blockers during implementation
- Rationale: preserve delivery speed, demo reliability, and an interview-defensible cloud baseline without expanding scope

## What Was Implemented
- FastAPI backend with `GET /health` and `POST /chat`
- Streamlit frontend connected to the backend contract
- multi-turn order verification workflow with `full_name`, `date_of_birth`, and `ssn_last4`
- grounded document Q&A through OpenSearch retrieval and OpenAI-compatible generation
- 10-K-only document ingestion centered on a fixed SEC-style PDF corpus
- 10-K-aware preprocessing with SEC `PART` / `Item` segmentation, TOC removal, and Item 6 table extraction
- DynamoDB-backed session and message persistence
- structured logging and PII-aware observability helpers
- Terraform-managed Lambda, API Gateway, DynamoDB, S3, IAM, and log group resources
- GitHub Actions CI and CD support workflows

## Phase 3 Document Pipeline
- The only Phase 3 demonstration corpus is `docs/company/Company-10k-18pages.pdf`.
- The indexing pipeline is intentionally optimized for one known SEC-style 10-K family rather than generic PDF ingestion.
- Retrieval content excludes `Table of Contents` / `INDEX` lines to avoid false hits on the outline instead of the real section text.
- `section` is mapped to retrieval-friendly SEC labels such as `Item 1. Business`, `Item 1A. Risk Factors`, and `Item 6. Selected Consolidated Financial Data`.
- Important Item 6 financial data is indexed in two forms:
  - `table_row` chunks for numeric QA
  - `table_block` chunks for broader contextual grounding
- The first iteration keeps structured table handling deliberately narrow: Item 6 is parsed carefully, while lower-priority table-like sections fall back to text blocks.
- Reindexing removes prior chunks for `doc_id=amazon_10k_2019` before inserting the updated PDF chunks to prevent duplicate search results.

## Deployment Result
- Phase 3 backend deployment completed successfully on AWS
- deployed API outputs were captured in `evidence/phase3/terraform-output.json`
- local Streamlit was validated against the deployed backend, with response evidence captured in `evidence/phase3/frontend-cloud.html`

## Evidence Index
- `evidence/phase3/terraform-output.json` - Terraform deployment outputs
- `evidence/phase3/health.json` - deployed health endpoint response
- `evidence/phase3/knowledge-success.json` - in-context grounded QA response
- `evidence/phase3/knowledge-fallback.json` - out-of-context conservative fallback
- `evidence/phase3/order-success.json` - verified order status response
- `evidence/phase3/dynamodb-query.json` - DynamoDB session and message persistence proof
- `evidence/phase3/cloudwatch-snippet.txt` - Lambda execution log evidence
- `evidence/phase3/frontend-cloud.html` - local Streamlit served against cloud backend

## Verification Summary
- `/health` returns `{"status":"ok"}` on the deployed backend
- knowledge success behavior was verified with grounded document evidence
- fallback behavior was verified with an out-of-context prompt that did not hallucinate
- order verification was verified end-to-end with `DD-MM-YYYY` DOB input
- DynamoDB session and message writes were verified on the deployed table
- CloudWatch Lambda execution logs were captured after live verification

## Infrastructure Layout
- `AWS Lambda` runs the FastAPI backend through `Mangum`
- `API Gateway HTTP API` exposes exactly `GET /health` and `POST /chat`
- `DynamoDB` uses a single-table design with `pk`, `sk`, and `ttl`
- `S3` can be either created by Terraform or reused as an existing docs bucket
- `CloudWatch log group` is managed explicitly by Terraform with `14` day retention

## Terraform Inputs Vs Lambda Runtime Environment
Terraform variables are the infrastructure inputs. Lambda environment variables are the runtime values injected by Terraform.

Examples:
- `TF_VAR_llm_api_key` -> Lambda env `LLM_API_KEY`
- `TF_VAR_opensearch_collection_endpoint` -> Lambda env `OPENSEARCH_COLLECTION_ENDPOINT`
- `TF_VAR_docs_bucket_name` -> Lambda env `DOCS_S3_BUCKET`

## Deployment Defaults
- Lambda runtime: `python3.12`
- Lambda memory: `512 MB`
- Lambda timeout: `30 seconds`
- Lambda log retention: `14 days`
- Packaging script: `scripts/package_lambda.py`
- Packaging format: `artifacts/backend-lambda.zip`

## API Contract

### Request
```json
{
  "session_id": "string",
  "message": "string",
  "user_id": "string optional"
}
```

### Response
```json
{
  "answer": "string",
  "intent": "KNOWLEDGE_QA | ORDER_STATUS | FALLBACK",
  "sources": [
    {
      "source_id": "string",
      "title": "string",
      "snippet": "string"
    }
  ],
  "verification_state": {
    "status": "not_started | collecting | verified",
    "missing_fields": ["full_name", "ssn_last4", "date_of_birth"],
    "verified_fields": ["full_name"]
  },
  "next_action": "ASK_USER | CALL_TOOL | RESPOND"
}
```

## How To Run Locally

### 1. Create and activate a virtual environment
```powershell
python -m venv .venv
.venv\Scripts\activate
```

### 2. Install dependencies
```powershell
pip install -r requirements.txt
```

### 3. Configure environment variables
Copy `.env.example` to `.env` and adjust values if needed.

For the AWS retrieval path, configure at least:

```env
AWS_REGION=us-east-1
LLM_PROVIDER=openai_compatible
LLM_API_KEY=<external-llm-api-key>
LLM_BASE_URL=https://r2lj67q.9router.com/v1
LLM_MODEL=cx/gpt-5.4
LLM_TIMEOUT_SECONDS=30
OPENSEARCH_COLLECTION_ENDPOINT=<aoss-endpoint>
OPENSEARCH_INDEX_NAME=policy-faq-chunks
DOCS_S3_BUCKET=<docs-bucket>
DOCS_S3_PREFIX=
```

`DOCS_S3_PREFIX` is optional. Leave it empty or unset when the source document lives at the bucket root. Set it only when the document key is stored under a prefix such as `filings/`.

### 4. Run the backend
```powershell
uvicorn app.backend.main:app --reload
```

### 5. Run the frontend
```powershell
streamlit run app/frontend/streamlit_app.py
```

### 6. Run tests
```powershell
pytest
```

### 7. Index sample docs into OpenSearch
```powershell
.venv\Scripts\python.exe scripts/index_sample_docs.py
```

## Frontend Deployment with Dokploy
Use this path when the backend is already deployed and you want to publish the Streamlit UI at `rag.ngxtm.site` from your VPS.

### 1. Build from the frontend Dockerfile
Use `Dockerfile.frontend` as the Dokploy build target.

### 2. Configure the frontend environment
Set the Dokploy environment variable:

```env
BACKEND_BASE_URL=<deployed-backend-url>
```

### 3. Use the Streamlit start command
The container starts Streamlit automatically with:

```bash
streamlit run app/frontend/streamlit_app.py --server.port 8501 --server.address 0.0.0.0
```

If you are not using the Dockerfile, you can still install frontend-only dependencies manually with:

```powershell
pip install -r requirements-frontend.txt
```

### 4. Map the Dokploy app to `rag.ngxtm.site`
- point the domain or subdomain to the VPS
- keep the app port and Dokploy domain mapping aligned on `8501`
- enable TLS in Dokploy

### 5. Troubleshoot reverse proxy and WebSocket issues first
Streamlit depends on WebSocket support behind the reverse proxy. If the page loads partially, hangs, or behaves differently remotely than it does locally:
- check Dokploy domain and port mapping first
- inspect reverse proxy handling for WebSocket traffic
- try this start command to rule out WebSocket compression issues:

```bash
streamlit run app/frontend/streamlit_app.py --server.port 8501 --server.address 0.0.0.0 --server.enableWebsocketCompression=false
```

Browser CORS is usually not the issue here because the Streamlit app calls the backend through server-side `httpx`.

## Deployment Steps
### 1. Package the Lambda artifact
```powershell
python scripts/package_lambda.py
```

### 2. Prepare Terraform variables
Copy `infra/terraform/terraform.tfvars.example` to `infra/terraform/terraform.tfvars` and adjust the values.

Do not commit a real `llm_api_key` into Terraform files. Provide it through a local non-committed tfvars file or shell input such as `TF_VAR_llm_api_key`.

### 3. Initialize and validate Terraform
```powershell
terraform -chdir=infra/terraform init
terraform -chdir=infra/terraform fmt -check
terraform -chdir=infra/terraform validate
```

### 4. Plan and apply infrastructure
```powershell
terraform -chdir=infra/terraform plan
terraform -chdir=infra/terraform apply
```

### 5. Capture deployment outputs
```powershell
terraform -chdir=infra/terraform output -json
```

The deployed `api_url` is captured in `evidence/phase3/terraform-output.json` and can be exported to the frontend through `BACKEND_BASE_URL`.

## Verification Steps
Order verification DOB input must use `DD-MM-YYYY`.

### 1. Verify health endpoint
```powershell
curl <API_URL>/health
```

Expected response:
```json
{"status":"ok"}
```

### 2. Verify knowledge retrieval
```powershell
curl -X POST <API_URL>/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"session_id\":\"phase3-kb-001\",\"message\":\"What is the return policy?\"}"
```

Fallback is considered correct if the API returns a valid response and the answer clearly indicates that there is not enough grounded context instead of inventing unsupported information.

### 3. Verify order workflow
```powershell
curl -X POST <API_URL>/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"session_id\":\"phase3-order-001\",\"message\":\"Where is my order?\"}"
```

```powershell
curl -X POST <API_URL>/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"session_id\":\"phase3-order-001\",\"message\":\"My name is John Smith\"}"
```

```powershell
curl -X POST <API_URL>/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"session_id\":\"phase3-order-001\",\"message\":\"My date of birth is 15-01-1990\"}"
```

```powershell
curl -X POST <API_URL>/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"session_id\":\"phase3-order-001\",\"message\":\"Last 4 of my SSN is 1234\"}"
```

### 4. Verify DynamoDB persistence
- Confirm the session item exists with `pk=session_id` and `sk=SESSION`
- Confirm message items exist with `pk=session_id` and `sk=MESSAGE#...`
- Confirm `ttl` is written on both session and message records

### 5. Verify OpenSearch connectivity
If knowledge retrieval fails after deployment, verify all three of the following:
- the Lambda role permissions allow signed AOSS requests
- the AOSS data access policy trusts the Lambda role principal
- the deployed `OPENSEARCH_COLLECTION_ENDPOINT` value is correct

## Demo Flow
1. Show the deployment result and evidence index
2. Verify the deployed `/health` response
3. Show a grounded knowledge success response
4. Show a conservative fallback response for an out-of-context question
5. Walk through the order verification workflow with `DD-MM-YYYY` DOB input
6. Show DynamoDB persistence and CloudWatch log evidence

## Interview Talking Points
- why `Lambda + API Gateway + DynamoDB` was chosen for a fast, serverless deployment baseline
- why the project uses a single-table DynamoDB memory model with `SESSION` and `MESSAGE` items
- why the deployed fallback architecture was used instead of forcing Bedrock under quota and throttling pressure
- why conservative fallback behavior matters for non-hallucinated customer support answers
- what production hardening would be prioritized after assignment delivery

## CI/CD Model
- `CI`: runs `pytest`, `terraform fmt -check`, and `terraform validate`
- `CD support`: packages the Lambda artifact and can run `terraform plan`
- `Apply`: remains manual or gated to reduce accidental cloud changes during the assignment

## Deferred Items
- streaming responses
- frontend cloud hosting
- WAF
- multi-env
- Secrets Manager rotation
- full monitoring/alarming
- migration back to Bedrock target path

## Current Repo Layout
```text
app/
  backend/
    classifier.py
    handler.py
    knowledge_base.py
    llm_client.py
    main.py
    memory_store.py
    models.py
    orchestrator.py
    order_workflow.py
    search_client.py
    validators.py
  frontend/
    streamlit_app.py
data/
  mock/
    orders.json
  sample_docs/
docs/
  ai/
  architecture/
infra/
scripts/
  index_sample_docs.py
tests/
  test_knowledge_base.py
  test_llm_client.py
  test_orchestrator.py
  test_order_workflow.py
  test_search_retrieval.py
  test_smoke.py
  test_validators.py
```
