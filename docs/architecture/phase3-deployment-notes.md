# Phase 3 Deployment Notes

## Deployment Scope
Phase 3 is a deployable, testable, interview-defensible AWS baseline for the assignment. It is not intended to be full production hardening.

## Adapter And Packaging Choices
- Lambda adapter: `Mangum`
- Packaging strategy: zip artifact created by `scripts/package_lambda.py`
- Lambda runtime baseline: `python3.12`, `512 MB`, `30 seconds`
- CloudWatch log group retention: `14 days`, managed explicitly in Terraform

## API Surface
Phase 3 exposes these public routes through API Gateway HTTP API:
- `GET /health`
- `POST /chat`
- `POST /chat/stream`

Streaming remains limited to knowledge responses. Order-status requests continue to use the non-streaming path so the verification workflow stays deterministic.

## S3 Strategy
The Terraform stack supports two document bucket modes:
- reuse an existing docs bucket
- create a docs bucket through Terraform

This keeps the deployment flexible without forcing a single infrastructure assumption.

## Known Architecture Delta
Target architecture:
- Amazon Bedrock Knowledge Bases
- Amazon S3
- S3 Vectors

Deployed fallback architecture:
- Amazon OpenSearch Serverless retrieval
- OpenAI-compatible grounded generation
- Amazon S3
- AWS Secrets Manager for LLM API key retrieval
- Orders DynamoDB table behind a dedicated order-status Lambda tool

## Runtime Hardening Additions
- the backend Lambda reads the external LLM API key from AWS Secrets Manager at runtime and caches it in process memory
- order lookup is externalized behind an `Order Status Tool Lambda` instead of reading local mock data from the deployment package
- CloudWatch metric alarms are provisioned for backend errors, order-tool errors, Lambda duration, and API Gateway 5XXs
- API Gateway detailed metrics are enabled
- Lambda tracing is configured through the shared `enable_xray` toggle

Reason for delta:
- repeated Bedrock throttling and quota blockers during execution
- unstable Bedrock runtime validation for the near-deadline MVP path

The fallback path preserves assignment functionality while keeping the cloud design explainable and interview-defensible.

## AOSS Connectivity Notes
OpenSearch Serverless is the highest-risk connectivity point in the deployed fallback path. Verify all three of the following if knowledge retrieval fails after deployment:
- the Lambda execution role has the required IAM permissions for signed AOSS requests
- the AOSS data access policy allows the Lambda role principal
- the Lambda environment points to the correct `OPENSEARCH_COLLECTION_ENDPOINT`
