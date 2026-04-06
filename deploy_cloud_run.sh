#!/bin/bash
# Deploy Jira Assistant Bot to Google Cloud Run
# Usage: ./deploy.sh

set -e

# Service name = current directory name (default gcloud behavior)
SERVICE_NAME="${PWD##*/}"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}🚀 Deploying $SERVICE_NAME to Cloud Run${NC}"
echo ""

# Check .env
if [ ! -f ".env" ]; then
    echo -e "${RED}❌ Error: .env file not found${NC}"
    exit 1
fi

# Build env vars from .env
echo -e "${YELLOW}📋 Loading environment variables...${NC}"
ENV_VARS=""
PROJECT_ID=""
REGION=""

while IFS='=' read -r key value || [ -n "$key" ]; do
    # Skip empty lines and comments starting with #
    [[ -z "$key" || "$key" =~ ^# ]] && continue
    
    # Strip inline comments (everything after #)
    value="${value%%#*}"
    
    # Trim trailing whitespace
    value="${value%"${value##*[![:space:]]}"}"
    
    # Clean quotes
    value="${value%\"}"
    value="${value#\"}"
    value="${value%\'}"
    value="${value#\'}"
    
    # Extract special deployment vars
    if [[ "$key" == "GCP_PROJECT_ID" ]]; then
        PROJECT_ID="$value"
        continue
    fi
    if [[ "$key" == "CLOUD_RUN_REGION" ]]; then
        REGION="$value"
        continue
    fi
    # Also skip local takeover service name
    [[ "$key" == "CLOUD_RUN_SERVICE_NAME" ]] && continue
    
    if [ -n "$ENV_VARS" ]; then
        ENV_VARS="$ENV_VARS,$key=$value"
    else
        ENV_VARS="$key=$value"
    fi
done < .env

# Deploy command construction
DEPLOY_CMD=(gcloud run deploy "$SERVICE_NAME" \
    --source . \
    --set-env-vars "$ENV_VARS" \
    --no-cpu-throttling \
    --min-instances 1 \
    --max-instances 1 \
    --memory 512Mi \
    --timeout 3600 \
    --no-allow-unauthenticated)

if [ -n "$PROJECT_ID" ]; then
    DEPLOY_CMD+=(--project "$PROJECT_ID")
fi
if [ -n "$REGION" ]; then
    DEPLOY_CMD+=(--region "$REGION")
fi

# Deploy
echo -e "${YELLOW}🔨 Building and deploying...${NC}"
if [ -n "$PROJECT_ID" ]; then
  echo "Project: $PROJECT_ID"
fi
if [ -n "$REGION" ]; then
  echo "Region: $REGION"
fi

"${DEPLOY_CMD[@]}"

echo ""
echo -e "${GREEN}✅ Deployment complete!${NC}"
