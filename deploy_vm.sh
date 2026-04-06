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

# Prepare Startup Script
echo ""
echo -e "${YELLOW}� Generating startup script...${NC}"

STARTUP_SCRIPT="startup-script.sh"

# Create startup script locally
cat > "$STARTUP_SCRIPT" <<EOF
#!/bin/bash
set -e

# Write .env file to /tmp/.env
cat > /tmp/.env <<ENV_EOF
$(cat .env)
ENV_EOF

# Authenticate Docker (COS behavior)
docker-credential-gcr configure-docker

# Pull latest image
echo "Pulling image: $IMAGE_REPO"
docker pull "$IMAGE_REPO"

# Stop and remove existing container if running
echo "Stopping old container..."
docker stop jira-bot || true
docker rm jira-bot || true

# Run new container
echo "Starting new container..."
docker run -d \\
  --name jira-bot \\
  --restart always \\
  --env-file /tmp/.env \\
  "$IMAGE_REPO"
EOF

# Deploy to VM
echo ""
echo -e "${YELLOW}📦 Deploying to VM: $VM_NAME ($ZONE)...${NC}"

# Check if VM exists
if gcloud compute instances describe "$VM_NAME" --zone "$ZONE" --project "$PROJECT_ID" >/dev/null 2>&1; then
    echo "VM exists. Updating metadata..."
    
    # Update startup-script metadata
    gcloud compute instances add-metadata "$VM_NAME" \
        --metadata-from-file startup-script="$STARTUP_SCRIPT" \
        --zone "$ZONE" \
        --project "$PROJECT_ID"
        
    # Check VM status to decide reset vs start
    VM_STATUS=$(gcloud compute instances describe "$VM_NAME" \
        --zone "$ZONE" \
        --project "$PROJECT_ID" \
        --format="value(status)")
    
    if [ "$VM_STATUS" = "RUNNING" ]; then
        echo "VM is running. Resetting to apply changes..."
        gcloud compute instances reset "$VM_NAME" \
            --zone "$ZONE" \
            --project "$PROJECT_ID"
    else
        echo "VM is stopped ($VM_STATUS). Starting VM..."
        gcloud compute instances start "$VM_NAME" \
            --zone "$ZONE" \
            --project "$PROJECT_ID"
    fi
else
    echo "VM does not exist. Creating new VM..."
    gcloud compute instances create "$VM_NAME" \
        --project "$PROJECT_ID" \
        --zone "$ZONE" \
        --machine-type e2-micro \
        --image-family cos-stable \
        --image-project cos-cloud \
        --boot-disk-size 30GB \
        --boot-disk-type pd-standard \
        --metadata-from-file startup-script="$STARTUP_SCRIPT" \
        --tags http-server,https-server
fi

# Cleanup local startup script
rm "$STARTUP_SCRIPT"

echo ""
echo -e "${GREEN}✅ Deployment complete! VM is rebooting/starting.${NC}"
