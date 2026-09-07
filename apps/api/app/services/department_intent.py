from dataclasses import dataclass

from app.services.concept_extractor import MatchedConcept, normalize_text


CONCEPT_PREFIX_TO_DEPARTMENT = {
    "ORTHO": "骨科部",
    "NEURO": "神經內科",
    "CARDIO": "心臟內科",
    "CHEST": "胸腔內科",
    "ENDO": "新陳代謝科",
    "GI": "胃腸肝膽科",
    "GERI": "高齡醫學科",
    "GYN": "婦產科",
    "HEME": "血液科",
    "ID": "感染醫學科",
    "NEPHRO": "腎臟科",
    "ONCO": "腫瘤科",
    "RHEUM": "風濕免疫科",
    "PROCTO": "大腸直腸肛門外科",
    "PLASTIC": "整形外科",
    "NS": "神經外科",
    "URO": "泌尿科",
    "CVS": "心臟血管外科",
    "TS": "胸腔外科",
    "TRAUMA": "外傷急症外科",
    "LT": "肝臟移植外科",
    "GS": "一般外科",
    "PED": "兒科",
    "DERM": "皮膚科",
    "OPH": "眼科",
    "PSY": "精神科",
}

DEPARTMENT_KEYWORDS = {
    "骨科部": (
        "骨科",
        "骨科部",
        "關節科",
        "脊椎科",
        "運動醫學",
    ),
    "神經內科": (
        "神經內科",
        "神經科",
        "腦神經",
    ),
    "心臟內科": (
        "心臟內科",
        "心臟科",
        "心血管科",
        "心臟血管",
    ),
    "胸腔內科": (
        "胸腔內科",
        "胸腔科",
        "肺部",
        "呼吸道",
    ),
    "新陳代謝科": (
        "新陳代謝科",
        "新陳代謝",
        "內分泌科",
        "糖尿病",
    ),
    "胃腸肝膽科": (
        "胃腸肝膽科",
        "胃腸科",
        "腸胃科",
        "肝膽腸胃",
    ),
    "高齡醫學科": (
        "高齡醫學科",
        "高齡醫學",
        "老年醫學",
    ),
    "婦產科": (
        "婦產科",
        "婦科",
        "產科",
        "婦產",
    ),
    "血液科": (
        "血液科",
        "血液病",
        "血液疾病",
    ),
    "感染醫學科": (
        "感染醫學科",
        "感染科",
        "感染醫學",
    ),
    "腎臟科": (
        "腎臟科",
        "腎臟病",
        "腎臟疾病",
    ),
    "腫瘤科": (
        "腫瘤科",
        "癌症",
        "腫瘤",
    ),
    "風濕免疫科": (
        "風濕免疫科",
        "風濕科",
        "免疫風濕",
        "自體免疫",
    ),
    "大腸直腸肛門外科": (
        "大腸直腸肛門外科",
        "大腸直腸外科",
        "直腸外科",
        "肛門外科",
    ),
    "整形外科": (
        "整形外科",
        "整形",
        "美容整形",
        "重建整形",
    ),
    "神經外科": (
        "神經外科",
        "腦外科",
        "脊椎神經外科",
    ),
    "泌尿科": (
        "泌尿科",
        "泌尿",
        "泌尿系統",
    ),
    "心臟血管外科": (
        "心臟血管外科",
        "心臟外科",
        "血管外科",
        "心血管外科",
    ),
    "胸腔外科": (
        "胸腔外科",
        "胸外科",
        "胸腔鏡",
    ),
    "外傷急症外科": (
        "外傷急症外科",
        "外傷急重症",
        "創傷外科",
    ),
    "肝臟移植外科": (
        "肝臟移植外科",
        "肝臟移植",
        "肝臟外科",
    ),
    "一般外科": (
        "一般外科",
        "乳房外科",
        "肝膽胰外科",
        "胃腸外科",
    ),
    "兒科": (
        "兒科",
        "小兒科",
        "一般兒科",
        "兒童醫學",
        "新生兒科",
    ),
    "皮膚科": (
        "皮膚科",
        "皮膚病",
        "皮膚疾病",
        "醫學美容",
    ),
    "眼科": (
        "眼科",
        "眼睛",
        "眼疾",
        "視力",
    ),
    "精神科": (
        "精神科",
        "精神醫學",
        "身心科",
        "身心",
    ),
}

AMBIGUOUS_DEPARTMENT_PHRASES = (
    "哪一科",
    "看哪科",
    "看哪一科",
    "不知道看哪",
    "不知道該看哪",
)

EXPLICIT_KEYWORD_SCORE = 3
CONCEPT_PREFIX_SCORE = 1


@dataclass(frozen=True)
class DepartmentIntent:
    department_zh: str | None
    confidence: float


def detect_department_intent(
    query: str,
    matched_concepts: list[MatchedConcept],
) -> DepartmentIntent:
    normalized_query = normalize_text(query)
    scores = {department: 0 for department in DEPARTMENT_KEYWORDS}

    if not is_ambiguous_department_question(normalized_query):
        for department, keywords in DEPARTMENT_KEYWORDS.items():
            for keyword in keywords:
                if normalize_text(keyword) in normalized_query:
                    scores[department] += EXPLICIT_KEYWORD_SCORE

    for concept in matched_concepts:
        prefix = concept.concept_id.split("_", 1)[0]
        department = CONCEPT_PREFIX_TO_DEPARTMENT.get(prefix)
        if department:
            scores[department] += CONCEPT_PREFIX_SCORE

    best_department, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score <= 0:
        return DepartmentIntent(department_zh=None, confidence=0.0)

    sorted_scores = sorted(scores.values(), reverse=True)
    second_score = sorted_scores[1] if len(sorted_scores) > 1 else 0
    if second_score == best_score:
        return DepartmentIntent(department_zh=None, confidence=0.0)

    confidence = min(0.95, 0.45 + (best_score * 0.12) + ((best_score - second_score) * 0.08))
    return DepartmentIntent(
        department_zh=best_department,
        confidence=round(confidence, 2),
    )


def is_ambiguous_department_question(normalized_query: str) -> bool:
    return any(
        normalize_text(phrase) in normalized_query
        for phrase in AMBIGUOUS_DEPARTMENT_PHRASES
    )
