# PLAN §5 "Deploy: Terraform for AWS (VPC, EKS, MSK, RDS, S3, KMS, Secrets
# Manager); `validate` and `plan` are the evidence unless cloud credit
# appears" — built from community AWS modules (PLAN §6.2), not hand-written
# resources, to keep this file short and let the maintained modules carry
# the hard parts (subnetting, IRSA, broker config).

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "${var.project}-vpc"
  cidr = var.vpc_cidr

  azs             = ["${var.aws_region}a", "${var.aws_region}b", "${var.aws_region}c"]
  private_subnets = ["10.20.1.0/24", "10.20.2.0/24", "10.20.3.0/24"]
  public_subnets  = ["10.20.101.0/24", "10.20.102.0/24", "10.20.103.0/24"]

  enable_nat_gateway   = true
  single_nat_gateway   = true # POC cost trim, not one-per-AZ
  enable_dns_hostnames = true

  tags = { Project = var.project }
}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = "${var.project}-eks"
  cluster_version = "1.30"

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  eks_managed_node_groups = {
    default = {
      instance_types = [var.eks_node_instance_type]
      min_size       = 1
      max_size       = var.eks_node_desired_count + 2
      desired_size   = var.eks_node_desired_count
    }
  }

  tags = { Project = var.project }
}

module "rds" {
  source  = "terraform-aws-modules/rds/aws"
  version = "~> 6.0"

  identifier = "${var.project}-postgres"

  engine               = "postgres"
  engine_version       = "16"
  family               = "postgres16"
  major_engine_version = "16"
  instance_class       = var.rds_instance_class

  allocated_storage     = 50
  max_allocated_storage = 200
  storage_encrypted     = true

  db_name  = "fleetpulse"
  username = "fleetpulse"
  port     = 5432

  manage_master_user_password = true # rotated via Secrets Manager, not a plaintext var

  vpc_security_group_ids = [aws_security_group.rds.id]
  db_subnet_group_name   = module.vpc.database_subnet_group_name
  create_db_subnet_group = true
  subnet_ids             = module.vpc.private_subnets

  tags = { Project = var.project }
}

resource "aws_security_group" "rds" {
  name_prefix = "${var.project}-rds-"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [module.eks.node_security_group_id]
  }
}

module "msk" {
  source  = "terraform-aws-modules/msk-kafka-cluster/aws"
  version = "~> 2.0"

  name                   = "${var.project}-msk"
  kafka_version          = "3.6.0"
  number_of_broker_nodes = var.msk_broker_count

  broker_node_client_subnets  = module.vpc.private_subnets
  broker_node_instance_type   = var.msk_instance_type
  broker_node_security_groups = [aws_security_group.msk.id]

  encryption_in_transit_client_broker = "TLS"
  encryption_at_rest_kms_key_arn      = aws_kms_key.fleetpulse.arn

  tags = { Project = var.project }
}

resource "aws_security_group" "msk" {
  name_prefix = "${var.project}-msk-"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port       = 9092
    to_port         = 9098
    protocol        = "tcp"
    security_groups = [module.eks.node_security_group_id]
  }
}

resource "aws_kms_key" "fleetpulse" {
  description             = "${var.project} data-at-rest encryption (RDS, MSK, S3)"
  deletion_window_in_days = 7
}

module "lake_bucket" {
  source  = "terraform-aws-modules/s3-bucket/aws"
  version = "~> 4.0"

  bucket = "${var.project}-lake-${data.aws_caller_identity.current.account_id}"

  server_side_encryption_configuration = {
    rule = {
      apply_server_side_encryption_by_default = {
        sse_algorithm     = "aws:kms"
        kms_master_key_id = aws_kms_key.fleetpulse.arn
      }
    }
  }

  lifecycle_rule = [
    {
      id      = "warm-to-cold"
      enabled = true
      transition = [
        { days = 90, storage_class = "GLACIER" } # PLAN §2 lifecycle: warm 90d -> cold/Glacier-class
      ]
    }
  ]

  tags = { Project = var.project }
}

resource "aws_secretsmanager_secret" "app" {
  name        = "${var.project}/app-secrets"
  description = "GOOGLE_API_KEY, Keycloak admin, JWT signing — PLAN §2 Security: Vault dropped, AWS Secrets Manager used in k8s"
  kms_key_id  = aws_kms_key.fleetpulse.arn
}

data "aws_caller_identity" "current" {}
