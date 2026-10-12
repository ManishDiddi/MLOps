#!/bin/bash
# EC2 user data: runs once, as root, on the instance's first boot.
# Installs Docker, pulls the Milepost image from ECR and starts it on port 8000.
set -euo pipefail

# Keep a copy of everything this script prints.
exec > >(tee -a /var/log/milepost-bootstrap.log) 2>&1

REGION="us-west-2"
REPOSITORY="milepost-ec2"
TAG="v1"

# Ask the instance metadata service (IMDSv2) which AZ and instance this is.
TOKEN="$(curl -fsS -X PUT http://169.254.169.254/latest/api/token \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 300")"
AZ="$(curl -fsS -H "X-aws-ec2-metadata-token: $TOKEN" \
  http://169.254.169.254/latest/meta-data/placement/availability-zone)"
INSTANCE_ID="$(curl -fsS -H "X-aws-ec2-metadata-token: $TOKEN" \
  http://169.254.169.254/latest/meta-data/instance-id)"

# Install Docker; start it now and on every boot.
dnf install -y docker
systemctl enable --now docker

# The registry's address contains the account ID: ask AWS, using the instance's role.
ACCOUNT_ID="$(aws sts get-caller-identity --region "$REGION" --query Account --output text)"
REGISTRY="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"

# Log in to ECR with the instance's role, then pull the image.
aws ecr get-login-password --region "$REGION" |
  docker login --username AWS --password-stdin "$REGISTRY"
docker pull "$REGISTRY/$REPOSITORY:$TAG"

# Start the service: host port 8000 -> container port 8000.
# --restart unless-stopped starts it again after a reboot or a crash.
docker run -d --name milepost --restart unless-stopped \
  -p 8000:8000 \
  -e AVAILABILITY_ZONE="$AZ" \
  -e INSTANCE_ID="$INSTANCE_ID" \
  "$REGISTRY/$REPOSITORY:$TAG"
