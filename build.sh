#!/bin/bash

# Build script for the insurance requests application

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Building Docker image for insurance requests application...${NC}"

# Get the current git commit hash for tagging
if command -v git &> /dev/null && git rev-parse --git-dir > /dev/null 2>&1; then
    GIT_COMMIT=$(git rev-parse --short HEAD)
    echo -e "${YELLOW}Using git commit: ${GIT_COMMIT}${NC}"
else
    GIT_COMMIT="latest"
    echo -e "${YELLOW}Git not available, using tag: ${GIT_COMMIT}${NC}"
fi

# Build the Docker image
IMAGE_NAME="flow-insur-requests"
FULL_TAG="${IMAGE_NAME}:${GIT_COMMIT}"

echo -e "${GREEN}Building image: ${FULL_TAG}${NC}"

docker build \
    --tag "${FULL_TAG}" \
    --tag "${IMAGE_NAME}:latest" \
    .

echo -e "${GREEN}✅ Build completed successfully!${NC}"
echo -e "${GREEN}Image tags:${NC}"
echo -e "  - ${FULL_TAG}"
echo -e "  - ${IMAGE_NAME}:latest"

echo -e "${YELLOW}To run the application locally:${NC}"
echo -e "  docker run -p 8000:8000 --env-file .env ${IMAGE_NAME}:latest"

echo -e "${YELLOW}To run with docker-compose:${NC}"
echo -e "  docker-compose up -d"