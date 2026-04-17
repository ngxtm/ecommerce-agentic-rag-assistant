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
- Current phase: **Phase 0 - Project Setup**
- Current focus: **Local scaffolding is stable, and pytest import-path compatibility has been fixed for direct local execution**
- Last updated: **2026-04-17 (Asia/Ho_Chi_Minh)**
- Overall state: **Phase 0 implementation is in place, smoke tests pass, and the local test runner configuration is stabilized**

---

## Approved Baseline
The following are already approved and should be treated as fixed unless the user explicitly changes direction:
- Use **Amazon Bedrock Knowledge Bases** for managed RAG
- Use **Amazon S3** for document storage
- Use **S3 Vectors** as the vector store
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
**Status:** Not started

#### 1. Chat UI
- [ ] Create Streamlit chat interface
- [ ] Render chat history
- [ ] Connect UI to backend endpoint

#### 2. Backend Orchestrator
- [ ] Create `/chat` API contract
- [ ] Add request/response models
- [ ] Implement top-level orchestration flow

#### 3. Request Classification
- [ ] Implement rule-based classifier
- [ ] Route `ORDER_STATUS` requests correctly
- [ ] Route `KNOWLEDGE_QA` requests correctly

#### 4. Bedrock Knowledge Base Integration
- [ ] Create S3 document bucket
- [ ] Upload sample/internal documents
- [ ] Create Bedrock Knowledge Base
- [ ] Connect S3 data source
- [ ] Trigger ingestion/sync
- [ ] Implement backend query call
- [ ] Return grounded answer

#### 5. Order Status Workflow
- [ ] Define workflow state model
- [ ] Collect full name
- [ ] Collect DOB
- [ ] Collect SSN last 4
- [ ] Validate all required fields
- [ ] Call mock order status tool only after validation
- [ ] Return shipment result

#### 6. Session Memory
- [ ] Persist session state
- [ ] Persist collected verification fields
- [ ] Persist chat messages
- [ ] Load previous state during next turn

Exit criteria:
- User can ask document questions and get grounded answers
- User can ask for order status and complete verification in multiple turns
- Missing/invalid input is handled correctly

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
- AWS credentials and Bedrock access are not yet confirmed in this tracker
- GitHub repository path is not yet recorded in this tracker

## Implementation Evidence
- Phase 0 repository skeleton created under the project root
- Backend files added: `app/backend/main.py`, `handler.py`, `models.py`, `orchestrator.py`
- Frontend file added: `app/frontend/streamlit_app.py`
- Config and dependency files added: `.env.example`, `.gitignore`, `requirements.txt`
- Test file added: `tests/test_smoke.py`
- Sample data added: `data/mock/orders.json`
- Documentation added: `README.md`
- Default AWS region recorded in `.env.example` as `us-east-1`
- `pytest` executed successfully with 2 passing smoke tests
- Python package markers added: `app/__init__.py`, `app/backend/__init__.py`, `app/frontend/__init__.py`
- `pytest.ini` added to pin `pythonpath = .` and `asyncio_default_fixture_loop_scope = function`
- Direct local `pytest` import error for `ModuleNotFoundError: No module named 'app'` has been resolved

---

## Next 3 Tasks
1. Manually run local backend and Streamlit UI together to capture end-to-end placeholder evidence
2. Implement Phase 1 rule-based classifier and expand orchestrator routing behavior
3. Prepare sample documents and Bedrock Knowledge Base integration scaffolding

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
- Do not replace Bedrock Knowledge Bases with custom RAG for the MVP
- Do not switch to OpenSearch Serverless unless there is a real blocker
- Prioritize demo-complete core functionality over optional enhancements
- Always update `PROGRESS_TRACKER.md` and `progress_state.json` after meaningful progress
