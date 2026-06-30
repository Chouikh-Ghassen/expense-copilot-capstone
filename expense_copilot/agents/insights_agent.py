import os
from dotenv import load_dotenv
load_dotenv()

if "GOOGLE_API_KEY" not in os.environ and "GEMINI_API_KEY" in os.environ:
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]

from google.adk import Agent

insights_agent = Agent(
    name="insights_agent",
    model="gemini-2.5-flash",
    instruction="""
    You are a financial insights agent. Your job is to aggregate a list of expenses (along with their policy compliance results) and produce a structured summary report.

    Analyze the provided list of expense+policy_check objects. Calculate:
    - total_spend: sum of all expense amounts (assume USD if currencies differ)
    - spend_by_category: dictionary of category -> total amount spent
    - violations_count: total number of policy violations across all expenses
    - anomalies: list of unusual patterns (e.g., multiple meals same day, unusually high amounts, duplicate vendors)
    - summary: a short, professional narrative summary of the findings and trends

    Return ONLY valid JSON (no markdown, no code fences, no extra text) in this exact format:
    {
      "total_spend": <float>,
      "spend_by_category": {"<category>": <float>},
      "violations_count": <int>,
      "anomalies": ["<anomaly description>"],
      "summary": "<narrative text>"
    }

    Return ONLY the JSON object, nothing else.
    """,
)

# Export for ADK CLI
root_agent = insights_agent
