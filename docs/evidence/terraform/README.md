# Terraform evidence (PLAN §5 "Deploy: Terraform for AWS ... `validate` and `plan` are the evidence unless cloud credit appears")

- `validate_output.txt` — `terraform validate` against `infra/terraform/aws`: **passes**, using the real community AWS modules (`terraform-aws-modules/{vpc,eks,rds,msk-kafka-cluster,s3-bucket}/aws`) pulled from the public registry, not stubbed.
- `plan_output.txt` — `terraform plan`: gets as far as planning the two credential-free resources (`random_id` for RDS/MSK naming), then fails on `No valid credential sources found` — expected and honest, since no AWS account/credit was available for this hackathon. This is as far as `plan` can go without real AWS credentials.

Reproduce: `cd infra/terraform/aws && terraform init && terraform validate && terraform plan`.
