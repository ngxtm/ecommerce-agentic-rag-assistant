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
- RAG: `Amazon Bedrock Knowledge Bases`
- Documents: `Amazon S3`
- Vector store: `S3 Vectors`
- Session memory: `DynamoDB`
- Observability: `CloudWatch Logs` and `CloudWatch Metrics`
- IaC: `Terraform`

## Phase 0 Scope
Phase 0 establishes the local development skeleton before real integrations are added.

Included in this phase:
- FastAPI backend with `GET /health` and `POST /chat`
- stable request/response contract for chat orchestration
- local logging stub with request metadata and latency
- Streamlit frontend wired to the backend
- sample mock order data
- smoke tests

Not included yet:
- Bedrock Knowledge Base integration
- DynamoDB session persistence
- AWS deployment
- IaC resources

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

## Current Repo Layout
```text
app/
  backend/
    handler.py
    main.py
    models.py
    orchestrator.py
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
tests/
  test_smoke.py
```
