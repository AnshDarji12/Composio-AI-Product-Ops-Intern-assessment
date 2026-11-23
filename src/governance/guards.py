"""Security guards: SSRF, secret scanning, PII redaction, robots.txt.

Pure functions / small stateful helpers - no I/O except DNS resolution
and robots.txt fetches. The governance engine composes these into policy
decisions and audits every outcome.
"""
import ipaddress
import re
import socket
import urllib.robotparser
from urllib.parse import urlparse

# ── SSRF guard ────────────────────────────────────────────────────────


def _ip_is_forbidden(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True for loopback / private / link-local / reserved / multicast ranges.

    This is what stops a malicious docs page from redirecting the agent to
    http://169.254.169.254/ (cloud metadata) or internal services.
    """
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def resolve_host_ips(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    return sorted({info[4][0] for info in infos})


def ssrf_check(host: str) -> tuple[bool, str]:
    """Resolve `host` and refuse any address in a non-public range.

    Fail-closed: DNS failure counts as a violation, not a pass.
    NOTE: resolve-then-connect leaves a theoretical DNS-rebinding window;
    production deployments should pin the resolved IP in the transport.
    """
    try:
        ips = resolve_host_ips(host)
    except OSError as exc:
        return False, f"dns-resolution-failed: {exc}"
    for ip_str in ips:
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return False, f"unparseable-resolved-ip: {ip_str}"
        if _ip_is_forbidden(ip):
            return False, f"private-or-reserved-ip: {ip_str}"
    return True, f"resolved-public-ips={len(ips)}"


# ── secret scanning ───────────────────────────────────────────────────

# (label, pattern). Placeholders commonly seen in docs examples are
# excluded to keep false positives low.
_PLACEHOLDER = r"(?!YOUR|your|xxx|XXX|<[^>]*>|example|EXAMPLE|Bearer|TEST|test_)"
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("openai-style-key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("github-pat", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b")),
    ("stripe-key", re.compile(r"\b[sr]k_(test|live)_[0-9a-zA-Z]{16,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}\b")),
    (
        "key-value-pair",
        re.compile(
            r"(?i)\b(api[_-]?key|secret|password|token)[\"']?\s*[:=]\s*[\"']"
            + _PLACEHOLDER
            + r"[A-Za-z0-9_\-]{16,}[\"']"
        ),
    ),
]


def scan_secrets(text: str) -> list[str]:
    """Return labels of credential patterns found in `text`."""
    found = []
    for label, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            found.append(label)
    return found


def redact_secrets(text: str) -> tuple[str, list[str]]:
    """Mask any credential-looking substring. Returns (clean_text, labels)."""
    labels = []
    for label, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            labels.append(label)
            text = pattern.sub(f"[REDACTED:{label}]", text)
    return text, labels


# ── PII redaction (stored evidence quotes) ────────────────────────────

EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]{2,}\b")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}(?!\d)")


def redact_pii(text: str) -> tuple[str, list[str]]:
    labels = []
    if EMAIL_RE.search(text):
        labels.append("email")
        text = EMAIL_RE.sub("[REDACTED:email]", text)
    if PHONE_RE.search(text):
        labels.append("phone")
        text = PHONE_RE.sub("[REDACTED:phone]", text)
    return text, labels


# ── robots.txt ────────────────────────────────────────────────────────

USER_AGENT = "ComposioResearchAgent/1.0 (+research take-home; respects robots.txt)"


class RobotsCache:
    """Fetches and caches robots.txt per origin (through plain httpx)."""

    def __init__(self) -> None:
        self._parsers: dict[str, urllib.robotparser.RobotFileParser] = {}
        self._failed: set[str] = set()

    def can_fetch(self, url: str) -> bool:
        origin = urlparse(url)
        base = f"{origin.scheme}://{origin.netloc}"
        if base in self._failed:
            return True  # unreachable robots.txt -> default allow (RFC 9309)
        if base not in self._parsers:
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(f"{base}/robots.txt")
            try:
                rp.read()
                self._parsers[base] = rp
            except OSError:
                self._failed.add(base)
                return True
        return self._parsers[base].can_fetch(USER_AGENT, url)
