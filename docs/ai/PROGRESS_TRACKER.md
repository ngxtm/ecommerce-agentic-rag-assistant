# Project Progress Tracker

## Purpose
This file is the **single source of truth for execution progress**.
Any AI assistant or engineer continuing this project should read files in this order:
1. `AI_Handoff_Context_Pack.md`
2. `ai_handoff_context.json`
3. `PROGRESS_TRACKER.md`
4. current codebase / repo state

Then they should continue **only unfinished tasks** and avoid redesigning the approved architecture unless explicitly instructed.

---

## Current Status
- Current phase: **Phase 1 - Level 100 Core Features**
- Current focus: **Phase 1 AWS retrieval plus external generation implementation is in place for OpenSearch retrieval, OpenAI-compatible generation, multi-turn order workflow, local session memory, and test coverage**
- Last updated: **2026-04-18 (Asia/Ho_Chi_Minh)**
- Overall state: **OpenSearch retrieval is running against AWS and the generation layer has been switched to an OpenAI-compatible API, while final live grounded generation validation is currently blocked only by a missing local `LLM_API_KEY` value in `.env`**

---

## Approved Baseline
The following are already approved and should be treated as fixed unless the user explicitly changes direction:
- Use **Amazon S3** for document storage
- Use **Amazon OpenSearch Serverless** search collections for Phase 1 retrieval because Bedrock Knowledge Bases ingestion is blocked by repeated 429 throttling
- Use an **OpenAI-compatible API** for grounded answer generation because Bedrock invocation reliability and quota constraints blocked stable validation
- Use **AWS Lambda** for orchestration and mock order status tool
- Use **API Gateway** as API entry point
- Use **DynamoDB** for session memory / conversation data
- Use **CloudWatch** for observability
- Use **Terraform or AWS CDK** for IaC
- Keep the UI **simple** (Streamlit preferred)
- Prioritize **working demo first**, then deployment/polish

---

## Overall Progress
- [x] Architecture direction finalized
- [x] Technical design document created
- [x] AI handoff context pack created
- [x] Structured implementation plan created
- [x] Repo implementation started
- [ ] Level 100 core features completed
- [ ] Level 300 minimum viable features completed
- [ ] Level 200 minimum viable deployment completed
- [ ] Demo recording completed
- [ ] Final submission packaged

---

## Phase Breakdown

### Phase 0 - Project Setup
**Status:** In progress

Tasks:
- [x] Create repository structure
- [x] Add README skeleton
- [x] Create frontend skeleton
- [x] Create backend skeleton
- [x] Add environment variable template
- [x] Choose AWS region
- [ ] Confirm Bedrock access / credentials

Exit criteria:
- [x] Local project skeleton exists
- [ ] Repo can be pushed to GitHub
- [x] Frontend and backend placeholders run locally

---

### Phase 1 - Level 100 Core Features
**Status:** In progress

#### 1. Chat UI
- [x] Create Streamlit chat interface
- [x] Render chat history
- [x] Connect UI to backend endpoint

#### 2. Backend Orchestrator
- [x] Create `/chat` API contract
- [x] Add request/response models
- [x] Implement top-level orchestration flow

#### 3. Request Classification
- [x] Implement rule-based classifier
- [x] Route `ORDER_STATUS` requests correctly
- [x] Route `KNOWLEDGE_QA` requests correctly

#### 4. Knowledge Retrieval And Generation
- [x] Create S3 document bucket
- [x] Upload sample/internal documents
- [ ] Create Bedrock Knowledge Base
- [ ] Connect S3 data source
- [ ] Trigger ingestion/sync
- [x] Implement backend query call through the OpenSearch + external generation replacement path
- [x] Return grounded answer

#### 4b. AWS Retrieval Replacement Path
- [x] Create OpenSearch Serverless search collection access path
- [x] Add sample document indexing script
- [x] Index sample documents into OpenSearch
- [x] Retrieve top chunks through BM25/full-text search
- [ ] Validate live OpenAI-compatible generation end-to-end once a valid `LLM_API_KEY` is present in `.env`

#### 5. Order Status Workflow
- [x] Define workflow state model
- [x] Collect full name
- [x] Collect DOB
- [x] Collect SSN last 4
- [x] Validate all required fields
- [x] Call mock order status tool only after validation
- [x] Return shipment result

#### 6. Session Memory
- [x] Persist session state
- [x] Persist collected verification fields
- [x] Persist chat messages
- [x] Load previous state during next turn

Exit criteria:
- [x] User can ask document questions through the AWS retrieval path and get grounded chunks from OpenSearch
- [x] User can ask for order status and complete verification in multiple turns
- [x] Missing/invalid input is handled correctly
- [ ] Live external generation is validated end-to-end with a valid `LLM_API_KEY`

---

### Phase 2 - Level 300 Minimum Viable Coverage
**Status:** Not started

#### 1. Conversation Data Model
- [ ] Implement `ConversationSession` table
- [ ] Implement `ConversationMessage` table
- [ ] Add TTL strategy

#### 2. Runtime Integration
- [ ] Load session before orchestration
- [ ] Update session after each turn
- [ ] Store assistant and user messages
- [ ] Store tool execution summary

