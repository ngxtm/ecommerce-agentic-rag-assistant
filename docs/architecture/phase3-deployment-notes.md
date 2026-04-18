# Phase 3 Deployment Notes

## Deployment Scope
Phase 3 is a deployable, testable, interview-defensible AWS baseline for the assignment. It is not intended to be full production hardening.

## Adapter And Packaging Choices
- Lambda adapter: `Mangum`
- Packaging strategy: zip artifact created by `scripts/package_lambda.py`
- Lambda runtime baseline: `python3.12`, `512 MB`, `30 seconds`
- CloudWatch log group retention: `14 days`, managed explicitly in Terraform

## API Surface
Phase 3 exposes only these public routes through API Gateway HTTP API:
- `GET /health`
- `POST /chat`

This keeps the deployment contract minimal and easier to defend in review.

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

Reason for delta:
- repeated Bedrock throttling and quota blockers during execution
- unstable Bedrock runtime validation for the near-deadline MVP path

The fallback path preserves assignment functionality while keeping the cloud design explainable and interview-defensible.

## AOSS Connectivity Notes
OpenSearch Serverless is the highest-risk connectivity point in the deployed fallback path. Verify all three of the following if knowledge retrieval fails after deployment:
- the Lambda execution role has the required IAM permissions for signed AOSS requests
- the AOSS data access policy allows the Lambda role principal
- the Lambda environment points to the correct `OPENSEARCH_COLLECTION_ENDPOINT`
