# Deployment Structure

This directory contains organized deployment configurations for different hosting providers.

## Directory Structure

```
deployments/
├── digital-ocean/          # Digital Ocean HTTP deployment
│   ├── docker-compose.yml  # Docker Compose for Digital Ocean
│   └── nginx/              # Nginx configuration for HTTP
├── timeweb/               # Timeweb HTTPS deployment
│   ├── docker-compose.yml  # Docker Compose for Timeweb
│   └── nginx/              # Nginx configurations for HTTPS
└── README.md              # This file

shared/                    # Shared configurations
├── env-templates/         # Environment variable templates
│   ├── digital-ocean.env.example
│   └── timeweb.env.example
└── django/               # Shared Django configurations
```

## Usage

### Digital Ocean Deployment (HTTP)
```bash
cd deployments/digital-ocean
cp ../../shared/env-templates/digital-ocean.env.example .env
# Edit .env with your configuration
docker-compose up -d
```

### Timeweb Deployment (HTTPS)
```bash
cd deployments/timeweb
cp ../../shared/env-templates/timeweb.env.example .env
# Edit .env with your configuration
docker-compose up -d
```

## Migration from Old Structure

The old deployment files have been organized as follows:

- `docker-compose.yml` → `deployments/digital-ocean/docker-compose.yml`
- `docker-compose.timeweb.yml` → `deployments/timeweb/docker-compose.yml`
- `nginx/` → `deployments/digital-ocean/nginx/`
- `nginx-timeweb/` → `deployments/timeweb/nginx/`
- `.env.example` → `shared/env-templates/digital-ocean.env.example`
- `.env.timeweb.example` → `shared/env-templates/timeweb.env.example`

## Requirements Satisfied

This structure satisfies the following requirements:
- **3.1**: Clear separation between Digital Ocean and Timeweb deployment configurations
- **3.2**: Changes to one deployment don't impact the other
- **3.1**: Separate configuration directories for each hosting provider
- **3.2**: Shared configurations for common elements