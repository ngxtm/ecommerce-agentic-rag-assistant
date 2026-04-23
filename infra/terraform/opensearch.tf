locals {
  opensearch_policy_prefix = substr(replace("${var.project_name}-${var.environment}", "_", "-"), 0, 24)
}

resource "aws_opensearchserverless_security_policy" "encryption" {
  name = "${local.opensearch_policy_prefix}-enc"
  type = "encryption"

  policy = jsonencode({
    Rules = [
      {
        ResourceType = "collection"
        Resource     = ["collection/${var.opensearch_collection_name}"]
      }
    ]
    AWSOwnedKey = true
  })
}

resource "aws_opensearchserverless_security_policy" "network" {
  name = "${local.opensearch_policy_prefix}-net"
  type = "network"

  policy = jsonencode([
    {
      Description = "Network policy for ${var.opensearch_collection_name}"
      Rules = [
        {
          ResourceType = "collection"
          Resource     = ["collection/${var.opensearch_collection_name}"]
        },
        {
          ResourceType = "dashboard"
          Resource     = ["collection/${var.opensearch_collection_name}"]
        }
      ]
      AllowFromPublic = var.opensearch_allow_public_access
    }
  ])
}

resource "aws_opensearchserverless_collection" "knowledge" {
  name = var.opensearch_collection_name
  type = var.opensearch_collection_type

  depends_on = [
    aws_opensearchserverless_security_policy.encryption,
    aws_opensearchserverless_security_policy.network,
  ]

  tags = local.base_tags
}

resource "aws_opensearchserverless_access_policy" "knowledge" {
  name = "${local.opensearch_policy_prefix}-acc"
  type = "data"

  policy = jsonencode([
    {
      Description = "Access policy for ${var.opensearch_collection_name}"
      Rules = [
        {
          ResourceType = "collection"
          Resource     = ["collection/${aws_opensearchserverless_collection.knowledge.name}"]
          Permission = [
            "aoss:DescribeCollectionItems",
            "aoss:CreateCollectionItems",
            "aoss:UpdateCollectionItems",
          ]
        },
        {
          ResourceType = "index"
          Resource     = ["index/${aws_opensearchserverless_collection.knowledge.name}/*"]
          Permission = [
            "aoss:CreateIndex",
            "aoss:DeleteIndex",
            "aoss:DescribeIndex",
            "aoss:UpdateIndex",
            "aoss:ReadDocument",
            "aoss:WriteDocument",
          ]
        }
      ]
      Principal = concat([aws_iam_role.lambda.arn, aws_iam_role.ingestion.arn], var.opensearch_additional_principal_arns)
    }
  ])
}
