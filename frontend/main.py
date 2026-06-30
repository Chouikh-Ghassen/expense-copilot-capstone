import os
import json
import logging
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import httpx
import google.auth
import google.auth.transport.requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("expense_copilot_frontend")

app = FastAPI(title="Expense Copilot Frontend")

# Serve static files (HTML, CSS, JS) from static directory
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_index():
    index_path = os.path.join(static_dir, "index.html")
    if not os.path.exists(index_path):
        return HTMLResponse("<h1>Frontend is initializing...</h1>", status_code=503)
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.post("/api/evaluate")
async def evaluate_expense(data: dict):
    message = data.get("message")
    if not message:
        raise HTTPException(status_code=400, detail="Missing message parameter")
    
    # 1. Fetch GCP Credentials
    try:
        credentials, project = google.auth.default()
        auth_request = google.auth.transport.requests.Request()
        credentials.refresh(auth_request)
        token = credentials.token
    except Exception as e:
        logger.error(f"Failed to get GCP credentials: {e}")
        raise HTTPException(status_code=500, detail=f"Authentication error: {e}")

    # 2. Get configuration
    project_id = os.environ.get("PROJECT_ID", project)
    engine_id = os.environ.get("ENGINE_ID", "540236791970529280")
    region = os.environ.get("REGION", "us-central1")
    
    if not project_id:
         raise HTTPException(status_code=500, detail="GCP Project ID not configured.")
         
    # 3. Setup Vertex AI REST details
    url = f"https://{region}-aiplatform.googleapis.com/v1beta1/projects/{project_id}/locations/{region}/reasoningEngines/{engine_id}:streamQuery"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "classMethod": "stream_query",
        "input": {
            "message": message,
            "user_id": "web_user"
        }
    }

    # 4. Stream response to client
    async def event_generator():
        timeout = httpx.Timeout(120.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    if response.status_code != 200:
                        err_content = await response.aread()
                        logger.error(f"Backend API error {response.status_code}: {err_content.decode('utf-8')}")
                        yield f"data: {json.dumps({'error_code': 'BackendError', 'error_message': f'Server returned {response.status_code}'})}\n\n"
                        return
                    
                    async for line in response.aiter_lines():
                        if line:
                            # Stream raw JSON lines to frontend as Server-Sent Events
                            yield f"data: {line}\n\n"
            except Exception as e:
                logger.error(f"Stream generation error: {e}")
                yield f"data: {json.dumps({'error_code': 'ConnectionError', 'error_message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
