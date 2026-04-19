# AI Handoff Context Pack

## Objective
Build and submit a **small-scale Agentic Conversational System** for the **Cloud Kinetics Data/AI Solution Architect Intern assignment**.

This handoff document is intended for another AI assistant or engineer so they can continue the work **without losing context** and **without changing the agreed direction**.

---

## What the assignment requires
The solution must support:

1. **Knowledge-based question answering** using internal documents via **RAG**.
2. **Order shipment status workflow** with mandatory user verification before tool execution.
3. **Multi-turn conversation handling** with session-level memory.
4. **Cloud deployment on AWS (preferred)** with **IaC preferred**.
5. **Streaming responses recommended**.
6. **Simple CI/CD recommended**.
7. **Level 300 design coverage** for conversation data model, memory integration, and observability.
8. Optional additions: request classification pipeline and data preprocessing pipeline.

### Mandatory verification fields for order status
Before order lookup, the system must collect and validate:
- Full name
- Last 4 digits of SSN
- Date of birth

### What matters most for scoring
The assignment evaluates three dimensions:
- Solution Architecture
- Engineering / Delivery
- Data & AI understanding

The assignment explicitly allows partial completion if time is limited, and it values **good design decisions and rationale** over implementing every advanced feature.

---

## Deadline reality and guiding principle
The user has a **near deadline** and explicitly wants a solution optimized for:
- **speed of implementation**
- **low cloud cost**
- **clean architecture that can be defended in interview**

Therefore, the chosen direction is:
- use **managed AWS services where possible**
- prioritize **Level 100 first**
- add **Level 300 minimum viable coverage** next
- add **Level 200 minimum viable deployment** after core functionality works
- avoid overbuilding optional features unless time remains

---

## Final architecture direction that has already been agreed
Do **not** redesign from scratch unless absolutely necessary.

### Chosen architecture
- **Frontend:** Streamlit chat UI
- **Entry point:** Amazon API Gateway
- **Backend orchestration:** AWS Lambda
- **Target RAG layer:** Amazon Bedrock Knowledge Bases
- **Deployed fallback retrieval:** Amazon OpenSearch Serverless
- **Deployed fallback generation:** OpenAI-compatible API
- **Document source:** Amazon S3
- **Target vector store:** **S3 Vectors**
- **Workflow tool:** AWS Lambda mock order status service
- **Session memory / conversation data:** DynamoDB
- **Observability:** CloudWatch Logs, CloudWatch Metrics, optional X-Ray
- **Infrastructure as Code:** Terraform or AWS CDK
- **CI/CD:** simple GitHub Actions pipeline

### Why this architecture was chosen
1. **Fastest path to a credible submission**
2. **Lower cost than standing up heavier infra**
3. **Managed RAG reduces implementation burden**
4. Still demonstrates architecture thinking, security thinking, and production-readiness mindset

---

## Important architecture decisions and non-goals

### Target path vs deployed fallback
The original target was **Amazon Bedrock Knowledge Bases** with **S3 Vectors** to keep the RAG stack managed.

For the submitted deployment, the system uses the already-validated fallback path instead:
- **Amazon OpenSearch Serverless** for retrieval
- **OpenAI-compatible generation** for grounded answering
- **Amazon S3** for document storage

This fallback was chosen because repeated Bedrock throttling and quota blockers made the target path unreliable for near-deadline validation.

Do not redesign around Bedrock again during submission polish unless the user explicitly asks.

Keep the narrative clear:
- target architecture remains useful for architecture discussion
- deployed fallback architecture is the path that was actually implemented, verified, and evidenced in the repo

Do not replace the deployed OpenSearch path during Phase 4.

Do not attempt to migrate back to Bedrock during submission polish.

Do not overbuild UI
The frontend should be simple, functional, and demo-friendly.
No fancy UI work unless core requirements are already complete.

### Avoid optional deep preprocessing unless time remains
A data preprocessing pipeline can be described, but does not need to be fully implemented unless there is extra time.

---

## Functional scope to implement

### 1. Knowledge QA / RAG
The chatbot must:
- answer user questions based on provided internal documents
- use retrieval to provide context to the model
- minimize hallucinations
- respond conservatively when context is insufficient

### 2. Order status workflow
The chatbot must:
- detect order/shipment intent
- ask follow-up questions if verification data is missing
- validate fields
- call a mock tool / mock API after verification is complete
- return order shipment status

### 3. Multi-turn conversation
The chatbot must:
- maintain session context
- remember verification progress inside the same session
- store and retrieve recent conversation state

---

