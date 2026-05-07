terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.36.0, < 7.0.0"
    }
  }
}

data "aws_partition" "current" {}

resource "terraform_data" "opensearch_index_bootstrap" {
  triggers_replace = {
    collection_endpoint = aws_opensearchserverless_collection.knowledge.collection_endpoint
    index_name          = var.opensearch_index_name
  }

  provisioner "local-exec" {
    command = "python ../../scripts/bootstrap_opensearch_index.py"
    environment = {
      AWS_REGION                     = var.aws_region
      OPENSEARCH_COLLECTION_ENDPOINT = aws_opensearchserverless_collection.knowledge.collection_endpoint
      OPENSEARCH_INDEX_NAME          = var.opensearch_index_name
    }
  }

  depends_on = [
    aws_opensearchserverless_access_policy.knowledge,
    aws_iam_user_policy.opensearch_local_user_access,
  ]
}

provider "aws" {
  region = var.aws_region
}