#### 3. Observability
- [ ] Add structured application logs
- [ ] Mask PII in logs
- [ ] Add latency logging
- [ ] Add intent distribution metrics
- [ ] Add workflow success/failure logging
- [ ] Add KB success/failure logging

Exit criteria:
- Memory is integrated into runtime
- Observability is visible and explainable in demo/interview

---

### Phase 3 - Level 200 Minimum Viable Deployment
**Status:** Not started

#### 1. IaC
- [ ] Create IaC skeleton
- [ ] Define Lambda resources
- [ ] Define API Gateway resources
- [ ] Define DynamoDB resources
- [ ] Define S3 resources

#### 2. Deployment
- [ ] Deploy backend to AWS
- [ ] Verify live API endpoint
- [ ] Connect frontend to cloud backend

#### 3. CI/CD
- [ ] Add GitHub Actions workflow
- [ ] Add lint/test step
- [ ] Add package/deploy step if feasible

#### 4. Optional UX Improvement
- [ ] Add streaming response if time permits

Exit criteria:
- At least backend is deployed in AWS
- IaC exists in usable form
- Basic CI/CD exists or is clearly documented

---

### Phase 4 - Polish and Submission Prep
**Status:** Not started

Tasks:
- [ ] Finalize README
- [ ] Add architecture images/screenshots
- [ ] Add setup/run instructions
- [ ] Record demo
- [ ] Validate links and documents
- [ ] Package final submission

Exit criteria:
- Submission artifacts are ready to hand over

---

## Current Blockers / Unknowns
- OpenSearch retrieval is working and the OpenAI-compatible generation path is implemented, but `.env` intentionally has a blank `LLM_API_KEY`, so live generation still falls back conservatively
- GitHub repository path is not yet recorded in this tracker

## Implementation Evidence
- Phase 0 repository skeleton created under the project root
- Backend files added: `app/backend/main.py`, `handler.py`, `models.py`, `orchestrator.py`
- Backend Phase 1 files added: `classifier.py`, `validators.py`, `memory_store.py`, `order_workflow.py`, `knowledge_base.py`
- Backend AWS retrieval files added: `search_client.py`
- Backend external generation file added: `llm_client.py`
- Frontend file added: `app/frontend/streamlit_app.py`
- Config and dependency files added: `.env.example`, `.gitignore`, `requirements.txt`
- Test file added: `tests/test_smoke.py`
- Sample data added: `data/mock/orders.json`
- Sample knowledge documents added under `data/sample_docs/`
- Sample docs indexed into OpenSearch index `policy-faq-chunks` with 51 chunks
- Documentation added: `README.md`
- Default AWS region recorded in `.env.example` as `us-east-1`
- `pytest` executed successfully with 2 passing smoke tests
- `pytest` executed successfully with 15 passing tests covering classifier, validators, order workflow, orchestrator, and smoke paths
- `pytest` executed successfully with 21 passing tests covering classifier, validators, order workflow, orchestrator, OpenSearch retrieval, knowledge-base fallbacks, and smoke paths
- `pytest` executed successfully with 24 passing tests covering classifier, validators, order workflow, orchestrator, OpenSearch retrieval, OpenAI-compatible generation, knowledge-base fallbacks, and smoke paths
- Python package markers added: `app/__init__.py`, `app/backend/__init__.py`, `app/frontend/__init__.py`
- `pytest.ini` added to pin `pythonpath = .` and `asyncio_default_fixture_loop_scope = function`
- Direct local `pytest` import error for `ModuleNotFoundError: No module named 'app'` has been resolved
- Local multi-turn order flow was manually verified through the orchestrator using `full_name`, `date_of_birth` in `DD-MM-YYYY`, and `ssn_last4`
- Local knowledge path was manually verified to return a conservative grounded answer with source references from sample docs
- Live OpenSearch retrieval was manually verified to return relevant chunks from AWS for knowledge questions
- Live OpenSearch retrieval was re-verified after the provider switch and still returns the correct chunks for knowledge questions
- The OpenAI-compatible generation code path falls back conservatively until `LLM_API_KEY` is populated in `.env`

---

## Next 3 Tasks
1. Add a valid `LLM_API_KEY` to `.env`, then rerun live in-context and out-of-context knowledge validation
2. Manually run local backend and Streamlit UI together to capture browser-visible end-to-end evidence for the AWS retrieval plus external generation path
3. Start Phase 2 runtime memory and observability work with a DynamoDB-backed session store and structured logging

---

## Update Rules
Whenever work is completed, update all of the following:
1. `Current Status`
2. task checkboxes in the relevant phase
3. `Current Blockers / Unknowns`
4. `Next 3 Tasks`
5. `progress_state.json`

Do not mark a phase complete unless its exit criteria are actually met.

---

## Instruction for Any Future AI Assistant
- Do not redesign the architecture unless the user explicitly asks
- Do not replace the current OpenSearch retrieval path unless there is a real blocker
- Keep external generation isolated to the smallest possible boundary in `knowledge_base.py` / `llm_client.py`
- Prioritize demo-complete core functionality over optional enhancements
- Always update `PROGRESS_TRACKER.md` and `progress_state.json` after meaningful progress
