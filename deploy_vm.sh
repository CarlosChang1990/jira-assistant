#!/bin/bash
# Deploy Jira Assistant Bot to Google Compute Engine (VM)
# Usage: ./deploy_vm.sh

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}🚀 Deploying Jira Bot to GCE${NC}"
echo ""

# Check .env
if [ ! -f ".env" ]; then
    echo -e "${RED}❌ Error: .env file not found${NC}"
    exit 1
fi

# Load PROJECT_ID from .env
# We use the existing parsing logic to extract GCP_PROJECT_ID
echo -e "${YELLOW}📋 Reading configuration...${NC}"
PROJECT_ID=""

while IFS='=' read -r key value || [ -n "$key" ]; do
    # Skip empty lines and comments
    [[ -z "$key" || "$key" =~ ^# ]] && continue
    
    # Strip inline comments
    value="${value%%#*}"
    
    # Trim trailing whitespace
    value="${value%"${value##*[![:space:]]}"}"
    
    # Clean quotes
    value="${value%\"}"
    value="${value#\"}"
    value="${value%\'}"
    value="${value#\'}"
    
    if [[ "$key" == "GCP_PROJECT_ID" ]]; then
        PROJECT_ID="$value"
    fi
done < .env

# Fallback to gcloud config if not in .env
if [ -z "$PROJECT_ID" ]; then
    echo -e "${YELLOW}⚠️ GCP_PROJECT_ID not found in .env, trying gcloud config...${NC}"
    PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
fi

if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}❌ Error: Could not determine PROJECT_ID.${NC}"
    exit 1
fi

echo "Project ID: $PROJECT_ID"

# GCE Variables
VM_NAME="jira-bot-vm"
ZONE="us-central1-a"
IMAGE_REPO="gcr.io/$PROJECT_ID/jira-bot"

# Build & Push
echo ""
echo -e "${YELLOW}🔨 Building and pushing container image...${NC}"
gcloud builds submit --tag "$IMAGE_REPO" --project "$PROJECT_ID" .

# Prepare container env file
# This VM runs the container via the COS container runtime (konlet), which reads
# its image + env from the `gce-container-declaration` metadata. We therefore push
# the env through `update-container` / `create-with-container` rather than a custom
# startup-script (the old approach updated startup-script, which konlet ignores, so
# env changes such as a rotated JIRA_API_TOKEN never reached the running container).
echo ""
echo -e "${YELLOW}📋 Generating container env file...${NC}"

ENV_FILE="container-env.tmp"
: > "$ENV_FILE"

while IFS='=' read -r key value || [ -n "$key" ]; do
    # Skip empty lines and comments
    [[ -z "$key" || "$key" =~ ^# ]] && continue

    # Strip inline comments
    value="${value%%#*}"

    # Trim trailing whitespace
    value="${value%"${value##*[![:space:]]}"}"

    # Clean quotes
    value="${value%\"}"
    value="${value#\"}"
    value="${value%\'}"
    value="${value#\'}"

    echo "${key}=${value}" >> "$ENV_FILE"
done < .env

# Deploy to VM
echo ""
echo -e "${YELLOW}📦 Deploying to VM: $VM_NAME ($ZONE)...${NC}"

# Check if VM exists
if gcloud compute instances describe "$VM_NAME" --zone "$ZONE" --project "$PROJECT_ID" >/dev/null 2>&1; then
    echo "VM exists. Updating container declaration (image + env)..."

    # Updating the container declaration restarts the container automatically.
    gcloud compute instances update-container "$VM_NAME" \
        --zone "$ZONE" \
        --project "$PROJECT_ID" \
        --container-image "$IMAGE_REPO" \
        --container-env-file "$ENV_FILE"

    # Remove any stale startup-script from the previous deploy mechanism so it
    # cannot spin up a second, duplicate container alongside konlet's.
    gcloud compute instances remove-metadata "$VM_NAME" \
        --keys startup-script \
        --zone "$ZONE" \
        --project "$PROJECT_ID" 2>/dev/null || true
else
    echo "VM does not exist. Creating new VM with container..."
    gcloud compute instances create-with-container "$VM_NAME" \
        --project "$PROJECT_ID" \
        --zone "$ZONE" \
        --machine-type e2-micro \
        --boot-disk-size 30GB \
        --boot-disk-type pd-standard \
        --container-image "$IMAGE_REPO" \
        --container-env-file "$ENV_FILE" \
        --container-restart-policy always \
        --tags http-server,https-server
fi

# Cleanup local env file
rm "$ENV_FILE"

echo ""
echo -e "${GREEN}✅ Deployment complete! Container updated with latest image and env.${NC}"
