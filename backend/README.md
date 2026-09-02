# OrbitMesh Backend Service

FastAPI backend service powering the OrbitMesh diagnostic orchestrator, session state management, and RAG retrieval.

---

## 1. Quick Start (Running Locally)

### Prerequisites
- Python 3.11
- Docker and Docker Compose (for PostgreSQL and Qdrant)

### Start Full Backend Services (All-in-One)
To launch PostgreSQL, Qdrant, and the FastAPI application server together:
```bash
./start_all.sh
```

### Start Services Individually
You can also launch each service in its own terminal or script:

1. **Start PostgreSQL Database**:
   ```bash
   ./start_postgres.sh
   ```
   Runs on `localhost:5432` (Database: `orbitmesh`, User: `orbitmesh`, Password: `orbitmesh`).

2. **Start Qdrant Vector Server**:
   ```bash
   ./start_qdrant.sh
   ```
   Runs on `http://localhost:6333` (gRPC: `6334`).

3. **Start FastAPI Application Server**:
   ```bash
   ./start.sh
   # or: ./start_api.sh
   ```
   Runs on `http://localhost:8000`. Interactive OpenAPI documentation is available at `http://localhost:8000/docs`.

---

### Web Dashboards & Database GUIs
When Docker Compose is running (`docker compose up -d` or `./start_all.sh`), the following web dashboards are available:

1. **Qdrant Vector Web Dashboard**:
   - **URL**: `http://localhost:6333/dashboard`
   - **Features**: Visual collection explorer for `orbitmesh_docs`, search and inspect chunk vector points, check payload metadata, and view real-time vector database metrics.

2. **PostgreSQL Web Interface (Adminer)**:
   - **URL**: `http://localhost:8080`
   - **System**: Select `PostgreSQL`
   - **Server**: `postgres` (or `localhost` if using an external tool)
   - **Username**: `orbitmesh`
   - **Password**: `orbitmesh`
   - **Database**: `orbitmesh`
   - **Features**: Browser-based database management interface to inspect the `sessions` table, view conversation memory records, run SQL queries, and monitor session rows.

3. **FastAPI OpenAPI / Swagger Documentation**:
   - **URL**: `http://localhost:8000/docs` (or Redoc at `http://localhost:8000/redoc`)
   - **Features**: Interactive API explorer to execute test requests against `/api/chat` and `/api/health`.

---

## 2. API Endpoints

### Health Check
- **Endpoint**: `GET /api/health`
- **Response**:
  ```json
  {
    "status": "ok",
    "service": "orbitmesh-backend",
    "version": "1.0.0"
  }
  ```

### Chat Turn
- **Endpoint**: `POST /api/chat`
- **Headers**:
  - `Content-Type: application/json`
  - `X-API-Key: <API_KEY>` (Optional by default; enforced if `REQUIRE_API_KEY=true`)
- **Request Body**:
  ```json
  {
    "session_id": "session-1",
    "message": "My N1 satellite node has a solid amber light"
  }
  ```
- **Response Body**:
  ```json
  {
    "session_id": "session-1",
    "response": "A solid amber LED on your satellite N1 node indicates it is offline or out of range. Please move the N1 node closer to the main router.",
    "citations": [
      {
        "source_id": "led-reference",
        "locator": "N1 node LEDs"
      }
    ],
    "action": "instruct"
  }
  ```

---

## 3. Environment Configuration (`.env`)

Configure the following environment variables in the project root `.env`:

```bash
# LLM Configuration
LLM_MODE=openrouter
OPENROUTER_API_KEY=your_openrouter_api_key
OPENROUTER_MODEL=nvidia/nemotron-3.5-lightning:free
LLM_RATE_LIMIT_DELAY=1.0

# Vector Database (Qdrant Server)
QDRANT_URL=http://localhost:6333
QDRANT_PATH=data/qdrant

# Database (PostgreSQL)
DB_BACKEND=postgres
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=orbitmesh
POSTGRES_USER=orbitmesh
POSTGRES_PASSWORD=orbitmesh
DATABASE_URL=postgresql://orbitmesh:orbitmesh@localhost:5432/orbitmesh

# SQLite Fallback Path
SQLITE_DB_PATH=data/sessions.db

# API Authentication (Optional for demo, set to true to enforce)
API_KEY=orbitmesh-secret-key
REQUIRE_API_KEY=false
```

---

## 4. Docker Containerization & Amazon ECR

### Build and Test Container Locally
```bash
# Run from project root
docker build -f backend/Dockerfile -t orbitmesh-backend .
docker run -d -p 8000:8000 --env-file .env orbitmesh-backend
```

### Push to Amazon ECR
Run the push script to build and upload the backend container image to ECR:
```bash
export AWS_REGION=ap-southeast-1
export AWS_ACCOUNT_ID=123456789012
export ECR_REPO_NAME=orbitmesh-backend
export IMAGE_TAG=latest

./push_ecr.sh
```

---

## 5. Setting up PostgreSQL on AWS (Amazon RDS)

Amazon RDS is recommended for production relational storage:

### Step 1: Create RDS Security Group
1. In the AWS VPC Console, create security group `orbitmesh-rds-sg`.
2. Add an inbound rule:
   - Type: PostgreSQL (port 5432)
   - Source: Security group of the ECS Backend service (`orbitmesh-backend-sg`).

### Step 2: Create RDS PostgreSQL Instance
1. In the Amazon RDS console, select **Create database**.
2. Engine: PostgreSQL 16 (or later).
3. DB instance identifier: `orbitmesh-postgres`.
4. Master username: `orbitmesh`.
5. Master password: `<SECURE_PASSWORD>`.
6. Initial database name: `orbitmesh`.
7. VPC: Place in private subnets with `orbitmesh-rds-sg` attached.
8. Public access: No.
9. Note the RDS endpoint (e.g., `orbitmesh-postgres.xxxxxx.ap-southeast-1.rds.amazonaws.com`).