## Validation rules for order workflow
Use pragmatic validation only.

### Full name
- required
- must not be empty
- can enforce at least two tokens for realism, but keep it simple

### SSN last 4
- exactly 4 digits
- reject otherwise

### Date of birth
- accept a valid date format
- use `DD-MM-YYYY` for the verified submission and demo flow

### Verification flow behavior
- if any field is missing -> ask for the missing field(s)
- if a field is invalid -> explain the expected format and ask again
- only call the order tool after all required fields are present and valid

---

## Request classification approach
Use a **simple rule-based classifier first**.
Do not spend time implementing a complex LLM-based classifier unless later needed.

### Suggested intent categories
- `KNOWLEDGE_QA`
- `ORDER_STATUS`
- `FALLBACK`

### Example heuristics
If the message contains phrases like:
- `order`
- `shipment`
- `shipping status`
- `track`
- `where is my package`

then route to `ORDER_STATUS`.
Otherwise default to `KNOWLEDGE_QA`.

---

## Session memory and data model
This design is intended to cover the required Level 300 areas without overcomplicating implementation.

### DynamoDB table 1: ConversationSession
Suggested fields:
- `session_id` (PK)
- `created_at`
- `updated_at`
- `current_intent`
- `verification_state`
- `collected_full_name`
- `collected_dob`
- `collected_ssn_last4`
- `verified_customer_ref` (optional)
- `ttl`

### DynamoDB table 2: ConversationMessage
Suggested fields:
- `session_id` (PK)
- `message_ts` (SK)
- `role`
- `message_text`
- `tool_name`
- `tool_result_summary`
- `retrieval_refs`
- `contains_pii`
- `ttl`

### Runtime behavior
On each request:
1. load session state
2. determine intent
3. execute KB query or order workflow
4. update session state
5. persist user and assistant messages

---

## Observability requirements
This should visibly cover Level 300 thinking.

### Log / metric categories
Capture at least:
- total requests
- intent distribution
- RAG query success/failure
- retrieval latency
- order workflow success/failure
- verification failures
- fallback responses
- end-to-end response latency

### Security logging rules
- never log raw SSN
- avoid logging raw DOB if possible
- mask or redact sensitive values
- log only what is needed for debugging/demo purposes

---

## Security and best-practice expectations
The user wants the solution to reflect a real Solution Architect mindset, not just a demo.

### Minimum security posture
- least-privilege IAM
- encrypt data at rest where applicable
- separate document data from customer/order mock data
- do not log sensitive verification data in plaintext
- use TTL to expire temporary conversation/session records

### Important note
This is still a demo/MVP, so the solution does **not** need full enterprise security implementation. However, the design and documentation must show awareness of these concerns.

---

## Cost optimization decisions
These decisions are already agreed and should remain consistent.

### Cost priorities
- minimize always-on infrastructure
- prefer pay-per-use services
- keep the system easy to tear down after demo

### Cost-aware choices
- prefer **Lambda** over always-on compute for backend
- use the already-validated **OpenSearch Serverless + OpenAI-compatible** fallback for the submitted deployment
- use **DynamoDB** for serverless session memory
- deploy only what is needed
- destroy or stop nonessential resources after the demo

### Practical trade-off statement
This architecture intentionally prioritizes **time-to-delivery and cost efficiency** over maximum customization.
That is acceptable and appropriate for this assignment.

---

## Implementation order that must be followed
Do **not** start from IaC, CI/CD, or UI polish.
The correct order is:

### Phase 0 - Project skeleton
- repo structure
- local app setup
- backend entrypoint
- frontend stub
- README scaffold

### Phase 1 - Level 100 core
- chat UI working end-to-end
- backend orchestrator
- request classifier
- implemented retrieval/generation path
- order status workflow
- validation logic
- mock order lookup tool
- session-level memory

### Phase 2 - Level 300 minimum viable coverage
- DynamoDB conversation/session tables
- state persistence and retrieval
- structured logs / metrics
- observability notes and evidence

### Phase 3 - Level 200 minimum viable deployment
- deploy backend to AWS
- IaC for core infra
- optional frontend cloud deployment
- simple GitHub Actions pipeline

### Phase 4 - Polish
- better prompts
- error handling
- screenshots
- demo recording
- repo cleanup

---

## Definition of done for submission
The submission is acceptable when all of the following are true:

