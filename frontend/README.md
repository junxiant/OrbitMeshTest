# OrbitMesh Frontend

React-based chatbot web interface for the OrbitMesh Support Assistant. Built with React and Vite.

---

## 1. Running Locally

### Prerequisites
- Node.js 18+ and npm installed

### Start the Development Server
Run the provided startup script:
```bash
./start.sh
```
Or manually run:
```bash
npm install
npm run dev
```
The application will be accessible at: `http://localhost:5173`.

### Environment Configuration
Create a `.env` or `.env.local` file inside `frontend/` if connecting to a remote backend:
```bash
VITE_API_URL=http://localhost:8000
```
If `VITE_API_URL` is omitted in local development, Vite proxies `/api` requests to `http://127.0.0.1:8000`.

---

## 2. Docker Containerization

To build and run the frontend inside a local Docker container:

### Build Container
```bash
docker build -t orbitmesh-frontend .
```

### Run Container
```bash
docker run -d -p 80:80 --name orbitmesh-frontend orbitmesh-frontend
```
Access at: `http://localhost:80`.

---

## 3. Pushing to Amazon ECR

Use the included push script to build and publish the image to Amazon ECR:

```bash
# Optional environment variables (or rely on defaults):
export AWS_REGION=ap-southeast-1
export AWS_ACCOUNT_ID=123456789012
export ECR_REPO_NAME=orbitmesh-frontend
export IMAGE_TAG=latest

./push_ecr.sh
```

The script will:
1. Validate AWS CLI and Docker installation.
2. Authenticate Docker with Amazon ECR.
3. Automatically create the ECR repository if it does not exist.
4. Build the image via `Dockerfile`.
5. Tag and push the image to ECR.

---

## 4. Deploying to AWS Amplify Hosting

AWS Amplify is the recommended hosting platform for React single-page applications because it provides global CloudFront CDN distribution, automatic SSL, continuous deployment from Git, and zero server maintenance.

### Step 1: Connect Git Repository in AWS Amplify Console
1. Open the **AWS Management Console** and navigate to **AWS Amplify**.
2. Click **Host web app**.
3. Select your Git provider (GitHub, GitLab, Bitbucket, or AWS CodeCommit) and authenticate.
4. Select the repository and the deployment branch (e.g., `main` or `frontend` or `dev` or `production`).

### Step 2: Configure Build Settings
Amplify automatically detects Vite/React. Use the following build settings (or place an `amplify.yml` file in the root):

```yaml
version: 1
frontend:
  phases:
    preBuild:
      commands:
        - cd frontend
        - npm ci
    build:
      commands:
        - npm run build
  artifacts:
    baseDirectory: frontend/dist
    files:
      - '**/*'
  cache:
    paths:
      - frontend/node_modules/**/*
```

### Step 3: Configure Environment Variables in Amplify
In the Amplify console, navigate to **App settings > Environment variables** and add:
- `VITE_API_URL`: The URL of your backend API (e.g., `https://api.orbitmesh.yourdomain.com` or your ALB DNS name).
- `VITE_API_KEY`: (Optional) The API key matching `API_KEY` on your backend service if API key verification is enabled.

### Step 4: Configure Single Page App (SPA) Rewrites
To ensure deep links and browser refreshes work properly:
1. In Amplify Console, navigate to **App settings > Rewrites and redirects**.
2. Add a rule:
   - Source address: `</^[^.]+$|\.(?!(css|gif|ico|jpg|js|png|txt|svg|woff|woff2|ttf|map|json)$)([^.]+$)/>`
   - Target address: `/index.html`
   - Type: `200 (Rewrite)`

### Step 5: Save and Deploy
Click **Save and deploy**. Amplify will build the React application and distribute it across the global AWS edge network.
