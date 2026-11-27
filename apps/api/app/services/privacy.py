"""Reduce accidental identity disclosure; free-text detection is not a DLP guarantee."""
import re
import unicodedata

from fastapi import HTTPException

SENSITIVE = re.compile(
    r"(?<![A-Za-z0-9])[A-Za-z][12](?:[\s-]?\d){8}(?!\d)"
    r"|(?:身[分份]證|證號|驗證碼|護照|病歷號|身份证|\bpassport\b|\bnational\s+id\b|\bid\s+(?:number|no\.?)\b)[^\n，。;]{0,16}?[A-Za-z0-9]{4,}"
    r"|(?:生日|出生(?:日期|年月日)?|生於|birthday|birth\s*date|date\s*of\s*birth|\bdob\b)[^\n，。;]{0,12}?\d{2,4}[年./-]\s*\d{1,2}[月./-]\s*\d{1,2}"
    r"|(?:生日|出生日期|birthday|date\s*of\s*birth|\bdob\b)[^\n，。;]{0,10}?\d{6,8}", re.I,
)


def sensitive(text):
    return bool(SENSITIVE.search(unicodedata.normalize("NFKC", text)))


def ensure_safe_text(text):
    if sensitive(text):
        raise HTTPException(422, "證號、生日與驗證碼請填在掛號表單，不要放在一般對話或個案名稱。")


def ensure_safe_payload(value):
    if isinstance(value, str):
        ensure_safe_text(value)
    elif isinstance(value, dict):
        for item in value.values():
            ensure_safe_payload(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            ensure_safe_payload(item)
