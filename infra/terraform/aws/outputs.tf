output "eks_cluster_name" {
  value = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "rds_endpoint" {
  value     = module.rds.db_instance_endpoint
  sensitive = true
}

output "msk_bootstrap_brokers_tls" {
  value     = module.msk.bootstrap_brokers_tls
  sensitive = true
}

output "lake_bucket_name" {
  value = module.lake_bucket.s3_bucket_id
}
