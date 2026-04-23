# Agentic Commerce Assistant

Agentic Commerce Assistant is a small end-to-end support system that combines a retrieval-augmented generation pipeline for internal document Q&A with a guarded order-status workflow that requires user verification.

The repository is designed to demonstrate two distinct backend behaviors behind one chat API:

- grounded knowledge answers from an indexed document corpus
- a multi-turn order workflow that collects identity signals before returning order status

The current deployed cloud path uses `FastAPI + AWS Lambda + API Gateway + DynamoDB + OpenSearch Serverless + Secrets Manager + OpenAI-compatible generation`.

## Overview

This project has two primary capabilities:

- `Knowledge Q&A`: answer questions from an indexed internal document corpus and return supporting sources
- `Order Status`: collect verification details such as name, date of birth, and SSN last four before looking up an order

At a high level, a chat request enters the backend, gets classified by intent, and is then routed into either the RAG path or the order workflow path. Conversation state is persisted so multi-turn interactions can continue across requests.

## Core Capabilities

- grounded document answers with retrieved source citations
- conservative fallback when the retrieved context is insufficient
- multi-turn order verification workflow
- DynamoDB-backed session and message persistence
- externalized order lookup through a dedicated Lambda tool and Orders DynamoDB table
- optional streaming responses for knowledge queries
- Secrets Manager-backed LLM credential loading in cloud
- S3-backed document source bucket and dedicated ingestion Lambda for future auto-indexing
- CloudWatch alarms and X-Ray-ready tracing
- AWS deployment path managed with Terraform

## How The System Works

### Chat request flow

1. A client sends `session_id` and `message` to `POST /chat`.
2. The backend loads the session state and appends the user message.
3. The orchestrator classifies the message as either a knowledge question or an order-status request.
4. If it is a knowledge request, the backend runs retrieval, reranking, grounded answer generation, and source shaping.
5. If it is an order request, the backend runs the verification workflow and only returns order information after the required fields are collected.
6. The final assistant response and any retrieval references are written back to memory.

### Knowledge path

The knowledge path is centered on `app/backend/knowledge_base.py` and `app/backend/search_client.py`.

1. Retrieve candidate chunks from OpenSearch using lexical and embedding-based search.
2. Rerank the candidates according to query intent and SEC-style structure.
3. Limit the final chunk set to the most relevant evidence for the question.
4. Generate an answer only from the provided context.
5. Build a short, deduplicated source list for the response.

### Order workflow path

The order workflow is centered on `app/backend/order_workflow.py`.

1. Detect that the message is about order status.
2. Collect verification fields over multiple turns.
3. Validate the provided identity details.
4. Invoke a dedicated order-status tool Lambda after verification succeeds.
5. Read the verified order record from the Orders DynamoDB table.
6. Return a verified order response and persist the conversation state.

## RAG Pipeline

### Corpus

The current demonstration corpus is intentionally narrow. The main indexed filing is:

- `docs/company/Company-10k-18pages.pdf`

The retrieval pipeline is tuned for this SEC-style 10-K family rather than generic PDF ingestion.

### Indexing

The indexing entrypoint is:

- `scripts/index_sample_docs.py`

This script performs SEC-aware preprocessing and chunk creation. Important behaviors include:

- segmenting the filing by `PART` and `Item`
- removing table-of-contents style noise
- extracting structured financial rows for `Item 6`
- building chunk metadata such as `item`, `subsection`, `subsubsection`, `content_type`, `metric`, `year`, and entity fields
- replacing older chunks for the same `doc_id` during reindexing to avoid duplicates

### Chunk types

The parser produces several chunk styles to support different question types:

- `narrative`: longer explanatory text sections
- `fact`: shorter grounded factual statements
- `table_row`: row-level numeric data for table QA
- `table_block`: grouped table context for broader financial questions
- `profile_row`: structured executive/officer rows
- `profile_bio`: longer executive biography text

### Retrieval

Retrieval is implemented in `app/backend/search_client.py` and currently uses a hybrid strategy:

- lexical search over fields like `section`, `item`, `subsection`, `content`, `metric`, and `entity_name`
- embedding-based retrieval against OpenSearch vector fields
- intent-aware query expansion for question families such as:
  - business overview
  - facilities and properties
  - legal proceedings
  - executive lookup
  - numeric financial queries
  - exact risk heading lookup

### Answer grounding

Answer generation is implemented in `app/backend/knowledge_base.py`.

The backend does not treat all knowledge questions the same way. It applies intent-aware logic before generation, including:

- direct numeric answers for exact table-row matches
- stronger conservatism when the corpus only provides a cross-reference instead of a real explanation
- fallback behavior when the expected filing section is not actually present in the retrieved evidence
- source trimming and deduplication so the final source list stays short and relevant

This is important for the current corpus because some filing sections are only partially represented in the 18-page PDF.

## Architecture

### Application stack

- Frontend: `Streamlit`
- Backend API: `FastAPI`
- Backend adapter in cloud: `Mangum` on `AWS Lambda`
- API entry: `API Gateway HTTP API`
- Retrieval store: `OpenSearch Serverless`
- Generation: `OpenAI-compatible API`
- Session memory: `DynamoDB`
- Order lookup tool: `AWS Lambda`
- Order store: `DynamoDB`
- Secrets: `AWS Secrets Manager`
- Observability: `CloudWatch Logs`, `CloudWatch Alarms`, optional `X-Ray`
- Infrastructure: `Terraform`

## Repository Layout

