#!/bin/bash

# AWS Infrastructure Setup Script
# This script creates all necessary AWS resources for the notification platform

set -e

# Configuration
AWS_REGION=${AWS_REGION:-us-east-1}
PROJECT_NAME="notification"
VPC_CIDR="10.0.0.0/16"
SUBNET1_CIDR="10.0.1.0/24"
SUBNET2_CIDR="10.0.2.0/24"
DB_PASSWORD=${DB_PASSWORD:-$(openssl rand -base64 32)}

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
if ! command -v aws &> /dev/null; then
    print_error "AWS CLI is not installed"
    exit 1
fi

if ! command -v jq &> /dev/null; then
    print_warning "jq is not installed. Some features may not work properly."
fi

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
print_info "AWS Account ID: $AWS_ACCOUNT_ID"
print_info "AWS Region: $AWS_REGION"

# Create output file for resource IDs
OUTPUT_FILE="aws-resources.txt"
echo "AWS Resources Created on $(date)" > $OUTPUT_FILE
echo "======================================" >> $OUTPUT_FILE

# Step 1: Create VPC
print_info "Creating VPC..."
VPC_ID=$(aws ec2 create-vpc \
    --cidr-block $VPC_CIDR \
    --tag-specifications "ResourceType=vpc,Tags=[{Key=Name,Value=$PROJECT_NAME-vpc}]" \
    --query 'Vpc.VpcId' \
    --output text \
    --region $AWS_REGION)
echo "VPC_ID=$VPC_ID" >> $OUTPUT_FILE
print_info "VPC created: $VPC_ID"

# Enable DNS hostnames
aws ec2 modify-vpc-attribute --vpc-id $VPC_ID --enable-dns-hostnames --region $AWS_REGION

# Step 2: Create Internet Gateway
print_info "Creating Internet Gateway..."
IGW_ID=$(aws ec2 create-internet-gateway \
    --tag-specifications "ResourceType=internet-gateway,Tags=[{Key=Name,Value=$PROJECT_NAME-igw}]" \
    --query 'InternetGateway.InternetGatewayId' \
    --output text \
    --region $AWS_REGION)
echo "IGW_ID=$IGW_ID" >> $OUTPUT_FILE
print_info "Internet Gateway created: $IGW_ID"

# Attach IGW to VPC
aws ec2 attach-internet-gateway --vpc-id $VPC_ID --internet-gateway-id $IGW_ID --region $AWS_REGION

# Step 3: Create Subnets
print_info "Creating subnets..."
SUBNET1_ID=$(aws ec2 create-subnet \
    --vpc-id $VPC_ID \
    --cidr-block $SUBNET1_CIDR \
    --availability-zone ${AWS_REGION}a \
    --tag-specifications "ResourceType=subnet,Tags=[{Key=Name,Value=$PROJECT_NAME-public-subnet-1}]" \
    --query 'Subnet.SubnetId' \
    --output text \
    --region $AWS_REGION)
echo "SUBNET1_ID=$SUBNET1_ID" >> $OUTPUT_FILE
print_info "Subnet 1 created: $SUBNET1_ID"

SUBNET2_ID=$(aws ec2 create-subnet \
    --vpc-id $VPC_ID \
    --cidr-block $SUBNET2_CIDR \
    --availability-zone ${AWS_REGION}b \
    --tag-specifications "ResourceType=subnet,Tags=[{Key=Name,Value=$PROJECT_NAME-public-subnet-2}]" \
    --query 'Subnet.SubnetId' \
    --output text \
    --region $AWS_REGION)
echo "SUBNET2_ID=$SUBNET2_ID" >> $OUTPUT_FILE
print_info "Subnet 2 created: $SUBNET2_ID"

# Step 4: Create Route Table
print_info "Creating route table..."
RT_ID=$(aws ec2 create-route-table \
    --vpc-id $VPC_ID \
    --tag-specifications "ResourceType=route-table,Tags=[{Key=Name,Value=$PROJECT_NAME-public-rt}]" \
    --query 'RouteTable.RouteTableId' \
    --output text \
    --region $AWS_REGION)
