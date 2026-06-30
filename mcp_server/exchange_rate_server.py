"""
MCP Server: Currency Exchange Rate Lookup
-----------------------------------------
Exposes a single tool: get_exchange_rate(from_currency, to_currency) -> float

Uses the free, no-key Frankfurter API (https://www.frankfurter.app/) to fetch
live exchange rates.  Runs over stdio so ADK's McpToolset can spawn it as a
subprocess.

IMPORTANT: When running under stdio transport, never write to stdout with
print() — it corrupts the JSON-RPC stream. Use sys.stderr for any debug logs.
"""

import sys
import httpx
from mcp.server.fastmcp import FastMCP

# Initialise the FastMCP server (name shown in tool listings)
mcp = FastMCP("exchange_rate_server")

FRANKFURTER_BASE = "https://api.frankfurter.app/latest"


@mcp.tool()
async def get_exchange_rate(from_currency: str, to_currency: str) -> str:
    """
    Fetch the latest exchange rate between two ISO 4217 currency codes.

    Args:
        from_currency: The source currency code (e.g. "EUR", "GBP", "JPY").
        to_currency:   The target currency code (e.g. "USD").

    Returns:
        A plain-text string with the rate, e.g. "1 EUR = 1.0823 USD", or an
        error message if the currency pair is unsupported or the API is
        unreachable.
    """
    from_currency = from_currency.strip().upper()
    to_currency = to_currency.strip().upper()

    if from_currency == to_currency:
        return f"1 {from_currency} = 1.0 {to_currency} (same currency, no conversion needed)"

    url = FRANKFURTER_BASE
    params = {"from": from_currency, "to": to_currency}

    print(f"[exchange_rate_server] Fetching rate {from_currency} -> {to_currency}", file=sys.stderr)

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(url, params=params)

        if response.status_code == 422:
            # Frankfurter returns 422 for unsupported currencies
            return (
                f"ERROR: Unsupported currency pair '{from_currency}' -> '{to_currency}'. "
                "Please use a valid ISO 4217 currency code (e.g. USD, EUR, GBP, JPY, CHF)."
            )

        response.raise_for_status()
        data = response.json()

        rates = data.get("rates", {})
        if to_currency not in rates:
            return (
                f"ERROR: Target currency '{to_currency}' not found in Frankfurter response. "
                f"Available currencies for {from_currency}: {list(rates.keys())}"
            )

        rate = rates[to_currency]
        print(f"[exchange_rate_server] Rate: 1 {from_currency} = {rate} {to_currency}", file=sys.stderr)
        return f"1 {from_currency} = {rate} {to_currency}"

    except httpx.TimeoutException:
        return "ERROR: Request to Frankfurter API timed out. Please try again later."
    except httpx.HTTPStatusError as exc:
        return f"ERROR: Frankfurter API returned HTTP {exc.response.status_code}: {exc.response.text}"
    except Exception as exc:
        return f"ERROR: Unexpected error fetching exchange rate: {exc}"


if __name__ == "__main__":
    # Run with stdio transport (default for subprocess-based MCP clients)
    mcp.run(transport="stdio")
