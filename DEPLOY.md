# Deployment Guide — Expense Copilot to Agent Runtime

This guide provides step-by-step instructions to deploy the **Expense Copilot** multi-agent backend to **Google Cloud Agent Runtime** (Vertex AI Reasoning Engine) using the ADK CLI.

---

## Prerequisites

1. **Google Cloud SDK (`gcloud`)**: Install it and ensure it is in your system PATH.
2. **Billing Enabled**: Ensure your GCP project has billing enabled (the free tier/trial credits will cover this run).
3. **Authentication**:
   Authenticate with your Google Cloud account:
   ```bash
   gcloud auth login
   gcloud auth application-default login
   ```
4. **Project Settings**:
   Set your target GCP project ID:
   ```bash
   gcloud config set project YOUR_PROJECT_ID
   ```
5. **Enable Services**:
   Enable Vertex AI and Secret Manager APIs:
   ```bash
   gcloud services enable aiplatform.googleapis.com secretmanager.googleapis.com
   ```
6. **Required Packages**:
   Ensure `google-cloud-aiplatform` is installed in your python environment (it is included in `requirements.txt`):
   ```bash
   pip install google-cloud-aiplatform
   ```

---

## IMPORTANT: Folder Naming & Entrypoint Constraints

1. **Folder Naming**: The ADK CLI requires the name of the folder being deployed to be a **valid Python identifier** (containing letters, digits, and underscores only — no dashes). Since the root workspace directory name `expense-copilot-capstone` contains dashes, the deployment has been set up inside a clean subdirectory named **`expense_copilot`**.
2. **Auto-Discovery**: We have created an `__init__.py` inside `expense_copilot` that exports `root_agent = workflow` to allow the ADK runner to automatically resolve the agent workflow under `expense_copilot.root_agent`.

You must run all deployment and execution commands from within the `expense_copilot` directory.

---

## 1. Store the Gemini API Key in Secret Manager

Since the agent runs securely in the cloud, you must store your Gemini API key in Google Cloud Secret Manager so the Reasoning Engine can access it securely.

Run the following commands to create the secret and add your API key:

```bash
# 1. Create the secret metadata
gcloud secrets create gemini-api-key --replication-policy="automatic"

# 2. Add the API key value (replace YOUR_API_KEY with your actual Gemini API key)
echo -n "YOUR_API_KEY" | gcloud secrets versions add gemini-api-key --data-file=-
```

Note the resource ID of the created secret version. It will look like:
`projects/YOUR_PROJECT_NUMBER/secrets/gemini-api-key/versions/1`

---

## 2. Deploy the Backend to Agent Runtime (Reasoning Engine)

Switch to the `expense_copilot` folder and deploy:

```bash
# 1. Change directory to the dash-free folder
cd expense_copilot

# 2. Deploy to Agent Runtime
..\.venv\Scripts\adk.exe deploy agent_engine . \
  --project YOUR_PROJECT_ID \
  --region us-central1 \
  --entrypoint orchestrator:root_agent \
  --api-key-secret-version projects/YOUR_PROJECT_NUMBER/secrets/gemini-api-key/versions/1 \
  --display-name "expense-copilot" \
  --description "Multi-agent business expense intake and compliance evaluation workflow"
```

Once the command finishes, it will print the `ReasoningEngine` resource ID (e.g. `projects/YOUR_PROJECT_ID/locations/us-central1/reasoningEngines/YOUR_ENGINE_ID`). It also generates a `deployment_metadata.json` file in the `expense_copilot` folder with this information.

---

## 3. Local Verification of Deployed Agent

You can test the deployed agent by sending a REST API request (or via the Google Cloud Console playground link printed during deployment).

To test programmatically using python, you can invoke the Reasoning Engine's streaming query endpoint. Here is a sample execution snippet:

```python
import google.auth
import google.auth.transport.requests
import httpx

# 1. Get credentials and token
credentials, project = google.auth.default()
auth_request = google.auth.transport.requests.Request()
credentials.refresh(auth_request)
token = credentials.token

# 2. Define endpoint (replace YOUR_PROJECT_ID and YOUR_ENGINE_ID)
url = 'https://us-central1-aiplatform.googleapis.com/v1beta1/projects/YOUR_PROJECT_ID/locations/us-central1/reasoningEngines/YOUR_ENGINE_ID:streamQuery'
headers = {
    'Authorization': f'Bearer {token}',
    'Content-Type': 'application/json'
}

# 3. Request payload
payload = {
    'classMethod': 'stream_query',
    'input': {
        'message': 'I spent $45.50 on client lunch at Subway on 2026-06-25. Employee: Alice.',
        'user_id': 'test_user'
    }
}

# 4. Stream response
with httpx.stream('POST', url, headers=headers, json=payload, timeout=60.0) as r:
    if r.status_code == 200:
        for line in r.iter_lines():
            if line:
                print(line)
    else:
        print('Error:', r.status_code, r.read().decode('utf-8'))
```

---

## 4. Frontend Deployment Note (Next Step)

The frontend service will be deployed to **Cloud Run** and will consume this Reasoning Engine endpoint. 
To ensure zero costs when idle, the Cloud Run deployment will explicitly enforce a scale-to-zero policy:
```bash
gcloud run deploy expense-copilot-frontend \
  --source . \
  --min-instances 0 \
  --max-instances 5 \
  --region us-central1 \
  --allow-unauthenticated
```
*(This command will be detailed in the Frontend deployment guide once the UI code is generated).*