echo "RT_ID=$RT_ID" >> $OUTPUT_FILE
print_info "Route table created: $RT_ID"

# Create route to IGW
aws ec2 create-route --route-table-id $RT_ID --destination-cidr-block 0.0.0.0/0 --gateway-id $IGW_ID --region $AWS_REGION

# Associate subnets with route table
aws ec2 associate-route-table --subnet-id $SUBNET1_ID --route-table-id $RT_ID --region $AWS_REGION
aws ec2 associate-route-table --subnet-id $SUBNET2_ID --route-table-id $RT_ID --region $AWS_REGION

# Step 5: Create Security Groups
print_info "Creating security groups..."

# ALB Security Group
ALB_SG=$(aws ec2 create-security-group \
    --group-name $PROJECT_NAME-alb-sg \
    --description "Security group for ALB" \
    --vpc-id $VPC_ID \
    --query 'GroupId' \
    --output text \
    --region $AWS_REGION)
echo "ALB_SG=$ALB_SG" >> $OUTPUT_FILE
print_info "ALB Security Group created: $ALB_SG"

aws ec2 authorize-security-group-ingress --group-id $ALB_SG --protocol tcp --port 80 --cidr 0.0.0.0/0 --region $AWS_REGION
aws ec2 authorize-security-group-ingress --group-id $ALB_SG --protocol tcp --port 443 --cidr 0.0.0.0/0 --region $AWS_REGION

# ECS Security Group
ECS_SG=$(aws ec2 create-security-group \
    --group-name $PROJECT_NAME-ecs-sg \
    --description "Security group for ECS tasks" \
    --vpc-id $VPC_ID \
    --query 'GroupId' \
    --output text \
    --region $AWS_REGION)
echo "ECS_SG=$ECS_SG" >> $OUTPUT_FILE
print_info "ECS Security Group created: $ECS_SG"

aws ec2 authorize-security-group-ingress --group-id $ECS_SG --protocol tcp --port 8000 --source-group $ALB_SG --region $AWS_REGION
aws ec2 authorize-security-group-ingress --group-id $ECS_SG --protocol tcp --port 6379 --source-group $ECS_SG --region $AWS_REGION

# RDS Security Group
RDS_SG=$(aws ec2 create-security-group \
    --group-name $PROJECT_NAME-rds-sg \
    --description "Security group for RDS" \
    --vpc-id $VPC_ID \
    --query 'GroupId' \
    --output text \
    --region $AWS_REGION)
echo "RDS_SG=$RDS_SG" >> $OUTPUT_FILE
print_info "RDS Security Group created: $RDS_SG"

aws ec2 authorize-security-group-ingress --group-id $RDS_SG --protocol tcp --port 5432 --source-group $ECS_SG --region $AWS_REGION

# Step 6: Create RDS Subnet Group
print_info "Creating RDS subnet group..."
aws rds create-db-subnet-group \
    --db-subnet-group-name $PROJECT_NAME-db-subnet \
    --db-subnet-group-description "Subnet group for $PROJECT_NAME DB" \
    --subnet-ids $SUBNET1_ID $SUBNET2_ID \
    --region $AWS_REGION

# Step 7: Create RDS Instance
print_info "Creating RDS PostgreSQL instance (this will take 5-10 minutes)..."
RDS_ENDPOINT=$(aws rds create-db-instance \
    --db-instance-identifier $PROJECT_NAME-db \
    --db-instance-class db.t3.micro \
    --engine postgres \
    --engine-version 15.4 \
    --master-username postgres \
    --master-user-password "$DB_PASSWORD" \
    --allocated-storage 20 \
    --vpc-security-group-ids $RDS_SG \
    --db-subnet-group-name $PROJECT_NAME-db-subnet \
    --backup-retention-period 7 \
    --publicly-accessible false \
    --storage-encrypted \
    --region $AWS_REGION \
    --query 'DBInstance.Endpoint.Address' \
    --output text 2>/dev/null || echo "pending")

