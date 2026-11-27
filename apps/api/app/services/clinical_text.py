"""Conservative text evidence for the offline fallback, not a diagnostic model."""
import re


def reported_segments(query: str) -> list[str]:
    # Keep contrasts separate: “沒有糖尿病，但膝蓋痛” must retain knee pain.
    segments = re.split(r"[，,。；;！？!?\n]|但是|不過|而是|只有|只是|但|\bbut\b|\bhowever\b", query, flags=re.I)
    self_complaint = any(re.search(r"(?:我|\bI\b).*(?:痛|麻|咳|暈|脹|pain|hurt|cough)", segment, re.I)
                         and not re.search(r"幫|替|for my", segment, re.I) for segment in segments)
    result = []
    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue
        if re.search(r"家族(?:病)?史|family history", segment, re.I):
            continue
        if (self_complaint and re.search(r"爸爸|媽媽|父親|母親|祖父|祖母|\b(?:father|mother)\b", segment, re.I)
                and not re.search(r"幫|替|for my", segment, re.I)):
            continue
        if re.search(r"沒有|並無|否認|不是|不想看|排除|\b(?:no|not|without|denies|deny)\b", segment, re.I):
            continue
        result.append(segment)
    return result


def term_in_segment(term: str, segment: str) -> bool:
    if re.search(r"[a-zA-Z]", term) and not re.search(r"[\u4e00-\u9fff]", term):
        return bool(re.search(r"(?<![a-z])" + re.escape(term.strip()).replace(r"\ ", r"\s+") + r"(?![a-z])", segment, re.I))
    # Normalize common anatomical wording only; never infer a disease or alter the stored quote.
    normalized_segment = re.sub(r"\s+", "", segment).casefold().replace("膝頭", "膝蓋").replace("肩頭", "肩膀")
    return re.sub(r"\s+", "", term).casefold() in normalized_segment
