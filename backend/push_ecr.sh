#!/usr/bin/env bash
set -e

# Configuration
AWS_REGION="${AWS_REGION:-ap-southeast-1}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-}"
REPO_NAME="${ECR_REPO_NAME:-orbitmesh-backend}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "=== OrbitMesh Backend ECR Push ==="

# Check requirements
command -v aws >/dev/null 2>&1 || { echo "Error: AWS CLI is required but not installed." >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "Error: Docker is required but not installed." >&2; exit 1; }

# Auto-detect AWS Account ID if not provided
if [ -z "$AWS_ACCOUNT_ID" ]; then
    echo "Retrieving AWS Account ID..."
    AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || true)
    if [ -z "$AWS_ACCOUNT_ID" ]; then
        echo "Error: AWS_ACCOUNT_ID not set and could not be detected. Set AWS_ACCOUNT_ID environment variable." >&2
        exit 1
    fi
fi

ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE_URI="${ECR_REGISTRY}/${REPO_NAME}:${IMAGE_TAG}"

echo "Region:     $AWS_REGION"
echo "Account ID: $AWS_ACCOUNT_ID"
echo "Repository: $REPO_NAME"
echo "Image Tag:  $IMAGE_TAG"
echo "Image URI:  $IMAGE_URI"

# 1. Login to Amazon ECR
echo "Logging in to Amazon ECR..."
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY"

# 2. Ensure repository exists
echo "Checking if ECR repository exists..."
if ! aws ecr describe-repositories --repository-names "$REPO_NAME" --region "$AWS_REGION" >/dev/null 2>&1; then
    echo "Creating repository $REPO_NAME..."
    aws ecr create-repository --repository-name "$REPO_NAME" --region "$AWS_REGION"
fi

# 3. Build Docker image
echo "Building Backend Docker image..."
docker build -f backend/Dockerfile -t "$REPO_NAME:$IMAGE_TAG" .

# 4. Tag Docker image for ECR
echo "Tagging Docker image..."
docker tag "$REPO_NAME:$IMAGE_TAG" "$IMAGE_URI"

# 5. Push to ECR
echo "Pushing image to ECR..."
docker push "$IMAGE_URI"

echo "Successfully pushed $IMAGE_URI to Amazon ECR."
