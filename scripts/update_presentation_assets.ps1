Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.IO.Compression.FileSystem

function Save-Utf8NoBom {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path,
        [Parameter(Mandatory = $true)]
        [string] $Content
    )

    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $encoding)
}

function Replace-OpenXmlTextValues {
    param(
        [Parameter(Mandatory = $true)]
        [string] $XmlPath,
        [Parameter(Mandatory = $true)]
        [hashtable] $Replacements
    )

    [xml] $xml = Get-Content -LiteralPath $XmlPath -Raw
    $changed = $false

    foreach ($node in $xml.SelectNodes("//*[local-name()='t']")) {
        $current = [string] $node.InnerText
        if ($Replacements.ContainsKey($current)) {
            $node.InnerText = [string] $Replacements[$current]
            $changed = $true
        }
    }

    if ($changed) {
        Save-Utf8NoBom -Path $XmlPath -Content $xml.OuterXml
    }
}

function Update-OfficePackage {
    param(
        [Parameter(Mandatory = $true)]
        [string] $PackagePath,
        [Parameter(Mandatory = $true)]
        [scriptblock] $Mutator
    )

    $resolvedPackage = (Resolve-Path -LiteralPath $PackagePath).Path
    $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("office-edit-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tempRoot | Out-Null

    try {
        [System.IO.Compression.ZipFile]::ExtractToDirectory($resolvedPackage, $tempRoot)
        & $Mutator $tempRoot

        if (Test-Path -LiteralPath $resolvedPackage) {
            Remove-Item -LiteralPath $resolvedPackage -Force
        }
        [System.IO.Compression.ZipFile]::CreateFromDirectory(
            $tempRoot,
            $resolvedPackage,
            [System.IO.Compression.CompressionLevel]::Optimal,
            $false
        )
    }
    finally {
        if (Test-Path -LiteralPath $tempRoot) {
            Remove-Item -LiteralPath $tempRoot -Recurse -Force
        }
    }
}

$pptPath = Join-Path $PSScriptRoot "..\\docs\\presentation\\Cloud Kinetics AI-Data Solution Architect Intern Assignment.pptx"
$docxPath = Join-Path $PSScriptRoot "..\\docs\\presentation\\04_SRS.docx"

Update-OfficePackage -PackagePath $pptPath -Mutator {
    param($root)

    $slideReplacements = @{
        "ppt/slides/slide1.xml" = @{
            "rag.ngxtm.site" = "Target-state architecture + pragmatic working implementation"
        }
        "ppt/slides/slide2.xml" = @{
            "Multi-turn conversation handling" = "Grounded Q&A"
            "Scalability thinking" = "Guarded order workflow"
            "Observability" = "Cloud-ready engineering"
            "Production-readiness mindset" = "Trade-off thinking and production-minded design"
        }
        "ppt/slides/slide3.xml" = @{
            "Partially Covered" = "Latest Branch / Partial"
            "- Streaming responses" = "- True streaming UX (latest repo branch; redeploy verification pending)"
            "  - Terraform-based IaC" = "  - Terraform-based IaC + CI checks"
        }
        "ppt/slides/slide4.xml" = @{
            "SOLUTION OVERVIEW" = "IMPLEMENTED ARCHITECTURE"
            "AWS Lambda via Mangum" = "AWS Lambda via Lambda Web Adapter"
            "API Gateway HTTP API" = "API Gateway REST API"
        }
        "ppt/slides/slide5.xml" = @{
            "TARGET VS DEPLOYED ARCHITECTURE" = "TARGET-STATE RECOMMENDATION VS IMPLEMENTED DELIVERY ARCHITECTURE"
            "Target Architecture" = "Target-State Recommendation"
            "Deployed / Verified Architecture" = "Implemented Delivery Architecture"
            "S3 VECTORS" = "S3 CORPUS"
            "S3 + DYNAMODB" = "S3 + DYNAMODB MEMORY"
            "LAMBDA + API GATEWAY" = "REST API + LAMBDA WEB ADAPTER"
            "BEDROCK" = "Lowest-risk assignment delivery path"
        }
        "ppt/slides/slide6.xml" = @{
            "Classify intent: KNOWLEDGE QA | ORDER_STATUS" = "Intent routing: KNOWLEDGE_QA | ORDER_STATUS | FALLBACK"
            "Persist user and assistant messages" = "Persist user and assistant messages in DynamoDB"
            "Store retrieval references or tool summary metadata" = "Persist retrieval refs and tool-result summaries"
            "ersist user and assistant messages" = "ersist user and assistant messages in DynamoDB"
            "re retrieval references or tool summary metadata" = "re retrieval refs and tool-result summaries"
        }
        "ppt/slides/slide7.xml" = @{
            "Combine lexical and vector-style evidence" = "Use hybrid retrieval with SEC-style preprocessing"
            "Rerank results by question type:" = "Rerank results by question type and document structure:"
            "Hallucination control" = "Heading-level retrieval"
        }
        "ppt/slides/slide8.xml" = @{
            "BEST ARCHITECHTURE" = "BEST ARCHITECTURE: AWS-NATIVE TARGET STATE"
        }
        "ppt/slides/slide9.xml" = @{
            "ASSUMPTION FOR PRICING" = "APPENDIX: PRICING ASSUMPTIONS"
        }
        "ppt/slides/slide10.xml" = @{
            "PRICING" = "APPENDIX: TARGET-STATE PRICING"
            'Note:Retrieval Layer: S3 document storage + S3 Vectors storage/query costGeneration + Query Embedding: number of knowledge requests × token usage × Bedrock model pricingOne-time indexing cost: SMB: ~$1 | Enterprise: ~$100' = 'Backup slide for target-state cost discussion. These figures assume an AWS-native Bedrock-oriented design, not the current implemented OpenSearch delivery path.'
            "Note:" = "Backup:"
            "Retrieval Layer: S3 document storage + S3 Vectors storage/query cost" = "Target-state pricing only: S3 + S3 Vectors retrieval cost assumption"
            "Generation + Query Embedding: number of knowledge requests × token usage × Bedrock model pricing" = "Bedrock-oriented generation cost assumption for architecture discussion"
            'One-time indexing cost: SMB: ~$1 | Enterprise: ~$100' = 'Use only if the panel asks about cost sensitivity'
        }
        "ppt/slides/slide11.xml" = @{
            "ARCHITECHTURE" = "ACTUAL REQUEST / RUNTIME FLOW"
        }
        "ppt/slides/slide12.xml" = @{
            "PRICING" = "APPENDIX: IMPLEMENTED-STACK PRICING"
            "Note:Retrieval Layer: OpenSearch Serverless compute floor + storageGeneration + Query Embedding: number of knowledge requests × token usage × Bedrock model pricing" = "Backup slide for the implemented stack. Retrieval cost reflects OpenSearch Serverless floor + storage, while generation cost should be modeled from the OpenAI-compatible endpoint and query volume."
            "Note:" = "Backup:"
            "Retrieval Layer: OpenSearch Serverless compute floor + storage" = "Implemented stack: OpenSearch Serverless compute floor + storage"
            "Generation + Query Embedding: number of knowledge requests × token usage × Bedrock model pricing" = "Generation estimate should come from the OpenAI-compatible endpoint, not Bedrock pricing"
        }
        "ppt/slides/slide14.xml" = @{
            "Simple serverless memory model" = "Simple serverless memory model for session continuity"
            "Enough to support continuity without overengineering" = "Chosen for multi-turn continuity, not long-term CRM history"
        }
        "ppt/slides/slide15.xml" = @{
            "Improves numeric retrieval and source precision" = "Improves numeric retrieval, heading recall, and source precision"
        }
        "ppt/slides/slide16.xml" = @{
            "Lambda runs the backend" = "Lambda backend packaged as zip artifact"
            "API Gateway exposes a minimal API surface" = "API Gateway REST API exposes public routes"
            "S3 stores document corpus inputs" = "S3 stores corpus inputs and drives ingestion"
        }
        "ppt/slides/slide17.xml" = @{
            "SSE streaming implemented for knowledge Q&A" = "Knowledge SSE stream emits status -> delta -> final"
            "SSE stre" = "Knowledge SSE stre"
            "aming implemented for knowledge Q&A" = "aming emits status -> delta -> final"
            "Order workflow intentionally remains non-streaming" = "Frontend renders progressive status, answer body, and sources"
            "Terraform supports validation and repeatable infrastructure" = "Order workflow intentionally remains non-streaming"
            "GitHub Actions CI runs:" = "Terraform + GitHub Actions support repeatable delivery:"
            "CD support workflow packages Lambda artifact and runs Terraform plan" = "CD support workflow packages the Lambda artifact and runs Terraform plan"
        }
        "ppt/slides/slide18.xml" = @{
            "Structured logs for:" = "Structured logs capture:"
            "Conservative fallback avoids unsupported or invented answers" = "PII-aware logging and conservative fallback reduce risk of wrong or sensitive responses"
        }
        "ppt/slides/slide19.xml" = @{
            "Stable fallback architecture vs forcing Bedrock under quota pressure" = "Target-state AWS-native architecture vs pragmatic delivery path"
        }
        "ppt/slides/slide20.xml" = @{
            "Problem, architecture, design rationale, trade-offs, roadmap" = "Slides: problem, target vs implemented architecture, trade-offs, roadmap"
            "Source code, tests, terraform, README, deployment / verification evidence" = "Repo: source code, tests, Terraform, CI, deployment / verification evidence"
            "Slides" = "Slides + SRS"
            "Demo" = "Demo / evidence"
        }
    }

    foreach ($entryPath in $slideReplacements.Keys) {
        $fullPath = Join-Path $root $entryPath
        Replace-OpenXmlTextValues -XmlPath $fullPath -Replacements $slideReplacements[$entryPath]
    }

    $slide17Path = Join-Path $root "ppt/slides/slide17.xml"
    [xml] $slide17 = Get-Content -LiteralPath $slide17Path -Raw
    $slide17TextNodes = $slide17.SelectNodes("//*[local-name()='t']")
    if ($slide17TextNodes.Count -gt 6) {
        $slide17TextNodes[6].InnerText = "Order workflow intentionally remains non-streaming"
        Save-Utf8NoBom -Path $slide17Path -Content $slide17.OuterXml
    }
}

Update-OfficePackage -PackagePath $docxPath -Mutator {
    param($root)

    $documentPath = Join-Path $root "word\\document.xml"
    $docReplacements = @{
        "The current implementation uses FastAPI, AWS Lambda, API Gateway, DynamoDB, OpenSearch Serverless, S3, Secrets Manager, Terraform, and an OpenAI-compatible LLM endpoint. The system is intentionally designed as an interview-defensible cloud MVP rather than a notebook-only AI prototype." = "The current implementation uses FastAPI, AWS Lambda, API Gateway, DynamoDB, OpenSearch Serverless, S3, Secrets Manager, Terraform, and an OpenAI-compatible LLM endpoint. This document explicitly separates a target-state architecture recommendation from the current implemented delivery path so both solution-architecture thinking and pragmatic execution are visible to reviewers. The system is intentionally designed as an interview-defensible cloud MVP rather than a notebook-only AI prototype, and the latest repo branch includes a true streaming UX path for knowledge responses while final cloud redeploy verification may still be pending."
        "This document describes the product requirements, system design, architectural trade-offs, RAG pipeline, security considerations, deployment model, testing strategy, current limitations, and future improvement opportunities." = "This document describes the product requirements, system design, architectural trade-offs, RAG pipeline, security considerations, deployment model, testing strategy, repository workflows such as pytest, terraform fmt -check, terraform validate, Lambda packaging, and Terraform plan support, plus current limitations and future improvement opportunities."
        "• Optional streaming responses for knowledge answers." = "• Knowledge-only SSE streaming with status, delta, final, and error events in the latest repo branch."
        "The system may support streaming responses for knowledge queries." = "The latest repo branch supports knowledge-only SSE streaming for grounded responses."
        "Order-status workflows should remain non-streaming to keep verification behavior deterministic." = "Order-status workflows remain non-streaming and reject the streaming endpoint to keep verification behavior deterministic."
        "The current deployed backend path uses:" = "The current implemented backend path in the latest repo uses:"
        "• Lambda adapter: Mangum" = "• Lambda adapter/runtime bridge: Lambda Web Adapter"
        "• API gateway: AWS API Gateway HTTP API" = "• API gateway: AWS API Gateway REST API"
        "API Gateway forwards the request to the backend Lambda." = "API Gateway REST API forwards the request to the backend Lambda runtime."
        "Mangum adapts the Lambda event into the FastAPI application." = "Lambda Web Adapter bridges the Lambda runtime to the FastAPI application and enables response streaming for /chat/stream."
        "The system was designed as a pragmatic cloud-native RAG application rather than a purely experimental notebook prototype. The architecture prioritizes deployability, explainability, and grounded behavior while accepting some trade-offs around production hardening and generic document support." = "The system was designed as a pragmatic cloud-native RAG application rather than a purely experimental notebook prototype. The architecture prioritizes deployability, explainability, and grounded behavior while accepting some trade-offs around production hardening and generic document support. The presentation intentionally preserves an AWS-native target-state recommendation while the implemented delivery path optimizes for delivery certainty, retrieval control, debuggability, and interview-defensible execution."
        "AWS Lambda with FastAPI via Mangum" = "AWS Lambda with FastAPI via Lambda Web Adapter"
        "API Gateway HTTP API" = "API Gateway REST API"
        "HTTP API is simpler and cost-effective for a small JSON chat API." = "REST API is used in the latest repo direction because it better supports true response streaming requirements for /chat/stream."
        "It has fewer advanced API management features than REST API." = "REST API adds more configuration complexity than HTTP API, but it better supports the streaming requirements of this repo direction."
        "OpenSearch provides AWS-native lexical, vector, and metadata-aware retrieval. It was also a practical fallback when Bedrock quota and runtime constraints created delivery risk." = "OpenSearch provides AWS-native lexical, vector, and metadata-aware retrieval while preserving retrieval control and debuggability. It was also a practical delivery path when Bedrock quota and runtime constraints created risk."
        "The streaming endpoint is intended for knowledge responses. Order verification workflows should remain deterministic and non-streaming." = "The streaming endpoint is intended for knowledge responses only. It emits SSE status, delta, final, and error events. Order verification workflows reject the streaming path and remain deterministic and non-streaming."
        'Amazon API Gateway (`HTTP API`)' = 'Amazon API Gateway (`REST API`)'
        "• API Gateway HTTP API." = "• API Gateway REST API."
    }

    Replace-OpenXmlTextValues -XmlPath $documentPath -Replacements $docReplacements
}

Write-Output "Updated presentation assets:"
Write-Output " - $pptPath"
Write-Output " - $docxPath"
