"""Bounded, non-secret evidence for public upstream failures; never retain HTML/cookies."""
from datetime import datetime, timezone
import hashlib
import re

SAMPLE_LIMIT = 65_536


def response_evidence(headers, body):
    allowed = {"server", "content-type", "cf-ray", "cf-mitigated", "retry-after"}
    values = {key.lower(): str(value) for key, value in (headers.items() if headers else []) if key.lower() in allowed}
    sample = body[:SAMPLE_LIMIT]
    lower = sample.decode("utf-8", errors="replace").lower()
    result = {"observed_at_utc": datetime.now(timezone.utc).isoformat(),
              "sample_bytes": str(len(sample)), "sample_sha256": hashlib.sha256(sample).hexdigest()}
    if re.fullmatch(r"[A-Za-z0-9 ._/-]{1,80}", values.get("server", "")):
        result["server"] = values["server"]
    if re.fullmatch(r"[0-9a-fA-F]{16,32}-[A-Z0-9]{3,5}", values.get("cf-ray", "")):
        result["cf_ray"] = values["cf-ray"]
    if values.get("cf-mitigated") == "challenge":
        result["cf_mitigated"] = "challenge"
    content_type = values.get("content-type", "").split(";", 1)[0].strip().lower()
    if re.fullmatch(r"[a-z0-9.+-]+/[a-z0-9.+-]+", content_type):
        result["content_type"] = content_type
    if re.fullmatch(r"\d{1,8}", values.get("retry-after", "")):
        result["retry_after_seconds"] = values["retry-after"]
    if result.get("cf_mitigated") == "challenge" or "challenge-platform" in lower or "cf-chl" in lower:
        result["classification"] = "cloudflare_challenge"
    elif "cloudflare" in lower and re.search(r"(?:error\s*(?:code)?[:\s]*|error-code[^>]*>)1020\b", lower):
        result["classification"] = "cloudflare_access_denied_1020"
    elif "cloudflare" in lower or result.get("server", "").lower() == "cloudflare":
        result["classification"] = "cloudflare_other"
    else:
        result["classification"] = "unclassified"
    return result
