import pytest

from app.services.concept_extractor import MatchedConcept
from app.services.department_intent import detect_department_intent


def matched_concept(concept_id: str) -> MatchedConcept:
    return MatchedConcept(
        concept_id=concept_id,
        canonical_name_zh=concept_id,
        canonical_name_en=concept_id,
        category="disease_or_condition",
        matched_terms=(concept_id,),
    )


def test_detects_cardiology_from_explicit_query():
    intent = detect_department_intent(
        "我想看心臟科，心跳不規則",
        [matched_concept("CARDIO_ARRHYTHMIA")],
    )

    assert intent.department_zh == "心臟內科"
    assert intent.confidence >= 0.75


def test_detects_neurology_from_explicit_query():
    intent = detect_department_intent(
        "想掛神經內科，最近常頭痛",
        [matched_concept("NEURO_HEADACHE")],
    )

    assert intent.department_zh == "神經內科"
    assert intent.confidence >= 0.75


def test_detects_orthopedics_from_concepts_without_explicit_department():
    intent = detect_department_intent(
        "膝蓋卡住，蹲下會痛",
        [matched_concept("ORTHO_KNEE"), matched_concept("ORTHO_MENISCUS_INJURY")],
    )

    assert intent.department_zh == "骨科部"
    assert intent.confidence > 0


def test_vague_department_question_has_no_intent_without_concepts():
    intent = detect_department_intent("我不知道應該看哪一科", [])

    assert intent.department_zh is None
    assert intent.confidence == 0.0


def test_tied_concept_prefixes_have_no_single_intent():
    intent = detect_department_intent(
        "我有腳麻和心悸",
        [matched_concept("NEURO_NEUROPATHIC_PAIN"), matched_concept("CARDIO_ARRHYTHMIA")],
    )

    assert intent.department_zh is None
    assert intent.confidence == 0.0


@pytest.mark.parametrize(
    ("query", "concept_id", "expected_department"),
    [
        ("想看胸腔科，氣喘和慢性咳嗽", "CHEST_ASTHMA", "胸腔內科"),
        ("糖尿病想看新陳代謝科", "ENDO_DIABETES", "新陳代謝科"),
        ("胃食道逆流想看胃腸科", "GI_GERD", "胃腸肝膽科"),
        ("長輩需要高齡醫學評估", "GERI_GERIATRICS", "高齡醫學科"),
        ("想看婦產科，月經失調和子宮肌瘤", "GYN_UTERINE_FIBROIDS", "婦產科"),
        ("淋巴瘤想看血液科", "HEME_LYMPHOMA", "血液科"),
        ("感染醫學追蹤愛滋病", "ID_HIV", "感染醫學科"),
        ("慢性腎臟病想看腎臟科", "NEPHRO_CKD", "腎臟科"),
        ("乳癌想看腫瘤科", "ONCO_BREAST_CANCER", "腫瘤科"),
        ("類風濕想看風濕免疫科", "RHEUM_RHEUMATOID_ARTHRITIS", "風濕免疫科"),
    ],
)
def test_detects_new_department_intents(query, concept_id, expected_department):
    intent = detect_department_intent(query, [matched_concept(concept_id)])

    assert intent.department_zh == expected_department
    assert intent.confidence >= 0.75
