variable "aws_region" {
  type    = string
  default = "ap-south-1"
}

variable "project" {
  type    = string
  default = "fleetpulse"
}

variable "vpc_cidr" {
  type    = string
  default = "10.20.0.0/16"
}

variable "eks_node_instance_type" {
  type    = string
  default = "t3.large"
}

variable "eks_node_desired_count" {
  type    = number
  default = 3
}

variable "rds_instance_class" {
  type    = string
  default = "db.t3.medium"
}

variable "msk_instance_type" {
  type    = string
  default = "kafka.t3.small"
}

variable "msk_broker_count" {
  type    = number
  default = 3
}
