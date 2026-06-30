import asyncio
import os
import json
import re
from dotenv import load_dotenv

load_dotenv()

if "GOOGLE_API_KEY" not in os.environ and "GEMINI_API_KEY" in os.environ:
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]

from google.adk.runners import InMemoryRunner
from google.adk import Workflow

# Import agents
try:
    from agents.intake_agent import intake_agent
    from agents.policy_agent import policy_agent
    from agents.insights_agent import insights_agent
except (ImportError, ModuleNotFoundError):
    from .agents.intake_agent import intake_agent
    from .agents.policy_agent import policy_agent
    from .agents.insights_agent import insights_agent

# Define the Workflow definition for ADK CLI/Web discovery
root_agent = Workflow(
    name="expense_copilot_workflow",
    edges=[
        ("START", intake_agent),
        (intake_agent, policy_agent),
        (policy_agent, insights_agent),
    ]
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_json_fences(text: str) -> str:
    """Remove markdown code fences some models add despite instructions."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE)
    return text.strip()


_RETRYABLE_STATUS = {429, 503}
_MAX_RETRIES = 4


async def execute_agent(agent, input_message: str, delay_seconds: int = 12) -> str:
    """
    Runs a single ADK agent via InMemoryRunner and returns its text output.

    A delay is applied before each call to respect the Gemini Free Tier 5 RPM
    limit.  Transient 429 / 503 errors are retried with exponential backoff
    (up to _MAX_RETRIES attempts).
    """
    from google.genai.types import Content, Part
    from google.genai.errors import ServerError, ClientError
    from google.adk.models.google_llm import _ResourceExhaustedError

    print(f"  [{agent.name}] Waiting {delay_seconds}s (rate-limit guard)...")
    await asyncio.sleep(delay_seconds)

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            runner = InMemoryRunner(agent=agent, app_name="expense_copilot")
            session = await runner.session_service.create_session(
                app_name="expense_copilot",
                user_id="orchestrator_user",
            )

            content = Content(role="user", parts=[Part.from_text(text=input_message)])

            output_parts: list[str] = []
            async for event in runner.run_async(
                user_id="orchestrator_user",
                session_id=session.id,
                new_message=content,
            ):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if hasattr(part, "text") and part.text:
                            output_parts.append(part.text)

            raw = "".join(output_parts).strip()
            return _strip_json_fences(raw)

        except (ServerError, ClientError, _ResourceExhaustedError) as exc:
            status = getattr(exc, "status_code", None) or getattr(exc, "code", None) or 429
            if isinstance(exc, _ResourceExhaustedError):
                status = 429
            if status in _RETRYABLE_STATUS and attempt < _MAX_RETRIES:
                # Parse the API-recommended retry delay if present ("retry in Xs")
                import re as _re
                hint = _re.search(r"retry in ([\d.]+)s", str(exc), _re.IGNORECASE)
                api_wait = int(float(hint.group(1))) + 5 if hint else 0
                floor = 45 * (2 ** (attempt - 1))   # 45s, 90s, 180s
                wait = max(api_wait, floor)
                print(f"  [{agent.name}] Transient {status} (attempt {attempt}/{_MAX_RETRIES}). "
                      f"Retrying in {wait}s...")
                await asyncio.sleep(wait)
            else:
                raise


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def run_orchestrator(raw_descriptions: list[str]):
    """
    Runs the full Expense Copilot pipeline:
      1. intake_agent  — parse raw description -> structured JSON
      2. policy_agent  — check compliance (with MCP currency conversion)
      3. insights_agent — aggregate all results into a summary report
    """
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  Expense Copilot  |  {len(raw_descriptions)} expense(s)")
    print(f"{sep}\n")

    processed_expenses: list[dict] = []

    for i, desc in enumerate(raw_descriptions, 1):
        print(f"-- Expense {i}/{len(raw_descriptions)} " + "-" * 44)
        print(f"  Raw: {desc}")

        # Step 1: Intake — parse raw text into structured JSON
        print("\n  [Step 1] Parsing with intake_agent...")
        intake_raw = await execute_agent(intake_agent, desc)
        print(f"  Parsed JSON:\n  {intake_raw}")

        try:
            expense_json = json.loads(intake_raw)
        except json.JSONDecodeError:
            print("  WARNING: Could not parse intake output as JSON. Storing raw.")
            expense_json = {"raw_description": desc, "parse_error": intake_raw}

        # Step 2: Policy check — policy_agent calls MCP get_exchange_rate if needed
        print("\n  [Step 2] Checking policy compliance with policy_agent...")
        print("          (If non-USD, agent will call MCP get_exchange_rate tool)")
        policy_raw = await execute_agent(policy_agent, json.dumps(expense_json))
        print(f"  Policy JSON:\n  {policy_raw}")

        try:
            policy_json = json.loads(policy_raw)
        except json.JSONDecodeError:
            policy_json = {"error": policy_raw}

        processed_expenses.append({
            "expense": expense_json,
            "policy_check": policy_json,
        })

    # Step 3: Insights — aggregate all processed expenses
    print("\n-- Generating Insights Report " + "-" * 30)
    print("  [Step 3] Aggregating results with insights_agent...")
    aggregated_input = json.dumps(processed_expenses, indent=2)
    insights_raw = await execute_agent(insights_agent, aggregated_input)

    print(f"\n{sep}")
    print("  FINAL INSIGHTS REPORT")
    print(f"{sep}")
    try:
        report = json.loads(insights_raw)
        print(json.dumps(report, indent=2))
    except json.JSONDecodeError:
        print(insights_raw)

    return processed_expenses, insights_raw


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # 3 expenses -> 7 agent calls total (3x intake + 3x policy + 1x insights).
    # With 12-second delays that's ~84 seconds of pure wait time, well within
    # the Gemini free-tier 5 RPM window.
    # Expense 3 (EUR) demonstrates the MCP currency-conversion flow.
    sample_expenses = [
        "I spent $45.50 on client lunch at Subway on 2026-06-25. Employee: Alice.",
        "Executive business dinner at high-end restaurant costing $1200.00 on 2026-06-28 by Diana.",
        "Client dinner in Paris, 85 EUR, at Le Comptoir du Relais on 2026-06-20 by Marc.",
    ]

    asyncio.run(run_orchestrator(sample_expenses))
