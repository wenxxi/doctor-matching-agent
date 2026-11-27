from datetime import date

import pytest

from app.services.hospital_screening import (
    CANDIDATES, HospitalRedirects, PublicNavigation, allowed_url, mmh_choices,
    mmh_patient_verified,
)


def link(day="2099-12-01", label="可掛", extra="", special="Array"):
    return f'''<a class="regbtn" {extra} onclick="registergo('{day}',1,'52','5236','{special}','first'); return false;">{label}</a>'''


def test_only_future_available_normal_clinics():
    html = (link() + link("2020-01-01") + link(label="額滿")
            + link(extra="disabled") + link(extra='aria-disabled="true"')
            + link(special="A") + link("2099-13-01"))
    choices = mmh_choices(html, date(2026, 11, 27))
    assert len(choices) == 1
    assert choices[0]["doctor_code"] == "5236"


def test_patient_entry_must_match_selected_clinic():
    choice = mmh_choices(link(), date(2026, 11, 27))[0]
    fields = dict(txtID="", txtBirth="", txtwebword="", strSchdate="2099/12/01",
                  strDr="5236", strDept="52", strSchap="1")
    html = '<form action="registerdone.php" method="POST">楊惟翔'
    html += "".join(f'<input name="{key}" value="{value}">' for key, value in fields.items()) + '</form>'
    assert mmh_patient_verified(html, choice, "楊惟翔")
    assert not mmh_patient_verified(html.replace("5236", "9999"), choice, "楊惟翔")
    assert not mmh_patient_verified(html, choice, "其他醫師")


@pytest.mark.parametrize("url", ["http://www.mmh.org.tw/", "https://evil.example/", "https://www.mmh.org.tw.evil.example/", "https://user@www.mmh.org.tw/"])
def test_host_restriction_including_redirects(url):
    hosts = {"www.mmh.org.tw"}
    with pytest.raises(ValueError):
        allowed_url(url, hosts)
    with pytest.raises(ValueError):
        HospitalRedirects(hosts).redirect_request(None, None, 302, "", {}, url)


def test_patient_submission_rejected_before_any_network(monkeypatch):
    client = PublicNavigation(CANDIDATES["mmh_taipei_orthopedics"])
    monkeypatch.setattr(client.opener, "open", lambda *a, **kw: pytest.fail("network must not run"))
    with pytest.raises(ValueError):
        client.page("https://www.mmh.org.tw/registerdone.php", {"txtID":"test"})
    with pytest.raises(ValueError):
        client.page("https://www.mmh.org.tw/register_firstaction.php", {"txtID":"test"})
