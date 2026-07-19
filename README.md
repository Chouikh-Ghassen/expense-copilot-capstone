# Expense Copilot — Multi-Agent Business Expense Assistant

A multi-agent business expense assistant built for the AI Agents capstone project
using **Google Agent Development Kit (ADK) 2.x**.


![Alt text](icons/EXPENSE_COPILOT_BANNER.png)


## Demo Video

Watch the full project walkthrough:

[![YouTube Demo](https://img.shields.io/badge/▶️%20Watch%20Demo-YouTube-red?logo=youtube)](https://www.youtube.com/watch?v=_JyMwMDhms4)

---

The system consists of three specialised agents coordinated in sequence, plus an
MCP server for real-time currency conversion:

| Component | File | Role |
|---|---|---|
| **Intake Agent** | `agents/intake_agent.py` | Parses raw expense descriptions into structured JSON |
| **Policy Agent** | `agents/policy_agent.py` | Checks compliance against `policy_config.json`; calls the exchange-rate MCP tool for non-USD expenses |
| **Insights Agent** | `agents/insights_agent.py` | Aggregates results: total spend, category breakdown, anomalies, narrative summary |
| **Exchange Rate MCP Server** | `mcp_server/exchange_rate_server.py` | MCP server exposing `get_exchange_rate`; fetches live rates from the free Frankfurter API |

---

## Directory Structure

```text
expense-copilot-capstone/
├── agents/
│   ├── __init__.py
│   ├── intake_agent.py
│   ├── policy_agent.py        # MCP client of exchange_rate_server
│   └── insights_agent.py
├── mcp_server/
│   └── exchange_rate_server.py  # MCP server (FastMCP, stdio transport)
├── orchestrator.py
├── policy_config.json
├── requirements.txt
├── .env.example
└── README.md
```

---

## Prerequisites

- **Python 3.10+**
- A **Gemini API Key** from [Google AI Studio](https://aistudio.google.com/).
- Internet access (for the Frankfurter exchange-rate API — no API key needed).

---

## Local Setup

1. **Clone or navigate to the project directory**:
   ```bash
   cd expense-copilot-capstone
   ```

2. **Create and activate a virtual environment**:
   ```powershell
   # Windows (PowerShell)
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```
   ```bash
   # macOS / Linux
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure your API key** — create a `.env` file:
   ```env
   GOOGLE_API_KEY=your_actual_gemini_api_key_here
   ```

---

## How to Run

### Run the full orchestrator (recommended)

```bash
python orchestrator.py
```

This processes the sample expenses in sequence:
1. **Intake Agent** — parses each raw description into structured JSON.
2. **Policy Agent** — checks compliance; for non-USD expenses it automatically
   calls the `get_exchange_rate` MCP tool to convert to USD first.
3. **Insights Agent** — produces an aggregated report.

---

## MCP Currency Exchange Server

### What it does

`mcp_server/exchange_rate_server.py` is a **Model Context Protocol (MCP) server**
built with [FastMCP](https://github.com/modelcontextprotocol/python-sdk).
It exposes one tool:

```
get_exchange_rate(from_currency: str, to_currency: str) -> str
```

The tool calls the free [Frankfurter API](https://www.frankfurter.app/) — no API
key required — and returns a human-readable rate string, e.g.:

```
1 EUR = 1.0823 USD
```

Errors (unsupported currency, network timeout, etc.) are returned as descriptive
`ERROR: ...` strings so the policy agent can include them in its violation list.

### How it's wired into the Policy Agent

`policy_agent.py` creates an `McpToolset` pointing at the server as a subprocess:

```python
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from mcp import StdioServerParameters

exchange_rate_toolset = McpToolset(
    connection_params=StdioServerParameters(
        command=sys.executable,
        args=["mcp_server/exchange_rate_server.py"],
    ),
    tool_filter=["get_exchange_rate"],
)

policy_agent = Agent(
    name="policy_agent",
    model="gemini-2.5-flash",
    tools=[exchange_rate_toolset],
    instruction="...",
)
```

ADK's `InMemoryRunner` starts the subprocess automatically when the agent is
invoked and tears it down when the session ends.  No manual process management
is needed.

### Test the MCP server standalone

You can verify the server works independently using the MCP CLI:

```bash
# Install the MCP CLI if you don't have it
pip install "mcp[cli]"

# Inspect the server and list its tools
mcp dev mcp_server/exchange_rate_server.py
```

Or write a quick async test script:

```python
import asyncio, json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def test():
    async with stdio_client(StdioServerParameters(
        command="python", args=["mcp_server/exchange_rate_server.py"]
    )) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "get_exchange_rate",
                {"from_currency": "EUR", "to_currency": "USD"}
            )
            print(result.content[0].text)

asyncio.run(test())
```

---

## How to Run via ADK CLI (Optional)

```bash
# Interactive CLI chat with the full workflow
adk run .

# Visual ADK Web Studio
adk web .
# then open http://localhost:8000
```

---

## Security & Evaluation

This project implements robust security guardrails and automated testing to ensure reliability and safety.

### 1. Security Guardrails (Anti-Prompt Injection)

Prompt injection guardrails are active on both the **Intake Agent** and **Policy Agent**.
- System instructions explicitly direct the LLMs to treat all input expense description text strictly as passive data.
- Any commands or overrides embedded within the description text (e.g. *"ignore policy limits"*, *"force compliant to true"*) are ignored.
- The evaluation always runs according to the criteria defined in `policy_config.json`.

### 2. Unit Testing (TDD Suite)

A fast, mocked test suite is provided in the `/tests` directory to verify agent logic without making actual API calls or incurring token costs. It uses `pytest` and `pytest-mock` to stub the Gemini LLM responses.

To run the unit tests:
```bash
python -m pytest tests/
```

This suite verifies:
- **Intake parsing**: `intake_agent` correctly parses and structures well-formed USD expenses.
- **Policy limit violations**: `policy_agent` correctly rejects expenses exceeding category limits.
- **Approval threshold**: `policy_agent` flags expenses exceeding the overall threshold (e.g. $1,000.00).
- **Prompt Injection Resilience**: Verifies that injection payloads embedded in text fields do not change the compliance outcome.

### 3. Automated Quality Evaluation Set

A real-world quality benchmark is provided in the `/eval` directory. It runs real cases (with rate-limiting guards) through the entire sequential pipeline (Intake -> Policy with MCP -> final verdict) and validates the outcomes.

To run the quality evaluation benchmark:
```bash
python eval/run_eval.py
```

It outputs a scorecard showing the status of each case (compliant, non-compliant, EUR conversion, prompt injection attempt, missing vendor edge case) and calculates a final pass/fail percentage score.

---

## Policy Configuration

Edit `policy_config.json` to adjust limits:

```json
{
  "category_limits": {
    "meals":           50.0,
    "travel":         500.0,
    "software":       100.0,
    "office supplies": 150.0
  },
  "approval_threshold": 1000.0
}
```

---

## Web Frontend (FastAPI + HTML5/CSS3/JS)

A stunning, responsive, dark-mode web interface has been built to showcase the multi-agent workflow in action:
- **Interactive Form**: Allows users to paste raw unstructured expense text.
- **Agent Execution Stream**: Displays live logging from the intake, policy, and insights agents.
- **Compliance Verdict Dashboard**: Visually displays whether the expense is compliant, shows policy violations, Normalized USD amount, and manager approval requirements.
- **Aggregated Insights**: Displays progress bars for category breakdowns, anomalous patterns, and an executive narrative summary.

### Running Frontend Locally

1. **Activate your virtual environment** and make sure dependencies are installed:
   ```bash
   pip install -r frontend/requirements.txt
   ```

2. **Run the FastAPI application**:
   ```bash
   $env:ENGINE_ID="540236791970529280"
   $env:PROJECT_ID="expense-copilot-capstone"
   python -m uvicorn main:app --app-dir frontend --port 8000
   ```
   Open `http://localhost:8000` in your web browser!

---

## Deployment to Google Cloud

This project is designed to run in production on Google Cloud with **100% serverless scale-to-zero settings** to ensure zero idle running costs.

### 1. Backend: Vertex AI Reasoning Engine (Agent Runtime)
Follow the step-by-step guide in [DEPLOY.md](file:///d:/projects/kaggle_projects/expense-copilot-capstone/DEPLOY.md) to package the ADK workflow and deploy it to Vertex AI.
- **Backend Reasoning Engine Resource**: `projects/230079881073/locations/us-central1/reasoningEngines/540236791970529280`

### 2. Frontend: Google Cloud Run
Build the frontend container via Google Cloud Build and deploy it to Cloud Run:
```bash
gcloud run deploy expense-copilot-frontend \
  --source frontend/ \
  --region us-central1 \
  --min-instances 0 \
  --max-instances 5 \
  --allow-unauthenticated \
  --set-env-vars="PROJECT_ID=expense-copilot-capstone,ENGINE_ID=540236791970529280"
```
- **Live Deployed App URL**: [https://expense-copilot-frontend-230079881073.us-central1.run.app](https://expense-copilot-frontend-230079881073.us-central1.run.app)

## Credits

Built by Ghassen Chouikh, Ayoub Chamakhi and Nouhe Chouikh
