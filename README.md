# Agentic Commerce Assistant

Small-scale agentic conversational system for the Cloud Kinetics Data/AI Solution Architect Intern assignment.

## Goal
Build a submission-ready MVP that can:
- answer knowledge questions from internal documents via RAG
- handle an order status workflow with required user verification
- maintain multi-turn session context
- show a credible path to AWS deployment, observability, and IaC

## Chosen Architecture
- Frontend: `Streamlit`
- Local backend: `FastAPI`
- Cloud API entry: `Amazon API Gateway`
- Backend orchestration: `AWS Lambda`
- Documents: `Amazon S3`
- Retrieval: `Amazon OpenSearch Serverless` search collection with BM25/full-text search
- Grounded generation: `OpenAI-compatible API`
- Session memory: `DynamoDB`
- Observability: `CloudWatch Logs` and `CloudWatch Metrics`
- IaC: `Terraform`

## Retrieval And Generation Delta
The target retrieval architecture was originally Amazon Bedrock Knowledge Bases with S3/S3 Vectors. However, repeated ingestion attempts failed with Bedrock 429 throttling on embedding calls. To keep the solution AWS-native while unblocking retrieval, the current Phase 1 retrieval path uses Amazon OpenSearch Serverless search collections for document retrieval. Grounded generation was then moved from Amazon Bedrock Runtime to an OpenAI-compatible API because Bedrock invocation reliability and quota constraints blocked stable validation. This keeps the application contract stable, limits the architecture delta to the retrieval and generation layers, and preserves a clean path to return generation to Bedrock later.

## Current Scope
The repository has completed local Phase 1 core behavior and now includes an AWS retrieval path for knowledge questions.

Implemented now:
- FastAPI backend with `GET /health` and `POST /chat`
- stable request/response contract for chat orchestration
- Streamlit frontend wired to the backend
- multi-turn order workflow with required verification
- local session memory for Phase 1
- OpenSearch retrieval client and indexing script
- OpenAI-compatible generation integration path
- sample mock order data and sample knowledge docs
- automated tests

Not included yet:
- DynamoDB session persistence
- full observability coverage
- AWS deployment and IaC resources
- final live generation validation until a valid `LLM_API_KEY` is present in `.env`

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

## Roadmap
1. Phase 0: local scaffolding
2. Phase 1: core orchestration, rule-based classification, and workflow handling
3. Phase 2: RAG, session memory, and observability expansion
4. Phase 3: AWS deployment, IaC, and CI/CD
5. Phase 4: polish, demo, and submission packaging

## Local Setup

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
DOCS_S3_PREFIX=phase1-kb/
```

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
