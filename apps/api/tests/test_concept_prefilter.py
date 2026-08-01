from app.services.concept_prefilter import prefilter_concepts


def test_prefilter_prioritizes_knee_related_concepts():
    concepts = prefilter_concepts("我跑步後膝蓋卡卡的，蹲下會痛", max_candidates=20)
    concept_ids = [concept["concept_id"] for concept in concepts]

    assert "ORTHO_KNEE" in concept_ids
    assert "ORTHO_KNEE_OSTEOARTHRITIS" in concept_ids
    assert "ORTHO_ACL_INJURY" in concept_ids
    assert "ORTHO_MENISCUS_INJURY" in concept_ids
    assert len(concepts) <= 20


def test_prefilter_expands_shoulder_related_concepts():
    concepts = prefilter_concepts("肩膀卡卡不穩定", max_candidates=20)
    concept_ids = [concept["concept_id"] for concept in concepts]

    assert "ORTHO_SHOULDER" in concept_ids
    assert "ORTHO_ROTATOR_CUFF_INJURY" in concept_ids
    assert "ORTHO_SHOULDER_INSTABILITY" in concept_ids
    assert len(concepts) <= 20


def test_prefilter_adds_common_fallback_for_unmatched_query():
    concepts = prefilter_concepts("zzzz", max_candidates=20, min_candidates=15)
    concept_ids = [concept["concept_id"] for concept in concepts]

    assert len(concepts) >= 15
    assert "ORTHO_KNEE" in concept_ids
    assert "ORTHO_SPINE" in concept_ids
    assert "NEURO_NEUROLOGY" in concept_ids
    assert "CARDIO_CARDIOLOGY" in concept_ids


def test_prefilter_does_not_match_generic_department_question_as_medical_term():
    concepts = prefilter_concepts("我不知道應該看哪一科", max_candidates=20, min_candidates=15)
    concept_ids = [concept["concept_id"] for concept in concepts]

    assert "NEURO_DYSTONIA" not in concept_ids
    assert "CARDIO_GENERAL_INTERNAL_MEDICINE" not in concept_ids[:3]
    assert "CARDIO_CARDIOLOGY" in concept_ids


def test_prefilter_expands_neurology_related_concepts():
    concepts = prefilter_concepts("我常頭痛，也有癲癇和睡眠障礙", max_candidates=20)
    concept_ids = [concept["concept_id"] for concept in concepts]

    assert "NEURO_HEADACHE" in concept_ids
    assert "NEURO_EPILEPSY" in concept_ids
    assert "NEURO_SLEEP_DISORDERS" in concept_ids
    assert len(concepts) <= 20


def test_prefilter_expands_cardiology_related_concepts():
    concepts = prefilter_concepts("心律不整和高血壓，可能需要心導管", max_candidates=20)
    concept_ids = [concept["concept_id"] for concept in concepts]

    assert "CARDIO_ARRHYTHMIA" in concept_ids
    assert "CARDIO_HYPERTENSION" in concept_ids
    assert "CARDIO_CATHETERIZATION" in concept_ids
    assert "CARDIO_INTERVENTIONAL_CARDIOLOGY" in concept_ids
    assert len(concepts) <= 20
