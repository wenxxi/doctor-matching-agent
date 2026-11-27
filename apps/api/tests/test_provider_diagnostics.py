from app.services.provider_diagnostics import response_evidence, SAMPLE_LIMIT


def test_challenge_is_identified_from_documented_header_without_retaining_secrets():
    result = response_evidence({"Server":"cloudflare", "CF-Mitigated":"challenge", "CF-Ray":"a60cf00012345678-PDX",
        "Set-Cookie":"secret_cookie", "Authorization":"secret_bearer", "Content-Type":"text/html; charset=UTF-8"},
        b'<html>private-challenge-token</html>')
    assert result["classification"] == "cloudflare_challenge"
    assert result["cf_ray"] == "a60cf00012345678-PDX"
    assert not any("secret" in str(value) or "private-challenge-token" in str(value) for value in result.values())
    assert "set-cookie" not in result and "authorization" not in result


def test_cloudflare_header_alone_does_not_prove_a_challenge_or_specific_rule():
    assert response_evidence({"server":"cloudflare"}, b'Forbidden')["classification"] == "cloudflare_other"
    assert response_evidence({"server":"nginx"}, b'Forbidden')["classification"] == "unclassified"


def test_body_inspection_is_bounded_and_untrusted_headers_are_not_echoed():
    result = response_evidence({"cf-ray":"not-a-ray-secret", "server":"server\nsecret", "retry-after":"token"}, b'x' * (SAMPLE_LIMIT + 500))
    assert result["sample_bytes"] == str(SAMPLE_LIMIT)
    assert "cf_ray" not in result and "server" not in result and "retry_after_seconds" not in result
