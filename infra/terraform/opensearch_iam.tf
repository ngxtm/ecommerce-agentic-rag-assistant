data "aws_iam_policy_document" "opensearch_local_user_access" {
  count = length(var.opensearch_local_iam_user_names) > 0 ? 1 : 0

  statement {
    sid    = "AOSSLocalBootstrapAccess"
    effect = "Allow"
    actions = [
      "aoss:APIAccessAll",
      "aoss:DashboardsAccessAll",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_user_policy" "opensearch_local_user_access" {
  for_each = toset(var.opensearch_local_iam_user_names)

  name   = "${substr(replace(each.key, "_", "-"), 0, 24)}-aoss-access"
  user   = each.key
  policy = data.aws_iam_policy_document.opensearch_local_user_access[0].json
}
