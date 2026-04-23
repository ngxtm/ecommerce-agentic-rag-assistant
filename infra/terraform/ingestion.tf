resource "aws_lambda_permission" "docs_bucket_invoke_ingestion" {
  count = var.enable_docs_ingestion_trigger && var.create_docs_bucket ? 1 : 0

  statement_id  = "AllowDocsBucketInvokeIngestion"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingestion.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.docs[0].arn
}

resource "aws_s3_bucket_notification" "docs_ingestion" {
  count  = var.enable_docs_ingestion_trigger && var.create_docs_bucket ? 1 : 0
  bucket = aws_s3_bucket.docs[0].id

  dynamic "lambda_function" {
    for_each = toset(var.docs_ingestion_suffixes)
    content {
      lambda_function_arn = aws_lambda_function.ingestion.arn
      events              = ["s3:ObjectCreated:*"]
      filter_prefix       = local.docs_bucket_prefix == "" ? null : "${local.docs_bucket_prefix}/"
      filter_suffix       = lambda_function.value
    }
  }

  depends_on = [aws_lambda_permission.docs_bucket_invoke_ingestion]
}