```text
app/
  backend/
    classifier.py         Intent classification
    handler.py            Lambda entrypoint
    knowledge_base.py     Grounded answer generation and source shaping
    main.py               FastAPI application
    memory_store.py       Session persistence abstraction
    orchestrator.py       Main request routing logic
    order_lookup_client.py Lambda-invoked order tool client
    order_tool_handler.py Order tool Lambda handler
    ingestion_handler.py  S3-driven ingestion Lambda handler
    order_workflow.py     Verification-driven order flow
    search_client.py      OpenSearch retrieval and reranking
    secrets.py            Secrets Manager loader with in-process cache
  frontend/
    streamlit_app.py      Streamlit user interface
docs/                     Source documents and supporting docs
infra/
  terraform/              Cloud infrastructure definitions
scripts/
  bootstrap_opensearch_index.py OpenSearch index bootstrap helper
  debug_retrieval_response.py Retrieval debug helper
  index_sample_docs.py    Indexing pipeline for sample docs
  package_lambda.py       Lambda artifact packaging
tests/                    Unit and integration-oriented tests
evidence/                 Deployment and verification artifacts
```

## Quickstart

### 1. Create and activate a virtual environment

```powershell
python -m venv .venv
.venv\Scripts\activate
```

### 2. Install dependencies

```powershell
pip install -r requirements.txt
```

If you only need the Streamlit frontend dependencies separately, use:

```powershell
pip install -r requirements-frontend.txt
```

### 3. Configure environment variables

Copy `.env.example` to `.env` and set the values needed for your environment.

Runtime settings for local retrieval and API development:

```env
AWS_REGION=us-east-1
LLM_PROVIDER=openai_compatible
LLM_API_KEY=<external-llm-api-key>
LLM_BASE_URL=https://r2lj67q.9router.com/v1
LLM_MODEL=cx/gpt-5.4
LLM_TIMEOUT_SECONDS=30
OPENSEARCH_COLLECTION_ENDPOINT=<aoss-endpoint>
OPENSEARCH_INDEX_NAME=policy-faq-chunks
ORDER_TOOL_FUNCTION_NAME=<order-tool-lambda-name>
```

Optional S3 ingestion settings:

```env
DOCS_S3_BUCKET=<terraform-managed-docs-bucket>
DOCS_S3_PREFIX=phase1-kb/
INGESTION_STATE_TABLE_NAME=<terraform-managed-ingestion-state-table>
INGESTION_PROCESSING_TIMEOUT_SECONDS=900
```

The runtime answer path reads from OpenSearch, not directly from S3. The docs bucket is kept in the deployed stack so uploads of `.pdf`, `.md`, `.txt`, and `.docx` files can trigger the dedicated ingestion Lambda and refresh the index automatically.

For deployed AWS environments, the backend now reads the LLM API key from `LLM_API_KEY_SECRET_NAME` via Secrets Manager instead of storing the raw key in Lambda environment variables.

### 4. Run the backend

```powershell
uvicorn app.backend.main:app --reload
```

The main API endpoints are:

- `GET /health`
- `POST /chat`
- `POST /chat/stream`

### 5. Run the frontend

```powershell
streamlit run app/frontend/streamlit_app.py
```

### 6. Run the tests

```powershell
pytest
```

### 7. Index the sample document corpus

```powershell
.venv\Scripts\python.exe scripts/index_sample_docs.py
```

If your local indexing flow depends on a named AWS profile, set it before running the script.

Example:

```powershell
$env:AWS_PROFILE='minh-duykhanh'
.venv\Scripts\python.exe scripts/index_sample_docs.py
```

During deployment, Terraform also bootstraps the OpenSearch index mapping with `scripts/bootstrap_opensearch_index.py` so a fresh collection is ready before ingestion runs.

## Common Development Workflows

### Debug retrieval and answer generation

Use:

```powershell
.venv\Scripts\python.exe scripts/debug_retrieval_response.py
```

This script reflects the current OpenSearch retrieval and answer path. It prints:

- detected intent
- retrieved chunks
- provisional sources
- prompt messages
- direct answer from chunks
- final `answer_question()` output

You can override the debug question with:

```powershell
$env:DEBUG_QUESTION='Were there any legal proceedings?'
.venv\Scripts\python.exe scripts/debug_retrieval_response.py
```

### Run the benchmark set used during retrieval tuning

Use:

```powershell
$env:AWS_PROFILE='minh-duykhanh'
.venv\Scripts\python.exe scripts/run_round3_benchmark.py
```

This writes a capture file to:

- `artifacts/round3_benchmark.json`

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

## Deployment Overview

The backend is packaged as a Lambda artifact and deployed with Terraform. The deploy stack manages resources such as:

- Lambda for API, order tool, and document ingestion
- API Gateway
- DynamoDB for conversation memory, orders, and ingestion state
- OpenSearch Serverless
- S3 docs bucket, bucket notifications, and IAM resources needed by the deployed path
- Secrets Manager
- CloudWatch log groups and alarms

Use `docs/deployment.md` for the packaging, Terraform apply flow, post-deploy verification steps, reindexing, and troubleshooting notes.

## Current Limitations

- The main retrieval tuning is intentionally centered on a single SEC-style 10-K corpus.
- The parser is not a generic solution for arbitrary PDFs.
- The deployed path currently uses OpenSearch plus an OpenAI-compatible generation endpoint rather than Bedrock Knowledge Bases.
- The project demonstrates a credible cloud baseline, but it is not fully production hardened.

## Additional Notes

- Use `docs/deployment.md` for the deployment, verification, and reindexing runbook.
- Deployment and verification artifacts are stored under `evidence/`.
- Infrastructure definitions live under `infra/terraform/`.
- The backend is the primary system of record for the application flow; the Streamlit app is a thin UI over the API contract.
