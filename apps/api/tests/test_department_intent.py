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
        ("痔瘡想看大腸直腸外科", "PROCTO_HEMORRHOIDS", "大腸直腸肛門外科"),
        ("想做疤痕重建整形", "PLASTIC_SCAR_KELOID", "整形外科"),
        ("腦瘤想看神經外科", "NS_BRAIN_TUMOR", "神經外科"),
        ("泌尿道結石想看泌尿科", "URO_URINARY_STONES", "泌尿科"),
        ("心臟瓣膜手術想看心臟外科", "CVS_VALVE_SURGERY", "心臟血管外科"),
        ("肺癌手術想看胸腔外科", "TS_LUNG_CANCER_TUMOR", "胸腔外科"),
        ("多重外傷需要外傷急重症", "TRAUMA_MULTIPLE_TRAUMA", "外傷急症外科"),
        ("肝臟移植想找肝臟外科", "LT_LIVER_TRANSPLANT_SURGERY", "肝臟移植外科"),
        ("乳房外科追蹤乳房腫瘤", "GS_BREAST_CANCER_TUMOR", "一般外科"),
        ("小孩發燒想看兒科", "PED_FEVER", "兒科"),
        ("青春痘和濕疹想看皮膚科", "DERM_ACNE_ROSACEA_SCAR", "皮膚科"),
        ("白內障想看眼科", "OPH_CATARACT", "眼科"),
        ("憂鬱焦慮想看精神科", "PSY_DEPRESSION_ANXIETY", "精神科"),
        ("運動傷害想看復健科", "REHAB_SPORTS_MEDICINE", "復健科"),
        ("慢性病追蹤想看家庭醫學", "FAM_CHRONIC_DISEASE_CARE", "家庭醫學科"),
        ("鼻過敏和耳鳴想看耳鼻喉科", "ENT_RHINITIS_SINUSITIS_ENDOSCOPY", "耳鼻喉頭頸外科"),
    ],
)
def test_detects_new_department_intents(query, concept_id, expected_department):
    intent = detect_department_intent(query, [matched_concept(concept_id)])

    assert intent.department_zh == expected_department
    assert intent.confidence >= 0.75
