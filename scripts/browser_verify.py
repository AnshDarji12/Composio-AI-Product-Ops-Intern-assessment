"""Web-fetch verification loop.

Fetches the real vendor docs pages for 10 sampled apps and checks
whether the agent's answers (auth, self_serve) are supported by the
actual page content. Saves results to data/audit/browser-verify-report.json

Usage:
    python scripts/browser_verify.py
"""
import json
import sys
import re
from datetime import datetime, timezone
from pathlib import Path

try:
    import httpx
except ImportError:
    print("httpx not installed. Run: pip install httpx")
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

BASE = Path(__file__).parent.parent
OUT  = BASE / "data" / "audit" / "browser-verify-report.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

SAMPLE = [
    {
        "id": 1, "app": "Salesforce",
        "url": "https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/quickstart_oauth.htm",
        "claim_field": "auth", "claim_value": ["OAuth2", "Bearer token"],
        "must_contain": ["oauth", "access token", "bearer"],
        "must_not_contain": [],
    },
    {
        "id": 4, "app": "Attio",
        "url": "https://developers.attio.com/docs/authentication",
        "claim_field": "auth", "claim_value": ["Bearer token"],
        "must_contain": ["bearer", "token"],
        "must_not_contain": [],
    },
    {
        "id": 11, "app": "Zendesk",
        "url": "https://developer.zendesk.com/api-reference/introduction/security-and-auth/",
        "claim_field": "auth", "claim_value": ["API key", "Basic", "OAuth2"],
        "must_contain": ["api token", "oauth", "basic"],
        "must_not_contain": [],
    },
    {
        "id": 13, "app": "Freshdesk",
        "url": "https://developers.freshdesk.com/api/#authentication",
        "claim_field": "auth", "claim_value": ["API key", "Basic"],
        "must_contain": ["api key", "basic"],
        "must_not_contain": [],
    },
    {
        "id": 21, "app": "Slack",
        "url": "https://api.slack.com/authentication/oauth-v2",
        "claim_field": "self_serve", "claim_value": "self-serve",
        "must_contain": ["oauth", "app"],
        "must_not_contain": ["contact sales", "enterprise only"],
    },
    {
        "id": 61, "app": "GitHub",
        "url": "https://docs.github.com/en/rest/authentication/authenticating-to-the-rest-api",
        "claim_field": "auth", "claim_value": ["Bearer token", "OAuth2"],
        "must_contain": ["personal access token", "oauth"],
        "must_not_contain": [],
    },
    {
        "id": 70, "app": "Sentry",
        "url": "https://docs.sentry.io/api/auth/",
        "claim_field": "auth", "claim_value": ["Bearer token"],
        "must_contain": ["auth token", "bearer"],
        "must_not_contain": [],
    },
    {
        "id": 81, "app": "Stripe",
        "url": "https://stripe.com/docs/api/authentication",
        "claim_field": "auth", "claim_value": ["API key"],
        "must_contain": ["api key", "secret key"],
        "must_not_contain": [],
    },
    {
        "id": 90, "app": "PitchBook",
        "url": "https://pitchbook.com/pitchbook-api",
        "claim_field": "self_serve", "claim_value": "partner-gated",
        "must_contain": ["contact", "enterprise"],
        "must_not_contain": ["free trial", "sign up for free"],
    },
    {
        "id": 22, "app": "Twilio",
        "url": "https://www.twilio.com/docs/usage/api/account",
        "claim_field": "auth", "claim_value": ["API key", "Basic"],
        "must_contain": ["account sid", "auth token"],
        "must_not_contain": [],
    },
]


def fetch_text(url: str, timeout: int = 15) -> tuple[int, str]:
    try:
        with httpx.Client(headers=HEADERS, timeout=timeout,
                          follow_redirects=True) as client:
            r = client.get(url)
            status = r.status_code
            if BeautifulSoup:
                soup = BeautifulSoup(r.text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer"]):
                    tag.decompose()
                text = soup.get_text(" ", strip=True).lower()
            else:
                text = re.sub(r"<[^>]+>", " ", r.text).lower()
            return status, text
    except Exception as e:
        return 0, str(e).lower()


def verify_one(item: dict) -> dict:
    status, text = fetch_text(item["url"])
    result = {
        "id": item["id"],
        "app": item["app"],
        "url": item["url"],
        "http_status": status,
        "claim_field": item["claim_field"],
        "claim_value": item["claim_value"],
        "verdict": "ERROR",
        "evidence_found": "",
        "notes": "",
    }

    if status == 0 or status >= 400:
        result["verdict"] = "ERROR"
        result["notes"] = f"HTTP {status} — could not fetch page"
        return result

    hits = [kw for kw in item["must_contain"] if kw in text]
    misses = [kw for kw in item["must_contain"] if kw not in text]
    bad_hits = [kw for kw in item["must_not_contain"] if kw in text]

    # Extract a short evidence snippet
    for kw in hits[:2]:
        idx = text.find(kw)
        if idx >= 0:
            snippet = text[max(0, idx-30):idx+80].strip()
            result["evidence_found"] += f'…{snippet}… '

    if misses and not hits:
        result["verdict"] = "FAIL"
        result["notes"] = f"Required keywords not found: {misses}"
    elif bad_hits:
        result["verdict"] = "FAIL"
        result["notes"] = f"Disqualifying keywords found: {bad_hits}"
    elif hits:
        result["verdict"] = "PASS"
        result["notes"] = f"Keywords confirmed on page: {hits}"
    else:
        result["verdict"] = "FAIL"
        result["notes"] = "No confirming keywords found on page"

    return result


def main():
    print(f"Web-fetch verification: {len(SAMPLE)} apps\n")
    results = []
    for item in SAMPLE:
        print(f"  Checking #{item['id']:3d} {item['app']:20s} ... ", end="", flush=True)
        r = verify_one(item)
        results.append(r)
        print(f"{r['verdict']}  (HTTP {r['http_status']})")

    passed = sum(1 for r in results if r["verdict"] == "PASS")
    failed = sum(1 for r in results if r["verdict"] == "FAIL")
    errors = sum(1 for r in results if r["verdict"] == "ERROR")
    accuracy = round(passed / max(passed + failed, 1), 3)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": "web-fetch verification: direct HTTP fetch of live docs pages + keyword matching",
        "total_checked": len(results),
        "passed": passed,
        "failed": failed,
        "error": errors,
        "accuracy": accuracy,
        "results": results,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2))
    print(f"\n✓  PASS={passed}  FAIL={failed}  ERROR={errors}  accuracy={accuracy:.1%}")
    print(f"   Report -> {OUT}")
    return report


if __name__ == "__main__":
    main()