echo "RDS_ENDPOINT=$RDS_ENDPOINT" >> $OUTPUT_FILE
echo "DB_PASSWORD=$DB_PASSWORD" >> $OUTPUT_FILE
print_info "RDS instance creation initiated"

# Wait for RDS to be available
print_info "Waiting for RDS instance to be available..."
aws rds wait db-instance-available --db-instance-identifier $PROJECT_NAME-db --region $AWS_REGION

# Get actual endpoint
RDS_ENDPOINT=$(aws rds describe-db-instances \
    --db-instance-identifier $PROJECT_NAME-db \
    --query 'DBInstances[0].Endpoint.Address' \
    --output text \
    --region $AWS_REGION)
echo "RDS_ENDPOINT=$RDS_ENDPOINT" >> $OUTPUT_FILE
print_info "RDS endpoint: $RDS_ENDPOINT"

# Step 8: Create ECR Repositories
print_info "Creating ECR repositories..."
aws ecr create-repository --repository-name $PROJECT_NAME-api --region $AWS_REGION 2>/dev/null || print_warning "API repository already exists"
aws ecr create-repository --repository-name $PROJECT_NAME-celery --region $AWS_REGION 2>/dev/null || print_warning "Celery repository already exists"

# Step 9: Create ECS Cluster
print_info "Creating ECS cluster..."
aws ecs create-cluster --cluster-name $PROJECT_NAME-cluster --region $AWS_REGION 2>/dev/null || print_warning "Cluster already exists"

# Step 10: Create CloudWatch Log Groups
print_info "Creating CloudWatch log groups..."
aws logs create-log-group --log-group-name /ecs/$PROJECT_NAME-api --region $AWS_REGION 2>/dev/null || print_warning "API log group already exists"
aws logs create-log-group --log-group-name /ecs/$PROJECT_NAME-celery --region $AWS_REGION 2>/dev/null || print_warning "Celery log group already exists"
aws logs create-log-group --log-group-name /ecs/$PROJECT_NAME-redis --region $AWS_REGION 2>/dev/null || print_warning "Redis log group already exists"

# Step 11: Create IAM Role for ECS Tasks
print_info "Creating IAM role for ECS tasks..."
cat > ecs-task-trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

aws iam create-role \
    --role-name ecsTaskExecutionRole \
    --assume-role-policy-document file://ecs-task-trust-policy.json \
    --region $AWS_REGION 2>/dev/null || print_warning "IAM role already exists"

aws iam attach-role-policy \
    --role-name ecsTaskExecutionRole \
    --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy \
    --region $AWS_REGION 2>/dev/null || true

rm ecs-task-trust-policy.json

# Step 12: Create Application Load Balancer
print_info "Creating Application Load Balancer..."
ALB_ARN=$(aws elbv2 create-load-balancer \
    --name $PROJECT_NAME-alb \
    --subnets $SUBNET1_ID $SUBNET2_ID \
    --security-groups $ALB_SG \
    --scheme internet-facing \
    --type application \
    --query 'LoadBalancers[0].LoadBalancerArn' \
    --output text \
    --region $AWS_REGION)
echo "ALB_ARN=$ALB_ARN" >> $OUTPUT_FILE
print_info "ALB created: $ALB_ARN"

# Get ALB DNS
ALB_DNS=$(aws elbv2 describe-load-balancers \
    --load-balancer-arns $ALB_ARN \
    --query 'LoadBalancers[0].DNSName' \
    --output text \
    --region $AWS_REGION)
echo "ALB_DNS=$ALB_DNS" >> $OUTPUT_FILE
print_info "ALB DNS: $ALB_DNS"

