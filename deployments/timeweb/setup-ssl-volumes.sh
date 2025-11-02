#!/bin/bash

# SSL Certificate Volume Setup Script for Timeweb Deployment
# This script prepares the host system for SSL certificate management

set -e

# Configuration
SSL_BASE_DIR="/opt/insflow-system"
SSL_CERTS_DIR="${SSL_BASE_DIR}/letsencrypt"
ACME_CHALLENGE_DIR="${SSL_BASE_DIR}/acme-challenge"
DOCKER_USER_ID=${DOCKER_USER_ID:-1000}
DOCKER_GROUP_ID=${DOCKER_GROUP_ID:-1000}

echo "Setting up SSL certificate volumes for Timeweb deployment..."

# Create directories
echo "Creating SSL certificate directories..."
sudo mkdir -p "${SSL_CERTS_DIR}"
sudo mkdir -p "${ACME_CHALLENGE_DIR}"

# Set proper permissions
echo "Setting permissions for Docker access..."
sudo chown -R "${DOCKER_USER_ID}:${DOCKER_GROUP_ID}" "${SSL_BASE_DIR}"
sudo chmod -R 755 "${SSL_BASE_DIR}"

# Create .env configuration for bind mounts
echo "Creating bind mount configuration..."
cat > .env.bind-mounts << EOF
# SSL Volume Configuration for Bind Mounts
SSL_VOLUME_TYPE=bind
SSL_CERTIFICATES_PATH=${SSL_CERTS_DIR}
ACME_VOLUME_TYPE=bind
ACME_CHALLENGE_PATH=${ACME_CHALLENGE_DIR}
EOF

echo "SSL certificate volumes setup completed!"
echo ""
echo "Directories created:"
echo "  - SSL Certificates: ${SSL_CERTS_DIR}"
echo "  - ACME Challenge: ${ACME_CHALLENGE_DIR}"
echo ""
echo "To use bind mounts, add the following to your .env file:"
echo "  SSL_VOLUME_TYPE=bind"
echo "  SSL_CERTIFICATES_PATH=${SSL_CERTS_DIR}"
echo "  ACME_VOLUME_TYPE=bind"
echo "  ACME_CHALLENGE_PATH=${ACME_CHALLENGE_DIR}"
echo ""
echo "Or source the generated configuration:"
echo "  cat .env.bind-mounts >> .env"