1. The chatbot can answer at least several questions from the provided documents via RAG.
2. The chatbot can detect order status intent.
3. It collects missing verification fields through follow-up questions.
4. It validates SSN last 4 and DOB.
5. It only calls the order lookup tool after successful validation.
6. It returns a mock shipment status.
7. It maintains session context in multi-turn conversation.
8. There is a deployable AWS backend.
9. The repo contains clear documentation.
10. The design can be explained confidently in interview.

---

## Files and modules expected in the implementation repo
Suggested structure:

```text
agentic-commerce-assignment/
  docs/
    architecture/
  app/
    frontend/
      streamlit_app.py
    backend/
      handler.py
      orchestrator.py
      classifier.py
      knowledge_base.py
      order_workflow.py
      validators.py
      memory_store.py
      models.py
  infra/
  data/
    mock/
      orders.json
    sample_docs/
  tests/
    test_classifier.py
    test_validators.py
    test_order_workflow.py
  README.md
```

---

## Mock order data guidance
A small mock dataset is sufficient.
Example fields:
- customer_id
- full_name
- dob
- ssn_last4
- order_id
- shipment_status
- carrier
- estimated_delivery

Do not spend time building a real external integration.

---

## Demo guidance
If a demo recording is created, it should show this sequence:
1. brief architecture overview
2. knowledge Q&A example
3. order status request with missing info
4. validation error example
5. successful verification
6. shipment status response
7. short note on DynamoDB memory + CloudWatch + IaC

---

## What not to do
Do not:
- replace the architecture with a completely different stack
- build a complicated multi-agent system
- overinvest in UI design
- spend large effort on optional preprocessing implementation
- replace the deployed OpenSearch fallback path during submission polish
- attempt real production authentication flows for this submission

### Keep the workflow simple and controlled
The order status flow is **not** a general agent tool-calling playground.
It is a **controlled workflow** with validation and deterministic steps.

### Do not overbuild UI
The frontend should be simple, functional, and demo-friendly.
No fancy UI work unless core requirements are already complete.

### Avoid optional deep preprocessing unless time remains
A data preprocessing pipeline can be described, but does not need to be fully implemented unless there is extra time.

---

## Functional scope to implement

### 1. Knowledge QA / RAG
The chatbot must:
- answer user questions based on provided internal documents
- use retrieval to provide context to the model
- minimize hallucinations
- respond conservatively when context is insufficient

### 2. Order status workflow
The chatbot must:
- detect order/shipment intent
- ask follow-up questions if verification data is missing
- validate fields
- call a mock tool / mock API after verification is complete
- return order shipment status

### 3. Multi-turn conversation
The chatbot must:
- maintain session context
- remember verification progress inside the same session
- store and retrieve recent conversation state

---

## Validation rules for order workflow
Use pragmatic validation only.

### Full name
- required
- must not be empty
- can enforce at least two tokens for realism, but keep it simple

### SSN last 4
- exactly 4 digits
- reject otherwise

### Date of birth
- accept a valid date format
- use a single expected format if needed for simplicity, e.g. `YYYY-MM-DD`

### Verification flow behavior
- if any field is missing -> ask for the missing field(s)
- if a field is invalid -> explain the expected format and ask again
- only call the order tool after all required fields are present and valid

---

## Request classification approach
Use a **simple rule-based classifier first**.
Do not spend time implementing a complex LLM-based classifier unless later needed.

### Suggested intent categories
- `KNOWLEDGE_QA`
- `ORDER_STATUS`
- `FALLBACK`

### Example heuristics
If the message contains phrases like:
- `order`
- `shipment`
- `shipping status`
- `track`
- `where is my package`

then route to `ORDER_STATUS`.
Otherwise default to `KNOWLEDGE_QA`.

---

## Session memory and data model
This design is intended to cover the required Level 300 areas without overcomplicating implementation.

### DynamoDB table 1: ConversationSession
Suggested fields:
- `session_id` (PK)
- `created_at`
- `updated_at`
- `current_intent`
- `verification_state`
- `collected_full_name`
- `collected_dob`
- `collected_ssn_last4`
- `verified_customer_ref` (optional)
- `ttl`

### DynamoDB table 2: ConversationMessage
Suggested fields:
- `session_id` (PK)
- `message_ts` (SK)
- `role`
- `message_text`
- `tool_name`
- `tool_result_summary`
- `retrieval_refs`
- `contains_pii`
- `ttl`

### Runtime behavior
On each request:
1. load session state
2. determine intent
3. execute KB query or order workflow
4. update session state
5. persist user and assistant messages

---

## Observability requirements
This should visibly cover Level 300 thinking.

### Log / metric categories
Capture at least:
- total requests
- intent distribution
- RAG query success/failure
- retrieval latency
- order workflow success/failure
- verification failures
- fallback responses
- end-to-end response latency

