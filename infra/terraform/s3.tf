resource "aws_s3_bucket" "docs" {
  count  = var.create_docs_bucket ? 1 : 0
  bucket = local.effective_docs_bucket_name

  tags = local.base_tags
}

resource "aws_s3_bucket_versioning" "docs" {
  count  = var.create_docs_bucket ? 1 : 0
  bucket = aws_s3_bucket.docs[0].id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "docs" {
  count  = var.create_docs_bucket ? 1 : 0
  bucket = aws_s3_bucket.docs[0].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "docs" {
  count  = var.create_docs_bucket ? 1 : 0
  bucket = aws_s3_bucket.docs[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
