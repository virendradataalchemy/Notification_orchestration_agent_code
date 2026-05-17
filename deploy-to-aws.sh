#!/bin/bash

# AWS Deployment Script for Notification Platform
# This script automates the deployment process to AWS ECS

set -e

echo "==================================="
echo "AWS Deployment Script"
echo "==================================="

# Configuration
AWS_REGION=${AWS_REGION:-us-east-1}
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
CLUSTER_NAME="notification-cluster"
SERVICE_NAME="notification-service"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    print_error "AWS CLI is not installed. Please install it first."
    exit 1
fi

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install it first."
    exit 1
fi

print_info "AWS Account ID: $AWS_ACCOUNT_ID"
print_info "AWS Region: $AWS_REGION"

# Step 1: Login to ECR
print_info "Logging in to Amazon ECR..."
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

# Step 2: Build Docker images
print_info "Building Docker images..."

print_info "Building API image..."
docker build -t notification-api:latest -f Dockerfile .

print_info "Building Celery image..."
docker build -t notification-celery:latest -f Dockerfile.celery .

# Step 3: Tag images
print_info "Tagging images..."
docker tag notification-api:latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/notification-api:latest
docker tag notification-celery:latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/notification-celery:latest

# Step 4: Push images to ECR
print_info "Pushing images to ECR..."
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/notification-api:latest
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/notification-celery:latest

# Step 5: Update ECS service
print_info "Updating ECS service..."
aws ecs update-service \
    --cluster $CLUSTER_NAME \
    --service $SERVICE_NAME \
    --force-new-deployment \
    --region $AWS_REGION

print_info "Waiting for service to stabilize..."
aws ecs wait services-stable \
    --cluster $CLUSTER_NAME \
    --services $SERVICE_NAME \
    --region $AWS_REGION

print_info "Deployment completed successfully!"

# Get service status
print_info "Service status:"
aws ecs describe-services \
    --cluster $CLUSTER_NAME \
    --services $SERVICE_NAME \
    --region $AWS_REGION \
    --query 'services[0].{Status:status,Running:runningCount,Desired:desiredCount}' \
    --output table

# Get ALB URL
print_info "Getting Application Load Balancer URL..."
ALB_ARN=$(aws ecs describe-services \
    --cluster $CLUSTER_NAME \
    --services $SERVICE_NAME \
    --region $AWS_REGION \
    --query 'services[0].loadBalancers[0].targetGroupArn' \
    --output text)

if [ "$ALB_ARN" != "None" ]; then
    TG_ARN=$(echo $ALB_ARN | cut -d'/' -f2-)
    ALB_ARN=$(aws elbv2 describe-target-groups \
        --target-group-arns $ALB_ARN \
        --region $AWS_REGION \
        --query 'TargetGroups[0].LoadBalancerArns[0]' \
        --output text)
    
    ALB_DNS=$(aws elbv2 describe-load-balancers \
        --load-balancer-arns $ALB_ARN \
        --region $AWS_REGION \
        --query 'LoadBalancers[0].DNSName' \
        --output text)
    
    print_info "Application URL: http://$ALB_DNS"
    print_info "API Documentation: http://$ALB_DNS/api/v1/docs"
fi

echo ""
echo "==================================="
echo "Deployment Complete!"
echo "==================================="
