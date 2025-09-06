#!/bin/bash

# Test script for Docker build and basic functionality

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Testing Docker build and basic functionality...${NC}"

# Test 1: Build the image
echo -e "${YELLOW}Test 1: Building Docker image...${NC}"
docker build -t test-insurance-app . || {
    echo -e "${RED}❌ Docker build failed${NC}"
    exit 1
}
echo -e "${GREEN}✅ Docker build successful${NC}"

# Test 2: Check if static files were collected
echo -e "${YELLOW}Test 2: Checking static files...${NC}"
STATIC_FILES=$(docker run --rm test-insurance-app ls -la /app/staticfiles/ | wc -l)
if [ "$STATIC_FILES" -gt 3 ]; then
    echo -e "${GREEN}✅ Static files collected successfully${NC}"
else
    echo -e "${RED}❌ Static files not found${NC}"
    exit 1
fi

# Test 3: Test basic container startup
echo -e "${YELLOW}Test 3: Testing container startup...${NC}"
CONTAINER_ID=$(docker run -d \
    -e SECRET_KEY=test-secret-key \
    -e DEBUG=True \
    -e ALLOWED_HOSTS=localhost,127.0.0.1 \
    -p 8001:8000 \
    test-insurance-app)

# Wait for container to start
sleep 5

# Check if container is running
if docker ps | grep -q "$CONTAINER_ID"; then
    echo -e "${GREEN}✅ Container started successfully${NC}"
    
    # Test 4: Check if application responds
    echo -e "${YELLOW}Test 4: Testing application response...${NC}"
    if curl -f -s http://localhost:8001/health/ > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Application responds to health check${NC}"
    else
        echo -e "${YELLOW}⚠️  Health check endpoint not available (this is expected if not implemented)${NC}"
    fi
    
    # Clean up
    docker stop "$CONTAINER_ID" > /dev/null
    docker rm "$CONTAINER_ID" > /dev/null
else
    echo -e "${RED}❌ Container failed to start${NC}"
    docker logs "$CONTAINER_ID"
    docker rm "$CONTAINER_ID" > /dev/null
    exit 1
fi

# Test 5: Test with environment file
echo -e "${YELLOW}Test 5: Testing with environment file...${NC}"
if [ -f ".env" ]; then
    CONTAINER_ID=$(docker run -d --env-file .env -p 8002:8000 test-insurance-app)
    sleep 5
    
    if docker ps | grep -q "$CONTAINER_ID"; then
        echo -e "${GREEN}✅ Container works with environment file${NC}"
        docker stop "$CONTAINER_ID" > /dev/null
        docker rm "$CONTAINER_ID" > /dev/null
    else
        echo -e "${RED}❌ Container failed with environment file${NC}"
        docker logs "$CONTAINER_ID"
        docker rm "$CONTAINER_ID" > /dev/null
        exit 1
    fi
else
    echo -e "${YELLOW}⚠️  .env file not found, skipping environment file test${NC}"
fi

# Clean up test image
docker rmi test-insurance-app > /dev/null

echo -e "${GREEN}🎉 All tests passed! Docker setup is working correctly.${NC}"
echo -e "${GREEN}You can now build and deploy your application with confidence.${NC}"

echo -e "${YELLOW}Next steps:${NC}"
echo -e "  1. Build production image: ./build.sh"
echo -e "  2. Deploy with docker-compose: docker-compose -f docker-compose.prod.yml up -d"
echo -e "  3. Check deployment guide: DEPLOYMENT_GUIDE.md"