# Step 13: Create Target Group
print_info "Creating target group..."
TG_ARN=$(aws elbv2 create-target-group \
    --name $PROJECT_NAME-tg \
    --protocol HTTP \
    --port 8000 \
    --vpc-id $VPC_ID \
    --target-type ip \
    --health-check-path /health \
    --health-check-interval-seconds 30 \
    --health-check-timeout-seconds 5 \
    --healthy-threshold-count 2 \
    --unhealthy-threshold-count 3 \
    --query 'TargetGroups[0].TargetGroupArn' \
    --output text \
    --region $AWS_REGION)
echo "TG_ARN=$TG_ARN" >> $OUTPUT_FILE
print_info "Target Group created: $TG_ARN"

# Step 14: Create Listener
print_info "Creating ALB listener..."
aws elbv2 create-listener \
    --load-balancer-arn $ALB_ARN \
    --protocol HTTP \
    --port 80 \
    --default-actions Type=forward,TargetGroupArn=$TG_ARN \
    --region $AWS_REGION

# Step 15: Store secrets in Parameter Store
print_info "Storing secrets in AWS Systems Manager Parameter Store..."
DATABASE_URL="postgresql://postgres:$DB_PASSWORD@$RDS_ENDPOINT:5432/$PROJECT_NAME"
echo "DATABASE_URL=$DATABASE_URL" >> $OUTPUT_FILE

aws ssm put-parameter \
    --name /$PROJECT_NAME/DATABASE_URL \
    --value "$DATABASE_URL" \
    --type SecureString \
    --overwrite \
    --region $AWS_REGION

print_info "Generating secret keys..."
SECRET_KEY=$(openssl rand -base64 32)
JWT_SECRET=$(openssl rand -base64 32)

aws ssm put-parameter \
    --name /$PROJECT_NAME/SECRET_KEY \
    --value "$SECRET_KEY" \
    --type SecureString \
    --overwrite \
    --region $AWS_REGION

aws ssm put-parameter \
    --name /$PROJECT_NAME/JWT_SECRET_KEY \
    --value "$JWT_SECRET" \
    --type SecureString \
    --overwrite \
    --region $AWS_REGION

echo ""
echo "======================================" | tee -a $OUTPUT_FILE
echo "Infrastructure Setup Complete!" | tee -a $OUTPUT_FILE
echo "======================================" | tee -a $OUTPUT_FILE
echo "" | tee -a $OUTPUT_FILE
echo "Resource IDs saved to: $OUTPUT_FILE" | tee -a $OUTPUT_FILE
echo "" | tee -a $OUTPUT_FILE
echo "Important Information:" | tee -a $OUTPUT_FILE
echo "- VPC ID: $VPC_ID" | tee -a $OUTPUT_FILE
echo "- Subnet 1: $SUBNET1_ID" | tee -a $OUTPUT_FILE
echo "- Subnet 2: $SUBNET2_ID" | tee -a $OUTPUT_FILE
echo "- ECS Security Group: $ECS_SG" | tee -a $OUTPUT_FILE
echo "- RDS Endpoint: $RDS_ENDPOINT" | tee -a $OUTPUT_FILE
echo "- ALB DNS: $ALB_DNS" | tee -a $OUTPUT_FILE
echo "- Target Group ARN: $TG_ARN" | tee -a $OUTPUT_FILE
echo "" | tee -a $OUTPUT_FILE
echo "Database Password: $DB_PASSWORD" | tee -a $OUTPUT_FILE
echo "" | tee -a $OUTPUT_FILE
echo "Next Steps:" | tee -a $OUTPUT_FILE
echo "1. Update your .env file with the DATABASE_URL" | tee -a $OUTPUT_FILE
echo "2. Add your provider credentials to Parameter Store" | tee -a $OUTPUT_FILE
echo "3. Create and register ECS task definition" | tee -a $OUTPUT_FILE
echo "4. Deploy your application using deploy-to-aws.sh" | tee -a $OUTPUT_FILE
echo "" | tee -a $OUTPUT_FILE