### Security logging rules
- never log raw SSN
- avoid logging raw DOB if possible
- mask or redact sensitive values
- log only what is needed for debugging/demo purposes

---

## Security and best-practice expectations
The user wants the solution to reflect a real Solution Architect mindset, not just a demo.

### Minimum security posture
- least-privilege IAM
- encrypt data at rest where applicable
- separate document data from customer/order mock data
- do not log sensitive verification data in plaintext
- use TTL to expire temporary conversation/session records

### Important note
This is still a demo/MVP, so the solution does **not** need full enterprise security implementation. However, the design and documentation must show awareness of these concerns.

---

## Cost optimization decisions
These decisions are already agreed and should remain consistent.

### Cost priorities
- minimize always-on infrastructure
- prefer pay-per-use services
- keep the system easy to tear down after demo

### Cost-aware choices
- prefer **Lambda** over always-on compute for backend
- prefer **Bedrock Knowledge Bases** over a custom self-managed RAG stack
- prefer **S3 Vectors** over heavier vector-search infrastructure for MVP
- use **DynamoDB** for serverless session memory
- deploy only what is needed
- destroy or stop nonessential resources after the demo

### Practical trade-off statement
This architecture intentionally prioritizes **time-to-delivery and cost efficiency** over maximum customization.
That is acceptable and appropriate for this assignment.

---

## Implementation order that must be followed
Do **not** start from IaC, CI/CD, or UI polish.
The correct order is:

### Phase 0 - Project skeleton
- repo structure
- local app setup
- backend entrypoint
- frontend stub
- README scaffold

### Phase 1 - Level 100 core
- chat UI working end-to-end
- backend orchestrator
- request classifier
- Bedrock Knowledge Base integration
- order status workflow
- validation logic
- mock order lookup tool
- session-level memory

### Phase 2 - Level 300 minimum viable coverage
- DynamoDB conversation/session tables
- state persistence and retrieval
- structured logs / metrics
- observability notes and evidence

### Phase 3 - Level 200 minimum viable deployment
- deploy backend to AWS
- IaC for core infra
- optional frontend cloud deployment
- simple GitHub Actions pipeline

### Phase 4 - Polish
- better prompts
- error handling
- screenshots
- demo recording
- repo cleanup

---

## Definition of done for submission
The submission is acceptable when all of the following are true:

1. The chatbot can answer at least several questions from the provided documents via RAG.
2. The chatbot can detect order status intent.
3. It collects missing verification fields through follow-up questions.
4. It validates SSN last 4 and DOB.
5. It only calls the order lookup tool after successful validation.
6. It returns a mock shipment status.
7. It maintains session context in multi-turn conversation.
8. There is a deployable AWS backend.
9. The repo contains clear documentation.
10. The design can be explained confidently in interview.

---

## Files and modules expected in the implementation repo
Suggested structure:

```text
agentic-commerce-assignment/
  docs/
    architecture/
  app/
    frontend/
      streamlit_app.py
    backend/
      handler.py
      orchestrator.py
      classifier.py
      knowledge_base.py
      order_workflow.py
      validators.py
      memory_store.py
      models.py
  infra/
  data/
    mock/
      orders.json
    sample_docs/
  tests/
    test_classifier.py
    test_validators.py
    test_order_workflow.py
  README.md
```

---

## Mock order data guidance
A small mock dataset is sufficient.
Example fields:
- customer_id
- full_name
- dob
- ssn_last4
- order_id
- shipment_status
- carrier
- estimated_delivery

Do not spend time building a real external integration.

---

## Demo guidance
If a demo recording is created, it should show this sequence:
1. brief architecture overview
2. knowledge Q&A example
3. order status request with missing info
4. validation error example
5. successful verification
6. shipment status response
7. short note on DynamoDB memory + CloudWatch + IaC

---

## What not to do
Do not:
- replace the architecture with a completely different stack
- build a complicated multi-agent system
- overinvest in UI design
- spend large effort on optional preprocessing implementation
- add OpenSearch Serverless unless really needed
- attempt real production authentication flows for this submission

---

## Final instruction to the next AI / engineer
Your job is to continue implementation **within the agreed architecture and priorities**.

You should:
- preserve the existing architectural direction
- optimize for fast completion and submission quality
- prioritize Level 100 first
- add minimum credible Level 300 coverage
- add minimum viable Level 200 deployment
- avoid scope creep
- produce code, repo structure, and documentation that support a strong interview discussion