The session tables are initialized automatically by the backend upon first connection.

---

## 6. Setting up Server Qdrant on AWS (ECS Fargate + Amazon EFS)

Running Qdrant on ECS Fargate with Amazon EFS provides a serverless containerized vector database with persistent vector storage.

### Step 1: Create Amazon EFS File System
1. Open Amazon EFS Console and click **Create file system**.
2. Name: `orbitmesh-qdrant-efs`.
3. VPC: Application VPC.
4. Mount targets: Configure in each private subnet using security group `orbitmesh-efs-sg` (allows inbound port 2049 from `orbitmesh-qdrant-sg`).
5. Create an **Access Point**:
   - Path: `/qdrant/storage`
   - POSIX User: UID `1000`, GID `1000`
   - Permissions: `0755` with Owner UID `1000`, Owner GID `1000`
   - Record the Access Point ID (e.g., `fsap-0123456789abcdef0`).

### Step 2: Configure AWS Cloud Map Service Discovery
1. Create private DNS namespace `orbitmesh.local` in your VPC.
2. Create service discovery name `qdrant`.
3. This provides internal DNS: `http://qdrant.orbitmesh.local:6333`.

### Step 3: Register Qdrant ECS Task Definition
```json
{
  "family": "orbitmesh-qdrant-task",
  "requiresCompatibilities": ["FARGATE"],
  "networkMode": "awsvpc",
  "cpu": "1024",
  "memory": "2048",
  "executionRoleArn": "arn:aws:iam::<ACCOUNT_ID>:role/ecsTaskExecutionRole",
  "volumes": [
    {
      "name": "qdrant-efs-volume",
      "efsVolumeConfiguration": {
        "fileSystemId": "fs-0123456789abcdef0",
        "transitEncryption": "ENABLED",
        "authorizationConfig": {
          "accessPointId": "fsap-0123456789abcdef0"
        }
      }
    }
  ],
  "containerDefinitions": [
    {
      "name": "qdrant",
      "image": "qdrant/qdrant:v1.14.1",
      "essential": true,
      "portMappings": [
        { "containerPort": 6333, "hostPort": 6333, "protocol": "tcp" },
        { "containerPort": 6334, "hostPort": 6334, "protocol": "tcp" }
      ],
      "mountPoints": [
        {
          "sourceVolume": "qdrant-efs-volume",
          "containerPath": "/qdrant/storage"
        }
      ],
      "environment": [
        { "name": "QDRANT__TELEMETRY_DISABLED", "value": "true" }
      ]
    }
  ]
}
```

### Step 4: Run Qdrant Service
Create the ECS Service with desired count of `1` (single writer for file consistency):
```bash
aws ecs create-service \
  --cluster orbitmesh-cluster \
  --service-name orbitmesh-qdrant-service \
  --task-definition orbitmesh-qdrant-task \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[<PRIVATE_SUBNETS>],securityGroups=[<QDRANT_SG_ID>],assignPublicIp=DISABLED}" \
  --service-registries "registryArn=<CLOUD_MAP_ARN>"
```

---

## 7. Deploying Backend to AWS ECS Fargate

### Step 1: Create Application Load Balancer (ALB)
1. Create internet-facing ALB in public subnets: `orbitmesh-alb`.
2. Create Target Group:
   - Target type: IP
   - Protocol: HTTP, Port: 8000
   - Health check path: `/api/health`
3. Add HTTPS listener (port 443) forwarding to the Target Group.

### Step 2: Register Backend ECS Task Definition
```json
{
  "family": "orbitmesh-backend-task",
  "requiresCompatibilities": ["FARGATE"],
  "networkMode": "awsvpc",
  "cpu": "1024",
  "memory": "2048",
  "executionRoleArn": "arn:aws:iam::<ACCOUNT_ID>:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::<ACCOUNT_ID>:role/ecsTaskRole",
  "containerDefinitions": [
    {
      "name": "orbitmesh-backend",
      "image": "<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/orbitmesh-backend:latest",
      "essential": true,
      "portMappings": [
        { "containerPort": 8000, "hostPort": 8000, "protocol": "tcp" }
      ],
      "environment": [
        { "name": "LLM_MODE", "value": "openrouter" },
        { "name": "OPENROUTER_MODEL", "value": "nvidia/nemotron-3.5-lightning:free" },
        { "name": "DB_BACKEND", "value": "postgres" },
        { "name": "DATABASE_URL", "value": "postgresql://orbitmesh:<PASSWORD>@orbitmesh-postgres.xxxxxx.<REGION>.rds.amazonaws.com:5432/orbitmesh" },
        { "name": "QDRANT_URL", "value": "http://qdrant.orbitmesh.local:6333" },
        { "name": "API_KEY", "value": "<BACKEND_API_KEY>" }
      ],
      "secrets": [
        {
          "name": "OPENROUTER_API_KEY",
          "valueFrom": "arn:aws:secretsmanager:<REGION>:<ACCOUNT_ID>:secret:orbitmesh/openrouter_api_key"
        }
      ]
    }
  ]
}
```

### Step 3: Run Backend Service
```bash
aws ecs create-service \
  --cluster orbitmesh-cluster \
  --service-name orbitmesh-backend-service \
  --task-definition orbitmesh-backend-task \
  --desired-count 2 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[<PRIVATE_SUBNETS>],securityGroups=[<BACKEND_SG_ID>],assignPublicIp=DISABLED}" \
  --load-balancers "targetGroupArn=<ALB_TARGET_GROUP_ARN>,containerName=orbitmesh-backend,containerPort=8000"
```
