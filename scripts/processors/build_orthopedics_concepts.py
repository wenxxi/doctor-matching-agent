#!/usr/bin/env python3
import csv
import re
from collections import defaultdict
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT_DIR / "data" / "processed"
DOCTORS_NORMALIZED_CSV = PROCESSED_DIR / "doctors_normalized.csv"
MEDICAL_CONCEPTS_CSV = PROCESSED_DIR / "medical_concepts.csv"
DOCTOR_CONCEPT_MAP_CSV = PROCESSED_DIR / "doctor_concept_map.csv"

SOURCE = "cgmh_orthopedics_scrape_manual_v1"
HOSPITAL_ZH = "林口長庚紀念醫院"

DATASETS = [
    {
        "path": ROOT_DIR / "data" / "raw" / "cgmh_linkou_orthopedics_doctors.csv",
        "id_prefix": "CGMH_LINKOU_ORTHO",
        "department_zh": "骨科部",
        "subdepartment_zh": "骨科部",
    },
    {
        "path": ROOT_DIR / "data" / "raw" / "cgmh_linkou_neurological_doctors.csv",
        "id_prefix": "CGMH_LINKOU_NEURO",
        "department_zh": "神經內科",
        "subdepartment_zh": "神經內科",
    },
    {
        "path": ROOT_DIR / "data" / "raw" / "cgmh_linkou_cardiological_doctors.csv",
        "id_prefix": "CGMH_LINKOU_CARDIO",
        "department_zh": "心臟內科",
        "subdepartment_zh": "心臟內科",
    },
    {
        "path": ROOT_DIR / "data" / "raw" / "cgmh_linkou_chest_doctors.csv",
        "id_prefix": "CGMH_LINKOU_CHEST",
        "department_zh": "胸腔內科",
        "subdepartment_zh": "胸腔內科",
    },
    {
        "path": ROOT_DIR / "data" / "raw" / "cgmh_linkou_endocrinological_doctors.csv",
        "id_prefix": "CGMH_LINKOU_ENDO",
        "department_zh": "新陳代謝科",
        "subdepartment_zh": "新陳代謝科",
    },
    {
        "path": ROOT_DIR / "data" / "raw" / "cgmh_linkou_gastrointestinal_doctors.csv",
        "id_prefix": "CGMH_LINKOU_GI",
        "department_zh": "胃腸肝膽科",
        "subdepartment_zh": "胃腸肝膽科",
    },
    {
        "path": ROOT_DIR / "data" / "raw" / "cgmh_linkou_geriatrics_doctors.csv",
        "id_prefix": "CGMH_LINKOU_GERI",
        "department_zh": "高齡醫學科",
        "subdepartment_zh": "高齡醫學科",
    },
    {
        "path": ROOT_DIR / "data" / "raw" / "cgmh_linkou_gynecological_doctors.csv",
        "id_prefix": "CGMH_LINKOU_GYN",
        "department_zh": "婦產科",
        "subdepartment_zh": "婦產科",
    },
    {
        "path": ROOT_DIR / "data" / "raw" / "cgmh_linkou_hematological_doctors.csv",
        "id_prefix": "CGMH_LINKOU_HEME",
        "department_zh": "血液科",
        "subdepartment_zh": "血液科",
    },
    {
        "path": ROOT_DIR / "data" / "raw" / "cgmh_linkou_infectious_doctors.csv",
        "id_prefix": "CGMH_LINKOU_ID",
        "department_zh": "感染醫學科",
        "subdepartment_zh": "感染醫學科",
    },
    {
        "path": ROOT_DIR / "data" / "raw" / "cgmh_linkou_nephrological_doctors.csv",
        "id_prefix": "CGMH_LINKOU_NEPHRO",
        "department_zh": "腎臟科",
        "subdepartment_zh": "腎臟科",
    },
    {
        "path": ROOT_DIR / "data" / "raw" / "cgmh_linkou_oncological_doctors.csv",
        "id_prefix": "CGMH_LINKOU_ONCO",
        "department_zh": "腫瘤科",
        "subdepartment_zh": "腫瘤科",
    },
    {
        "path": ROOT_DIR / "data" / "raw" / "cgmh_linkou_rheumatological_doctors.csv",
        "id_prefix": "CGMH_LINKOU_RHEUM",
        "department_zh": "風濕免疫科",
        "subdepartment_zh": "風濕免疫科",
    },
]

DOCTOR_COLUMNS = [
    "doctor_id",
    "doctor_name_zh",
    "hospital_zh",
    "department_zh",
    "subdepartment_zh",
    "specialty_raw_zh",
    "source_url",
]

CONCEPT_COLUMNS = [
    "concept_id",
    "canonical_name_zh",
    "canonical_name_en",
    "category",
    "parent_concept_id",
    "synonyms_zh",
    "synonyms_en",
    "lay_terms_zh",
    "description_zh",
    "source",
]

MAP_COLUMNS = [
    "doctor_id",
    "doctor_name_zh",
    "concept_id",
    "concept_name_zh",
    "source_phrase_zh",
    "match_type",
    "confidence",
]


def concept(
    concept_id,
    zh,
    en,
    category,
    parent="",
    synonyms_zh=(),
    synonyms_en=(),
    lay_terms_zh=(),
    description_zh="",
    source=SOURCE,
):
    return {
        "concept_id": concept_id,
        "canonical_name_zh": zh,
        "canonical_name_en": en,
        "category": category,
        "parent_concept_id": parent,
        "synonyms_zh": ";".join(synonyms_zh),
        "synonyms_en": ";".join(synonyms_en),
        "lay_terms_zh": ";".join(lay_terms_zh),
        "description_zh": description_zh,
        "source": source,
    }


CONCEPTS = [
    concept("ORTHO_SPINE", "脊椎疾病", "Spine disorders", "subspecialty", synonyms_zh=("脊椎病變", "脊椎退化", "脊椎退化性病變", "脊椎外科"), lay_terms_zh=("脊椎問題", "背骨問題"), description_zh="脊椎退化、外傷、感染、腫瘤或神經壓迫相關問題。"),
    concept("ORTHO_SPINE_DISC_HERNIATION", "椎間盤突出", "Disc herniation", "disease_or_condition", "ORTHO_SPINE", synonyms_zh=("椎間盤軟骨突出", "椎間盤病變"), lay_terms_zh=("椎間盤突出", "椎間盤壓到神經"), description_zh="椎間盤突出造成疼痛、麻木或神經壓迫症狀。"),
    concept("ORTHO_SPINE_DEGENERATIVE_DISEASE", "脊椎退化性疾病", "Degenerative spine disease", "disease_or_condition", "ORTHO_SPINE", synonyms_zh=("脊椎退化性病變", "頸椎退化性疾病", "腰椎退化性疾病", "退化性疾患"), lay_terms_zh=("脊椎退化", "脊椎老化"), description_zh="脊椎因退化造成疼痛、狹窄、滑脫或神經壓迫。"),
    concept("ORTHO_SPINE_STENOSIS", "脊椎管狹窄", "Spinal stenosis", "disease_or_condition", "ORTHO_SPINE", synonyms_zh=("椎管狹窄",), lay_terms_zh=("脊椎神經通道變窄",), description_zh="脊椎管變窄造成神經壓迫。"),
    concept("ORTHO_SPINE_SCIATICA", "坐骨神經痛", "Sciatica", "symptom", "ORTHO_SPINE", lay_terms_zh=("屁股痛到腳麻", "坐骨神經痛"), description_zh="坐骨神經受到刺激或壓迫造成臀腿疼痛或麻木。"),
    concept("ORTHO_SPINE_LOW_BACK_PAIN", "下背痛", "Low back pain", "symptom", "ORTHO_SPINE", synonyms_zh=("腰痛", "背痛"), lay_terms_zh=("腰痠背痛", "腰痛"), description_zh="腰背部疼痛，可與肌肉、關節或神經壓迫相關。"),
    concept("ORTHO_SPINE_NECK_SHOULDER_PAIN", "肩頸痛", "Neck and shoulder pain", "symptom", "ORTHO_SPINE", synonyms_zh=("頸痛", "頸部疼痛"), lay_terms_zh=("肩頸痠痛", "脖子痛"), description_zh="頸部或肩頸區域疼痛。"),
    concept("ORTHO_SPINE_SPONDYLOLISTHESIS", "脊椎滑脫", "Spondylolisthesis", "disease_or_condition", "ORTHO_SPINE", synonyms_zh=("腰椎滑脫", "頸椎滑脫"), lay_terms_zh=("脊椎位移",), description_zh="上下脊椎骨位置滑移，可能造成疼痛或神經壓迫。"),
    concept("ORTHO_SPINE_SCOLIOSIS", "脊椎側彎", "Scoliosis", "disease_or_condition", "ORTHO_SPINE", synonyms_zh=("腰椎側彎",), lay_terms_zh=("脊椎歪斜",), description_zh="脊椎向側面彎曲的變形。"),
    concept("ORTHO_SPINE_KYPHOSIS", "駝背", "Kyphosis", "disease_or_condition", "ORTHO_SPINE", synonyms_zh=("駝背畸形",), lay_terms_zh=("駝背",), description_zh="脊椎向後彎曲增加造成背部外觀或功能問題。"),
    concept("ORTHO_SPINE_FRACTURE", "脊椎骨折", "Spinal fracture", "disease_or_condition", "ORTHO_SPINE", synonyms_zh=("胸腰椎外傷", "脊椎外傷"), lay_terms_zh=("脊椎骨斷掉",), description_zh="脊椎骨因外傷或骨質疏鬆造成骨折。"),
    concept("ORTHO_SPINE_COMPRESSION_FRACTURE", "壓迫性骨折", "Compression fracture", "disease_or_condition", "ORTHO_SPINE_FRACTURE", synonyms_zh=("壓迫骨折", "骨鬆性壓迫骨折", "胸腰椎壓迫性骨折"), lay_terms_zh=("脊椎壓扁", "骨鬆壓迫性骨折"), description_zh="常見於骨質疏鬆或外傷造成的脊椎椎體壓扁。"),
    concept("ORTHO_SPINE_TUMOR", "脊椎腫瘤", "Spinal tumor", "disease_or_condition", "ORTHO_SPINE", synonyms_zh=("脊椎骨骼及神經腫瘤", "轉移性脊椎腫瘤", "Metastatic spine disease"), lay_terms_zh=("脊椎長腫瘤",), description_zh="脊椎原發或轉移性腫瘤。"),
    concept("ORTHO_SPINE_INFECTION", "脊椎感染", "Spinal infection", "disease_or_condition", "ORTHO_SPINE", synonyms_zh=("脊椎感染性疾病",), lay_terms_zh=("脊椎發炎感染",), description_zh="脊椎骨或周邊組織感染。"),
    concept("ORTHO_OSTEOPOROSIS", "骨質疏鬆", "Osteoporosis", "disease_or_condition", synonyms_zh=("骨質疏鬆症", "骨鬆"), lay_terms_zh=("骨頭變脆", "骨鬆"), description_zh="骨密度下降，增加骨折風險。"),
    concept("ORTHO_BONE_SPUR", "骨刺", "Bone spur", "disease_or_condition", synonyms_zh=("脊椎骨刺",), lay_terms_zh=("長骨刺",), description_zh="骨頭邊緣增生，可能造成疼痛或神經壓迫。"),
    concept("ORTHO_JOINT_RECONSTRUCTION", "關節重建", "Joint reconstruction", "subspecialty", synonyms_zh=("關節重建手術", "髖關節與膝關節重建手術"), lay_terms_zh=("關節重建",), description_zh="針對關節退化、損傷或人工關節問題的重建治療。"),
    concept("ORTHO_OSTEOARTHRITIS", "退化性關節炎", "Osteoarthritis", "disease_or_condition", "ORTHO_JOINT_RECONSTRUCTION", synonyms_zh=("骨關節退化", "關節炎"), lay_terms_zh=("關節退化", "關節磨損"), description_zh="關節軟骨退化造成疼痛與活動受限。"),
    concept("ORTHO_KNEE_OSTEOARTHRITIS", "膝關節退化", "Knee osteoarthritis", "disease_or_condition", "ORTHO_OSTEOARTHRITIS", synonyms_zh=("膝部疾患",), lay_terms_zh=("膝蓋退化",), description_zh="膝關節退化造成疼痛、變形或行走困難。"),
    concept("ORTHO_HIP_OSTEOARTHRITIS", "髖關節退化", "Hip osteoarthritis", "disease_or_condition", "ORTHO_OSTEOARTHRITIS", synonyms_zh=("髖部疾患",), lay_terms_zh=("髖關節退化",), description_zh="髖關節退化造成鼠蹊或髖部疼痛。"),
    concept("ORTHO_KNEE_ARTHROPLASTY", "人工膝關節置換", "Total knee arthroplasty", "procedure", "ORTHO_JOINT_RECONSTRUCTION", synonyms_zh=("膝人工關節置換", "人工膝關節置換手術"), lay_terms_zh=("換人工膝關節",), description_zh="以人工關節取代嚴重退化或損壞的膝關節。"),
    concept("ORTHO_HIP_ARTHROPLASTY", "人工髖關節置換", "Total hip arthroplasty", "procedure", "ORTHO_JOINT_RECONSTRUCTION", synonyms_zh=("人工髖關節置換手術", "人工髖關節表面置換"), lay_terms_zh=("換人工髖關節",), description_zh="以人工關節取代嚴重退化、壞死或損壞的髖關節。"),
    concept("ORTHO_ARTHROPLASTY", "人工關節置換", "Arthroplasty", "procedure", "ORTHO_JOINT_RECONSTRUCTION", synonyms_zh=("人工關節置換手術", "人工關節重建手術"), lay_terms_zh=("換人工關節",), description_zh="以人工關節取代嚴重損壞的關節。"),
    concept("ORTHO_REVISION_ARTHROPLASTY", "人工關節翻修", "Revision arthroplasty", "procedure", "ORTHO_JOINT_RECONSTRUCTION", synonyms_zh=("人工關節再置換", "人工膝關節及人工髖關節再置換", "膝人工關節毀損後再置換"), lay_terms_zh=("人工關節重做",), description_zh="針對既有人工關節鬆脫、感染或磨損進行重新手術。"),
    concept("ORTHO_PERIPROSTHETIC_JOINT_INFECTION", "人工關節感染", "Periprosthetic joint infection", "disease_or_condition", "ORTHO_JOINT_RECONSTRUCTION", synonyms_zh=("人工關節感染治療",), lay_terms_zh=("人工關節發炎感染",), description_zh="人工關節周圍感染，需要抗生素或手術處理。"),
    concept("ORTHO_PROSTHESIS_LOOSENING", "人工關節鬆脫", "Prosthesis loosening", "disease_or_condition", "ORTHO_REVISION_ARTHROPLASTY", synonyms_zh=("人工關節毀損",), lay_terms_zh=("人工關節鬆掉",), description_zh="人工關節固定不穩或磨損導致疼痛與功能受限。"),
    concept("ORTHO_FEMORAL_HEAD_AVN", "股骨頭缺血性壞死", "Avascular necrosis of femoral head", "disease_or_condition", "ORTHO_HIP_OSTEOARTHRITIS", synonyms_zh=("股骨頭骨壞死",), lay_terms_zh=("股骨頭壞死",), description_zh="股骨頭血流不足造成骨壞死與髖關節疼痛。"),
    concept("ORTHO_SPORTS_MEDICINE", "運動傷害", "Sports injury", "subspecialty", synonyms_zh=("運動醫學", "腳部足踝運動傷害"), lay_terms_zh=("運動受傷",), description_zh="運動造成的肌肉、韌帶、關節或骨骼傷害。"),
    concept("ORTHO_LIGAMENT_INJURY", "韌帶損傷", "Ligament injury", "disease_or_condition", "ORTHO_SPORTS_MEDICINE", synonyms_zh=("韌帶重建", "膝韌帶重建"), lay_terms_zh=("韌帶受傷",), description_zh="韌帶拉傷、斷裂或不穩定。"),
    concept("ORTHO_ACL_INJURY", "前十字韌帶損傷", "ACL injury", "disease_or_condition", "ORTHO_LIGAMENT_INJURY", synonyms_zh=("前十字韌帶斷裂", "ACL injury"), lay_terms_zh=("前十字韌帶受傷",), description_zh="膝關節前十字韌帶受傷，常見於運動傷害。"),
    concept("ORTHO_MENISCUS_INJURY", "半月板損傷", "Meniscus injury", "disease_or_condition", "ORTHO_SPORTS_MEDICINE", synonyms_zh=("半月軟骨損傷", "半月板受傷", "半月板"), lay_terms_zh=("膝蓋半月板受傷",), description_zh="膝關節半月板撕裂或退化。"),
    concept("ORTHO_ROTATOR_CUFF_INJURY", "肩旋轉肌袖損傷", "Rotator cuff injury", "disease_or_condition", "ORTHO_SPORTS_MEDICINE", synonyms_zh=("旋轉肌袖損傷",), lay_terms_zh=("肩膀肌腱受傷",), description_zh="肩部旋轉肌袖肌腱受傷造成疼痛或無力。"),
    concept("ORTHO_SHOULDER_INSTABILITY", "肩關節不穩定", "Shoulder instability", "disease_or_condition", "ORTHO_SPORTS_MEDICINE", synonyms_zh=("肩關節不穩",), lay_terms_zh=("肩膀容易脫臼",), description_zh="肩關節穩定度不足，可能反覆脫臼或疼痛。"),
    concept("ORTHO_TRAUMA", "骨科外傷", "Orthopedic trauma", "subspecialty", synonyms_zh=("骨外傷科", "重大外傷", "骨科外傷重建"), lay_terms_zh=("骨科外傷",), description_zh="骨折、脫臼或嚴重肢體外傷照護。"),
    concept("ORTHO_FRACTURE", "骨折", "Fracture", "disease_or_condition", "ORTHO_TRAUMA", synonyms_zh=("一般骨折", "骨折外傷", "一般骨折外傷", "外傷骨折"), lay_terms_zh=("骨頭斷掉",), description_zh="骨頭因外力或骨質脆弱而斷裂。"),
    concept("ORTHO_COMPLEX_FRACTURE", "複雜骨折", "Complex fracture", "disease_or_condition", "ORTHO_FRACTURE", synonyms_zh=("複雜性骨折", "四肢複雜骨折", "爆裂性骨折"), lay_terms_zh=("嚴重骨折",), description_zh="較複雜或嚴重的骨折，常需重建或固定手術。"),
    concept("ORTHO_PELVIC_FRACTURE", "骨盆骨折", "Pelvic fracture", "disease_or_condition", "ORTHO_FRACTURE", synonyms_zh=("骨盆外傷",), lay_terms_zh=("骨盆斷裂",), description_zh="骨盆環或髖臼相關骨折。"),
    concept("ORTHO_UPPER_LIMB_FRACTURE", "上肢骨折", "Upper limb fracture", "disease_or_condition", "ORTHO_FRACTURE", synonyms_zh=("上肢疾患", "四肢骨折"), lay_terms_zh=("手臂骨折",), description_zh="肩、肘、腕、手等上肢骨折或外傷。"),
    concept("ORTHO_LOWER_LIMB_FRACTURE", "下肢骨折", "Lower limb fracture", "disease_or_condition", "ORTHO_FRACTURE", synonyms_zh=("四肢骨折",), lay_terms_zh=("腿部骨折",), description_zh="髖、膝、踝、足等下肢骨折或外傷。"),
    concept("ORTHO_OSTEOMYELITIS", "骨髓炎", "Osteomyelitis", "disease_or_condition", "ORTHO_TRAUMA", lay_terms_zh=("骨頭感染",), description_zh="骨頭感染造成疼痛、發炎或傷口問題。"),
    concept("ORTHO_HAND_DISORDERS", "手部疾病", "Hand disorders", "subspecialty", synonyms_zh=("手部病變", "手外科", "手部外科"), lay_terms_zh=("手部問題",), description_zh="手部疾病、外傷或功能障礙。"),
    concept("ORTHO_WRIST_DISORDERS", "腕關節疾病", "Wrist disorders", "subspecialty", synonyms_zh=("腕關節重建", "腕部病變"), lay_terms_zh=("手腕問題",), description_zh="腕關節疼痛、退化、外傷或重建問題。"),
    concept("ORTHO_FOOT_ANKLE", "足踝疾病", "Foot and ankle disorders", "subspecialty", synonyms_zh=("足踝", "足踝病變", "足踝疾患", "足踝關節重建"), lay_terms_zh=("腳踝問題", "足踝問題", "足踝疼痛"), description_zh="足部與踝關節疾病、變形或外傷。"),
    concept("ORTHO_DIABETIC_FOOT", "糖尿病足", "Diabetic foot", "disease_or_condition", "ORTHO_FOOT_ANKLE", lay_terms_zh=("糖尿病腳傷口",), description_zh="糖尿病造成足部傷口、感染或循環神經問題。"),
    concept("ORTHO_HALLUX_VALGUS", "大姆趾外翻", "Hallux valgus", "disease_or_condition", "ORTHO_FOOT_ANKLE", synonyms_zh=("拇趾外翻",), lay_terms_zh=("大腳趾外翻",), description_zh="大腳趾向外偏斜造成疼痛或穿鞋困難。"),
    concept("ORTHO_PEDIATRIC_ORTHOPEDICS", "小兒骨科", "Pediatric orthopedics", "subspecialty", synonyms_zh=("兒童先天疾患",), lay_terms_zh=("兒童骨科問題",), description_zh="兒童骨骼、關節、脊椎與先天問題。"),
    concept("ORTHO_PEDIATRIC_FRACTURE", "小兒骨折", "Pediatric fracture", "disease_or_condition", "ORTHO_PEDIATRIC_ORTHOPEDICS", lay_terms_zh=("兒童骨折",), description_zh="兒童或青少年骨折。"),
    concept("ORTHO_DDH", "兒童髖關節發育不良", "Developmental dysplasia of the hip", "disease_or_condition", "ORTHO_PEDIATRIC_ORTHOPEDICS", synonyms_zh=("髖關節發育不良",), lay_terms_zh=("小孩髖關節發育問題",), description_zh="兒童髖關節發育異常造成不穩或脫位風險。"),
    concept("ORTHO_CEREBRAL_PALSY", "腦性麻痺", "Cerebral palsy", "disease_or_condition", "ORTHO_PEDIATRIC_ORTHOPEDICS", lay_terms_zh=("腦麻",), description_zh="腦性麻痺造成的肌肉張力、步態或骨骼關節問題。"),
    concept("ORTHO_MINIMALLY_INVASIVE_SURGERY", "微創手術", "Minimally invasive surgery", "procedure_modifier", synonyms_zh=("微創脊椎手術", "骨折微創手術"), lay_terms_zh=("傷口較小的手術",), description_zh="以較小傷口或較少組織破壞完成治療。"),
    concept("ORTHO_ENDOSCOPIC_SURGERY", "內視鏡手術", "Endoscopic surgery", "procedure", synonyms_zh=("脊椎內視鏡手術", "脊椎微創內視鏡手術"), lay_terms_zh=("內視鏡手術",), description_zh="使用內視鏡輔助進行的手術。"),
    concept("ORTHO_SPINE_ENDOSCOPIC_SURGERY", "脊椎內視鏡手術", "Endoscopic spine surgery", "procedure", "ORTHO_ENDOSCOPIC_SURGERY", synonyms_zh=("微創脊椎內視鏡", "內視鏡椎間盤手術"), lay_terms_zh=("脊椎內視鏡手術",), description_zh="使用內視鏡進行脊椎減壓、椎間盤或相關治療。"),
    concept("ORTHO_ARTHROSCOPIC_SURGERY", "關節鏡手術", "Arthroscopic surgery", "procedure", synonyms_zh=("微創關節鏡手術", "關節鏡"), lay_terms_zh=("關節內視鏡手術",), description_zh="以關節鏡檢查或治療關節內問題。"),
    concept("ORTHO_SPINE_FUSION", "脊椎融合手術", "Spinal fusion", "procedure", "ORTHO_SPINE", synonyms_zh=("脊椎融合", "融合固定術", "脊椎微創減壓融合術"), lay_terms_zh=("脊椎固定手術",), description_zh="將不穩定或病變脊椎節段固定融合。"),
    concept("ORTHO_SPINE_DECOMPRESSION", "脊椎減壓手術", "Spinal decompression", "procedure", "ORTHO_SPINE", synonyms_zh=("減壓手術", "減壓與融合手術"), lay_terms_zh=("神經減壓手術",), description_zh="解除脊椎神經受壓。"),
    concept("ORTHO_VERTEBROPLASTY", "骨水泥灌注治療", "Vertebroplasty", "procedure", "ORTHO_SPINE_COMPRESSION_FRACTURE", synonyms_zh=("骨水泥", "脊椎灌漿手術", "Vertebroplasty", "脊椎骨折骨水泥手術"), lay_terms_zh=("灌骨水泥",), description_zh="以骨水泥穩定脊椎壓迫性骨折。"),
    concept("ORTHO_INJECTION_THERAPY", "注射治療", "Injection therapy", "procedure", synonyms_zh=("超音波導引注射", "超音波檢查與注射治療", "玻尿酸", "PRP", "神經阻斷"), lay_terms_zh=("打針治療",), description_zh="以藥物、玻尿酸、PRP或神經阻斷等注射方式治療疼痛或關節問題。"),
    concept("ORTHO_ULTRASOUND", "超音波檢查", "Ultrasound", "imaging_or_test", synonyms_zh=("超音波檢查", "超音波導引", "超音波引導"), lay_terms_zh=("超音波",), description_zh="使用超音波評估軟組織、關節或引導注射。"),
    concept("ORTHO_CERVICAL_SPINE", "頸椎", "Cervical spine", "anatomy", "ORTHO_SPINE", synonyms_zh=("上頸椎",), lay_terms_zh=("脖子的脊椎",), description_zh="位於頸部的脊椎。"),
    concept("ORTHO_LUMBAR_SPINE", "腰椎", "Lumbar spine", "anatomy", "ORTHO_SPINE", synonyms_zh=("胸腰椎",), lay_terms_zh=("腰部脊椎",), description_zh="位於腰部的脊椎。"),
    concept("ORTHO_SHOULDER", "肩關節", "Shoulder", "anatomy", synonyms_zh=("肩",), lay_terms_zh=("肩膀",), description_zh="肩部關節與周邊肌腱韌帶。"),
    concept("ORTHO_ELBOW", "肘關節", "Elbow", "anatomy", synonyms_zh=("肘", "肘部"), lay_terms_zh=("手肘",), description_zh="上臂與前臂之間的關節。"),
    concept("ORTHO_HAND", "手", "Hand", "anatomy", synonyms_zh=("手部", "上肢"), lay_terms_zh=("手",), description_zh="手掌、手指與相關肌腱骨骼。"),
    concept("ORTHO_WRIST", "腕關節", "Wrist", "anatomy", synonyms_zh=("腕",), lay_terms_zh=("手腕",), description_zh="前臂與手之間的關節。"),
    concept("ORTHO_HIP", "髖關節", "Hip", "anatomy", synonyms_zh=("髖", "髖部"), lay_terms_zh=("髖部", "胯下關節"), description_zh="骨盆與大腿骨之間的關節。"),
    concept("ORTHO_KNEE", "膝關節", "Knee", "anatomy", synonyms_zh=("膝", "膝部"), lay_terms_zh=("膝蓋",), description_zh="大腿與小腿之間的關節。"),
    concept("ORTHO_FOOT_ANKLE_ANATOMY", "足踝", "Foot and ankle", "anatomy", synonyms_zh=("足", "踝", "腳部足踝"), lay_terms_zh=("腳踝", "腳"), description_zh="足部與踝關節。"),
    concept("ORTHO_PELVIS", "骨盆", "Pelvis", "anatomy", synonyms_zh=("骨盆",), lay_terms_zh=("骨盆",), description_zh="連接脊椎與下肢的骨盆結構。"),
    concept("ORTHO_BONE_TUMOR", "骨骼腫瘤", "Bone tumor", "disease_or_condition", synonyms_zh=("肌肉及骨骼腫瘤", "骨骼及軟組織腫瘤"), lay_terms_zh=("骨頭或軟組織腫瘤",), description_zh="骨骼或軟組織腫瘤相關診療。"),
    concept("ORTHO_BONE_INFECTION", "骨科感染", "Orthopedic infection", "disease_or_condition", synonyms_zh=("骨科感染學", "感染性髖關節"), lay_terms_zh=("骨科感染",), description_zh="骨、關節或人工植入物相關感染。"),
    concept("ORTHO_REGENERATIVE_MEDICINE", "再生醫學", "Regenerative medicine", "procedure_modifier", synonyms_zh=("幹細胞", "PRP", "自體高濃縮血小板", "組織工程"), lay_terms_zh=("再生治療",), description_zh="使用細胞、血小板或生物材料輔助修復的治療方向。"),
    concept("ORTHO_HYPERBARIC_OXYGEN", "高壓氧治療", "Hyperbaric oxygen therapy", "procedure", synonyms_zh=("高壓氧醫學", "高壓氧醫療"), lay_terms_zh=("高壓氧",), description_zh="利用高壓氧輔助傷口、感染或組織修復。"),
]

CONCEPTS.extend(
    [
        concept("NEURO_NEUROLOGY", "神經內科", "Neurology", "subspecialty", synonyms_zh=("一般神經科", "一般神經疾病", "神經科"), lay_terms_zh=("神經問題",), description_zh="神經系統疾病與症狀的內科診療。", source="cgmh_neurology_scrape_manual_v1"),
        concept("NEURO_HEADACHE", "頭痛", "Headache", "symptom", "NEURO_NEUROLOGY", synonyms_zh=("急/慢性頭痛", "慢性頭痛"), lay_terms_zh=("頭痛", "頭很痛"), description_zh="頭部疼痛，可包含急性、慢性或其他神經相關頭痛。", source="cgmh_neurology_scrape_manual_v1"),
        concept("NEURO_MIGRAINE", "偏頭痛", "Migraine", "disease_or_condition", "NEURO_HEADACHE", synonyms_zh=("偏頭痛",), lay_terms_zh=("偏頭痛", "單側頭痛"), description_zh="反覆發作的頭痛型態，可能伴隨噁心、怕光或其他症狀。", source="cgmh_neurology_scrape_manual_v1"),
        concept("NEURO_DIZZINESS_VERTIGO", "頭暈與眩暈", "Dizziness and vertigo", "symptom", "NEURO_NEUROLOGY", synonyms_zh=("頭暈", "眩暈", "眩暈症"), lay_terms_zh=("會暈", "天旋地轉"), description_zh="頭暈、平衡感異常或旋轉感。", source="cgmh_neurology_scrape_manual_v1"),
        concept("NEURO_PARKINSON_DISEASE", "巴金森氏症", "Parkinson disease", "disease_or_condition", "NEURO_MOVEMENT_DISORDERS", synonyms_zh=("巴金森症", "帕金森病", "帕金森症", "巴金森氏病"), lay_terms_zh=("巴金森", "手抖動作變慢"), description_zh="常見動作障礙疾病，可能造成顫抖、僵硬、動作變慢或步態問題。", source="cgmh_neurology_scrape_manual_v1"),
        concept("NEURO_MOVEMENT_DISORDERS", "動作障礙疾病", "Movement disorders", "subspecialty", "NEURO_NEUROLOGY", synonyms_zh=("動作障礙", "顫抖症"), lay_terms_zh=("動作不順", "手抖"), description_zh="影響動作控制的神經疾病。", source="cgmh_neurology_scrape_manual_v1"),
        concept("NEURO_DYSTONIA", "肌張力不全", "Dystonia", "disease_or_condition", "NEURO_MOVEMENT_DISORDERS", synonyms_zh=("肌張力不全",), lay_terms_zh=("肌肉不自主收縮",), description_zh="肌肉不自主收縮造成姿勢或動作異常。", source="cgmh_neurology_scrape_manual_v1"),
        concept("NEURO_TREMOR", "震顫", "Tremor", "symptom", "NEURO_MOVEMENT_DISORDERS", synonyms_zh=("震顫", "顫抖症"), lay_terms_zh=("手抖", "發抖"), description_zh="身體部位不自主規律抖動。", source="cgmh_neurology_scrape_manual_v1"),
        concept("NEURO_MYOCONUS", "肌躍症", "Myoclonus", "disease_or_condition", "NEURO_MOVEMENT_DISORDERS", synonyms_zh=("肌躍症", "肌躍動症", "肌抽躍"), lay_terms_zh=("肌肉突然抽動",), description_zh="短暫、快速的不自主肌肉抽動。", source="cgmh_neurology_scrape_manual_v1"),
        concept("NEURO_ATAXIA", "共濟失調", "Ataxia", "disease_or_condition", "NEURO_MOVEMENT_DISORDERS", synonyms_zh=("共濟失調", "脊髓小腦共濟失調症", "小腦萎縮", "脊髓小腦萎縮症"), lay_terms_zh=("走路不穩", "平衡不好"), description_zh="協調和平衡能力異常。", source="cgmh_neurology_scrape_manual_v1"),
        concept("NEURO_SLEEP_DISORDERS", "睡眠障礙", "Sleep disorders", "disease_or_condition", "NEURO_NEUROLOGY", synonyms_zh=("神經性睡眠障礙", "夜間不自主運動", "睡眠不足"), lay_terms_zh=("睡不好", "睡覺會亂動"), description_zh="睡眠品質、睡眠行為或夜間動作異常相關問題。", source="cgmh_neurology_scrape_manual_v1"),
        concept("NEURO_DEMENTIA", "失智症", "Dementia", "disease_or_condition", "NEURO_NEUROLOGY", synonyms_zh=("年輕型失智症", "認知功能障礙", "退化性腦部疾病"), lay_terms_zh=("記憶變差", "認知退化"), description_zh="記憶、語言、判斷或日常功能退化。", source="cgmh_neurology_scrape_manual_v1"),
        concept("NEURO_ALZHEIMER_DISEASE", "阿茲海默症", "Alzheimer disease", "disease_or_condition", "NEURO_DEMENTIA", synonyms_zh=("阿茲海默症",), lay_terms_zh=("阿茲海默",), description_zh="常見退化性失智症原因。", source="cgmh_neurology_scrape_manual_v1"),
        concept("NEURO_VASCULAR_DEMENTIA", "血管性失智症", "Vascular dementia", "disease_or_condition", "NEURO_DEMENTIA", synonyms_zh=("血管性失智症",), lay_terms_zh=("中風後記憶退化",), description_zh="與腦血管疾病相關的認知退化。", source="cgmh_neurology_scrape_manual_v1"),
        concept("NEURO_CEREBROVASCULAR_DISEASE", "腦血管疾病", "Cerebrovascular disease", "disease_or_condition", "NEURO_NEUROLOGY", synonyms_zh=("腦血管疾病",), lay_terms_zh=("腦血管問題",), description_zh="腦部血管相關疾病，包含中風風險與相關照護。", source="cgmh_neurology_scrape_manual_v1"),
        concept("NEURO_STROKE", "腦中風", "Stroke", "disease_or_condition", "NEURO_CEREBROVASCULAR_DISEASE", synonyms_zh=("中風", "脊髓中風"), lay_terms_zh=("中風",), description_zh="腦部或脊髓血流異常造成的急性神經功能缺損。", source="cgmh_neurology_scrape_manual_v1"),
        concept("NEURO_EPILEPSY", "癲癇症", "Epilepsy", "disease_or_condition", "NEURO_NEUROLOGY", synonyms_zh=("癲癇", "麻將癲癇", "音樂癲癇", "反射性癲癇"), lay_terms_zh=("抽搐", "癲癇發作"), description_zh="反覆癲癇發作或腦部異常放電相關疾病。", source="cgmh_neurology_scrape_manual_v1"),
        concept("NEURO_REFRACTORY_EPILEPSY", "頑固型癲癇", "Refractory epilepsy", "disease_or_condition", "NEURO_EPILEPSY", synonyms_zh=("頑固型癲癇藥物", "頑固型癲癇治療"), lay_terms_zh=("藥物控制不好的癲癇",), description_zh="藥物治療仍難以控制的癲癇。", source="cgmh_neurology_scrape_manual_v1"),
        concept("NEURO_EPILEPSY_SURGERY_EVALUATION", "癲癇手術評估", "Epilepsy surgery evaluation", "procedure", "NEURO_EPILEPSY", synonyms_zh=("癲癇外科手術評估", "癲癇外科手術定位", "癲癇外科手術立體定位", "癲癇手術術前評估"), lay_terms_zh=("癲癇手術評估",), description_zh="針對癲癇是否適合手術或定位治療的評估。", source="cgmh_neurology_scrape_manual_v1"),
        concept("NEURO_NEUROPATHIC_PAIN", "神經性疼痛", "Neuropathic pain", "symptom", "NEURO_NEUROLOGY", synonyms_zh=("病態性神經疼痛",), lay_terms_zh=("麻痛刺痛",), description_zh="神經病變造成的疼痛、灼熱、麻刺或異常感覺。", source="cgmh_neurology_scrape_manual_v1"),
        concept("NEURO_PERIPHERAL_NERVE_DISEASE", "周邊神經疾病", "Peripheral nerve disease", "disease_or_condition", "NEURO_NEUROLOGY", synonyms_zh=("週邊神經疾病", "周邊神經肌肉疾病", "遺傳性神經病變"), lay_terms_zh=("周邊神經問題", "手腳麻"), description_zh="周邊神經病變或神經肌肉相關問題。", source="cgmh_neurology_scrape_manual_v1"),
        concept("NEURO_NEUROMUSCULAR_DISEASE", "神經肌肉疾病", "Neuromuscular disease", "disease_or_condition", "NEURO_NEUROLOGY", synonyms_zh=("神經肌肉疾病", "肌肉病變"), lay_terms_zh=("肌肉無力", "神經肌肉問題"), description_zh="影響神經與肌肉功能的疾病。", source="cgmh_neurology_scrape_manual_v1"),
        concept("NEURO_MYASTHENIA_GRAVIS", "重症肌無力症", "Myasthenia gravis", "disease_or_condition", "NEURO_NEUROMUSCULAR_DISEASE", synonyms_zh=("重症肌無力症",), lay_terms_zh=("容易肌肉無力",), description_zh="自體免疫相關神經肌肉接合處疾病，造成易疲勞無力。", source="cgmh_neurology_scrape_manual_v1"),
        concept("NEURO_MULTIPLE_SCLEROSIS", "多發性硬化症", "Multiple sclerosis", "disease_or_condition", "NEURO_NEUROLOGY", synonyms_zh=("多發性硬化症",), lay_terms_zh=("多發性硬化",), description_zh="中樞神經免疫相關脫髓鞘疾病。", source="cgmh_neurology_scrape_manual_v1"),
        concept("NEURO_NMOSD", "視神經脊髓炎", "Neuromyelitis optica spectrum disorder", "disease_or_condition", "NEURO_NEUROLOGY", synonyms_zh=("泛視神經脊髓炎", "視神經脊髓炎"), lay_terms_zh=("視神經脊髓發炎",), description_zh="影響視神經與脊髓的自體免疫疾病。", source="cgmh_neurology_scrape_manual_v1"),
        concept("NEURO_AUTOIMMUNE_ENCEPHALITIS", "自體免疫性腦炎", "Autoimmune encephalitis", "disease_or_condition", "NEURO_NEUROLOGY", synonyms_zh=("自體免疫性腦炎", "神經免疫疾病"), lay_terms_zh=("免疫造成腦部發炎",), description_zh="免疫系統攻擊腦部造成的神經症狀。", source="cgmh_neurology_scrape_manual_v1"),
        concept("NEURO_BRAIN_TUMOR", "腦部腫瘤", "Brain tumor", "disease_or_condition", "NEURO_NEUROLOGY", synonyms_zh=("腦部腫瘤",), lay_terms_zh=("腦部長腫瘤",), description_zh="腦部腫瘤相關神經症狀與照護。", source="cgmh_neurology_scrape_manual_v1"),
        concept("NEURO_HYDROCEPHALUS", "水腦症", "Hydrocephalus", "disease_or_condition", "NEURO_NEUROLOGY", synonyms_zh=("水腦症",), lay_terms_zh=("腦積水",), description_zh="腦脊髓液循環異常造成腦室擴大。", source="cgmh_neurology_scrape_manual_v1"),
        concept("NEURO_BOTULINUM_TOXIN_INJECTION", "肉毒桿菌素注射治療", "Botulinum toxin injection", "procedure", "NEURO_MOVEMENT_DISORDERS", synonyms_zh=("肉毒桿菌素注射", "肉毒桿菌注射", "肉毒桿菌治療"), lay_terms_zh=("肉毒注射",), description_zh="用於特定肌張力、動作障礙或疼痛相關治療。", source="cgmh_neurology_scrape_manual_v1"),
        concept("NEURO_DEEP_BRAIN_STIMULATION", "深層腦部刺激術", "Deep brain stimulation", "procedure", "NEURO_MOVEMENT_DISORDERS", synonyms_zh=("深部腦刺激術", "深層腦部刺激術"), lay_terms_zh=("腦部刺激治療",), description_zh="以植入刺激裝置治療特定動作障礙疾病。", source="cgmh_neurology_scrape_manual_v1"),
        concept("NEURO_TMS", "經顱磁刺激術", "Transcranial magnetic stimulation", "procedure", "NEURO_NEUROLOGY", synonyms_zh=("經顱磁刺激術", "穿顱磁刺激術"), lay_terms_zh=("磁刺激治療",), description_zh="非侵入性腦部磁刺激治療或評估。", source="cgmh_neurology_scrape_manual_v1"),
        concept("NEURO_NEUROGENETICS", "神經遺傳疾病", "Neurogenetic disorders", "disease_or_condition", "NEURO_NEUROLOGY", synonyms_zh=("神經遺傳學", "神經遺傳性疾病", "遺傳性神經退化疾病", "遺傳性神經性疾病", "亨丁頓氏舞蹈症", "亨丁頓舞蹈症"), lay_terms_zh=("遺傳性神經疾病",), description_zh="與遺傳相關的神經退化或動作障礙疾病。", source="cgmh_neurology_scrape_manual_v1"),
        concept("CARDIO_CARDIOLOGY", "心臟內科", "Cardiology", "subspecialty", synonyms_zh=("一般心臟學", "心臟內科學", "心臟血管疾病", "心血管疾病"), lay_terms_zh=("心臟問題",), description_zh="心臟與血管疾病的內科診療。", source="cgmh_cardiology_scrape_manual_v1"),
        concept("CARDIO_CARDIOVASCULAR_DISEASE", "心臟血管疾病", "Cardiovascular disease", "disease_or_condition", "CARDIO_CARDIOLOGY", synonyms_zh=("心血管疾病", "冠心病"), lay_terms_zh=("心血管問題",), description_zh="心臟與血管相關疾病的總稱。", source="cgmh_cardiology_scrape_manual_v1"),
        concept("CARDIO_CORONARY_ARTERY_DISEASE", "冠狀動脈疾病", "Coronary artery disease", "disease_or_condition", "CARDIO_CARDIOVASCULAR_DISEASE", synonyms_zh=("冠心病", "冠狀動脈"), lay_terms_zh=("心臟血管阻塞",), description_zh="供應心臟的冠狀動脈狹窄或阻塞。", source="cgmh_cardiology_scrape_manual_v1"),
        concept("CARDIO_ARRHYTHMIA", "心律不整", "Arrhythmia", "disease_or_condition", "CARDIO_CARDIOLOGY", synonyms_zh=("心律不整",), lay_terms_zh=("心跳不規則", "心悸"), description_zh="心跳節律異常，可能造成心悸、暈眩或其他症狀。", source="cgmh_cardiology_scrape_manual_v1"),
        concept("CARDIO_ELECTROPHYSIOLOGY", "心臟電氣生理檢查及治療", "Cardiac electrophysiology", "procedure", "CARDIO_ARRHYTHMIA", synonyms_zh=("心臟電氣生理檢查", "電生理學檢查", "電燒手術"), lay_terms_zh=("心律檢查", "電燒治療"), description_zh="評估與治療心律不整的電生理檢查或介入治療。", source="cgmh_cardiology_scrape_manual_v1"),
        concept("CARDIO_PACEMAKER", "心律調節器植入", "Pacemaker implantation", "procedure", "CARDIO_ARRHYTHMIA", synonyms_zh=("心律調節器植入", "心臟節律器治療", "心律調節器"), lay_terms_zh=("裝心律調節器",), description_zh="植入裝置協助心跳節律控制。", source="cgmh_cardiology_scrape_manual_v1"),
        concept("CARDIO_CATHETERIZATION", "心導管檢查", "Cardiac catheterization", "procedure", "CARDIO_CARDIOLOGY", synonyms_zh=("心導管檢查", "心導管"), lay_terms_zh=("心導管檢查",), description_zh="以導管檢查心臟血管或心臟結構。", source="cgmh_cardiology_scrape_manual_v1"),
        concept("CARDIO_INTERVENTIONAL_CARDIOLOGY", "介入性心導管治療", "Interventional cardiology", "procedure", "CARDIO_CATHETERIZATION", synonyms_zh=("介入性心導管治療", "心導管介入治療", "心導管介入性治療", "介入型心導管治療", "介入性治療"), lay_terms_zh=("心導管治療",), description_zh="使用心導管進行血管或結構性心臟病介入治療。", source="cgmh_cardiology_scrape_manual_v1"),
        concept("CARDIO_STENT", "血管支架置放", "Vascular stent placement", "procedure", "CARDIO_INTERVENTIONAL_CARDIOLOGY", synonyms_zh=("支架置放", "血管支架", "支架之裝設", "頸動脈血管支架"), lay_terms_zh=("放支架",), description_zh="以支架維持血管暢通的介入治療。", source="cgmh_cardiology_scrape_manual_v1"),
        concept("CARDIO_HYPERTENSION", "高血壓", "Hypertension", "disease_or_condition", "CARDIO_CARDIOVASCULAR_DISEASE", synonyms_zh=("高血壓疾病",), lay_terms_zh=("血壓高",), description_zh="血壓長期偏高，與心血管風險相關。", source="cgmh_cardiology_scrape_manual_v1"),
        concept("CARDIO_HEART_FAILURE", "心臟衰竭", "Heart failure", "disease_or_condition", "CARDIO_CARDIOLOGY", synonyms_zh=("心衰竭", "心臟衰竭"), lay_terms_zh=("心臟無力",), description_zh="心臟無法有效供應身體所需血流。", source="cgmh_cardiology_scrape_manual_v1"),
        concept("CARDIO_ECHOCARDIOGRAPHY", "心臟超音波", "Echocardiography", "imaging_or_test", "CARDIO_CARDIOLOGY", synonyms_zh=("心臟血管超音波", "心血管超音波", "心臟超音波檢查"), lay_terms_zh=("心臟超音波",), description_zh="以超音波評估心臟結構與功能。", source="cgmh_cardiology_scrape_manual_v1"),
        concept("CARDIO_PERIPHERAL_VASCULAR_DISEASE", "周邊血管疾病", "Peripheral vascular disease", "disease_or_condition", "CARDIO_CARDIOVASCULAR_DISEASE", synonyms_zh=("週邊血管", "周邊血管", "週邊血管超音波", "周邊血流超音波"), lay_terms_zh=("周邊血管問題", "腳血管問題"), description_zh="四肢或周邊血管循環相關疾病。", source="cgmh_cardiology_scrape_manual_v1"),
        concept("CARDIO_VALVULAR_HEART_DISEASE", "心臟瓣膜疾病", "Valvular heart disease", "disease_or_condition", "CARDIO_CARDIOLOGY", synonyms_zh=("心臟瓣膜疾病", "二尖瓣", "三尖瓣膜"), lay_terms_zh=("心臟瓣膜問題",), description_zh="心臟瓣膜狹窄或閉鎖不全等疾病。", source="cgmh_cardiology_scrape_manual_v1"),
        concept("CARDIO_STRUCTURAL_HEART_DISEASE", "結構性心臟病", "Structural heart disease", "disease_or_condition", "CARDIO_CARDIOLOGY", synonyms_zh=("結構性心臟病",), lay_terms_zh=("心臟結構問題",), description_zh="心臟結構異常或需介入治療的疾病。", source="cgmh_cardiology_scrape_manual_v1"),
        concept("CARDIO_PULMONARY_HYPERTENSION", "肺高壓", "Pulmonary hypertension", "disease_or_condition", "CARDIO_CARDIOLOGY", synonyms_zh=("肺高壓",), lay_terms_zh=("肺部血壓高",), description_zh="肺循環壓力升高，可造成喘或心臟負擔。", source="cgmh_cardiology_scrape_manual_v1"),
        concept("CARDIO_HYPERLIPIDEMIA", "高血脂", "Hyperlipidemia", "disease_or_condition", "CARDIO_CARDIOVASCULAR_DISEASE", synonyms_zh=("高血脂",), lay_terms_zh=("血脂高", "膽固醇高"), description_zh="血脂或膽固醇異常，與心血管風險相關。", source="cgmh_cardiology_scrape_manual_v1"),
        concept("CARDIO_OBESITY", "肥胖", "Obesity", "disease_or_condition", "CARDIO_CARDIOVASCULAR_DISEASE", synonyms_zh=("肥胖治療",), lay_terms_zh=("體重過重",), description_zh="體重過重或肥胖，可能增加心血管風險。", source="cgmh_cardiology_scrape_manual_v1"),
        concept("CARDIO_GENERAL_INTERNAL_MEDICINE", "一般內科", "General internal medicine", "subspecialty", synonyms_zh=("一般內科學", "內科"), lay_terms_zh=("一般內科",), description_zh="一般內科疾病評估與照護。", source="cgmh_cardiology_scrape_manual_v1"),
        concept("CARDIO_CRITICAL_CARE", "重症醫療照護", "Critical care", "subspecialty", synonyms_zh=("重症醫療照護",), lay_terms_zh=("重症照護",), description_zh="重症病患照護與心臟相關重症處置。", source="cgmh_cardiology_scrape_manual_v1"),
    ]
)

CONCEPTS.extend(
    [
        concept("CHEST_PULMONOLOGY", "胸腔內科", "Pulmonology", "subspecialty", synonyms_zh=("胸腔科", "肺部疾病", "呼吸道疾病"), lay_terms_zh=("肺部問題", "呼吸問題"), description_zh="肺部、呼吸道與胸腔相關疾病診療。", source="cgmh_chest_scrape_manual_v1"),
        concept("CHEST_ASTHMA", "氣喘", "Asthma", "disease_or_condition", "CHEST_PULMONOLOGY", synonyms_zh=("過敏性氣喘",), lay_terms_zh=("喘", "氣喘"), description_zh="慢性呼吸道發炎造成喘鳴、胸悶或咳嗽。", source="cgmh_chest_scrape_manual_v1"),
        concept("CHEST_COPD", "慢性阻塞性肺疾病", "Chronic obstructive pulmonary disease", "disease_or_condition", "CHEST_PULMONOLOGY", synonyms_zh=("肺阻塞", "慢性阻塞性肺疾", "慢性阻塞性肺病", "COPD"), lay_terms_zh=("慢性肺阻塞", "容易喘"), description_zh="慢性呼吸道阻塞造成喘、咳嗽或活動耐受下降。", source="cgmh_chest_scrape_manual_v1"),
        concept("CHEST_CHRONIC_COUGH", "慢性咳嗽", "Chronic cough", "symptom", "CHEST_PULMONOLOGY", synonyms_zh=("久咳", "咳嗽"), lay_terms_zh=("咳很久", "一直咳", "一直咳嗽"), description_zh="持續或反覆咳嗽的症狀。", source="cgmh_chest_scrape_manual_v1"),
        concept("CHEST_TUBERCULOSIS", "結核病", "Tuberculosis", "disease_or_condition", "CHEST_PULMONOLOGY", synonyms_zh=("結核", "肺結核"), lay_terms_zh=("肺結核",), description_zh="結核菌感染，可影響肺部或其他器官。", source="cgmh_chest_scrape_manual_v1"),
        concept("CHEST_PULMONARY_INFECTION", "肺部感染", "Pulmonary infection", "disease_or_condition", "CHEST_PULMONOLOGY", synonyms_zh=("感染性疾病", "肺炎", "呼吸道感染", "呼吸道感染症"), lay_terms_zh=("肺部發炎感染", "黃痰", "咳痰", "有痰", "喉嚨痛"), description_zh="肺部或呼吸道感染相關疾病。", source="cgmh_chest_scrape_manual_v1"),
        concept("CHEST_LUNG_CANCER", "肺癌", "Lung cancer", "disease_or_condition", "CHEST_PULMONOLOGY", synonyms_zh=("肺部腫瘤", "肺腫瘤"), lay_terms_zh=("肺癌",), description_zh="肺部惡性腫瘤相關診療。", source="cgmh_chest_scrape_manual_v1"),
        concept("CHEST_SLEEP_APNEA", "睡眠呼吸中止症", "Sleep apnea", "disease_or_condition", "CHEST_PULMONOLOGY", synonyms_zh=("睡眠呼吸中止",), lay_terms_zh=("睡覺打呼會停呼吸",), description_zh="睡眠期間反覆呼吸暫停或低通氣。", source="cgmh_chest_scrape_manual_v1"),
        concept("CHEST_SMOKING_CESSATION", "戒菸", "Smoking cessation", "procedure_modifier", "CHEST_PULMONOLOGY", synonyms_zh=("戒菸門診",), lay_terms_zh=("戒菸",), description_zh="協助戒除菸品使用以降低肺部與心血管風險。", source="cgmh_chest_scrape_manual_v1"),
        concept("ENDO_ENDOCRINOLOGY", "新陳代謝科", "Endocrinology and metabolism", "subspecialty", synonyms_zh=("內分泌科", "新陳代謝", "內分泌疾病"), lay_terms_zh=("內分泌問題", "代謝問題"), description_zh="內分泌、糖尿病與代謝疾病診療。", source="cgmh_endocrinology_scrape_manual_v1"),
        concept("ENDO_DIABETES", "糖尿病", "Diabetes mellitus", "disease_or_condition", "ENDO_ENDOCRINOLOGY", synonyms_zh=("血糖", "血糖高"), lay_terms_zh=("血糖高", "糖尿病"), description_zh="血糖調控異常造成的慢性代謝疾病。", source="cgmh_endocrinology_scrape_manual_v1"),
        concept("ENDO_DIABETIC_FOOT", "糖尿病足病變", "Diabetic foot disease", "disease_or_condition", "ENDO_DIABETES", synonyms_zh=("糖尿病足",), lay_terms_zh=("糖尿病腳傷口",), description_zh="糖尿病造成足部傷口、感染或神經血管問題。", source="cgmh_endocrinology_scrape_manual_v1"),
        concept("ENDO_METABOLIC_SYNDROME", "代謝症候群", "Metabolic syndrome", "disease_or_condition", "ENDO_ENDOCRINOLOGY", synonyms_zh=("代謝症候群"), lay_terms_zh=("代謝異常",), description_zh="血糖、血壓、血脂與腹部肥胖等代謝風險聚集。", source="cgmh_endocrinology_scrape_manual_v1"),
        concept("ENDO_THYROID_DISEASE", "甲狀腺疾病", "Thyroid disease", "disease_or_condition", "ENDO_ENDOCRINOLOGY", synonyms_zh=("甲狀腺", "甲狀腺及內分泌疾病"), lay_terms_zh=("甲狀腺問題",), description_zh="甲狀腺功能或結構異常相關疾病。", source="cgmh_endocrinology_scrape_manual_v1"),
        concept("ENDO_HYPERTHYROIDISM", "甲狀腺亢進", "Hyperthyroidism", "disease_or_condition", "ENDO_THYROID_DISEASE", synonyms_zh=("甲亢",), lay_terms_zh=("甲狀腺太亢進",), description_zh="甲狀腺荷爾蒙分泌過多。", source="cgmh_endocrinology_scrape_manual_v1"),
        concept("ENDO_HYPOTHYROIDISM", "甲狀腺低下", "Hypothyroidism", "disease_or_condition", "ENDO_THYROID_DISEASE", synonyms_zh=("甲低",), lay_terms_zh=("甲狀腺不足",), description_zh="甲狀腺荷爾蒙不足。", source="cgmh_endocrinology_scrape_manual_v1"),
        concept("ENDO_THYROID_NODULE", "甲狀腺結節", "Thyroid nodule", "disease_or_condition", "ENDO_THYROID_DISEASE", synonyms_zh=("甲狀腺腫瘤",), lay_terms_zh=("甲狀腺長結節",), description_zh="甲狀腺結節或腫塊評估。", source="cgmh_endocrinology_scrape_manual_v1"),
        concept("ENDO_HYPERLIPIDEMIA", "高血脂", "Hyperlipidemia", "disease_or_condition", "ENDO_ENDOCRINOLOGY", synonyms_zh=("血脂異常",), lay_terms_zh=("膽固醇高", "血脂高"), description_zh="血脂或膽固醇異常。", source="cgmh_endocrinology_scrape_manual_v1"),
        concept("ENDO_OBESITY", "肥胖與減重", "Obesity and weight management", "disease_or_condition", "ENDO_ENDOCRINOLOGY", synonyms_zh=("肥胖", "減重"), lay_terms_zh=("體重過重", "想減重"), description_zh="肥胖、體重控制與代謝風險管理。", source="cgmh_endocrinology_scrape_manual_v1"),
        concept("GI_GASTROENTEROLOGY", "胃腸肝膽科", "Gastroenterology and hepatology", "subspecialty", synonyms_zh=("胃腸科", "腸胃科", "肝膽腸胃科", "胃腸疾病"), lay_terms_zh=("腸胃問題", "肝膽腸胃問題"), description_zh="胃腸、肝膽胰與消化道疾病診療。", source="cgmh_gastroenterology_scrape_manual_v1"),
        concept("GI_BLOATING", "腹脹與胃脹氣", "Abdominal bloating", "symptom", "GI_GASTROENTEROLOGY", synonyms_zh=("腹脹", "胃脹", "胃脹氣", "脹氣"), lay_terms_zh=("肚子脹", "胃很脹", "一直脹氣"), description_zh="腹部或胃部脹氣、脹滿感等常見腸胃症狀。", source="cgmh_gastroenterology_scrape_manual_v1"),
        concept("GI_GERD", "胃食道逆流", "Gastroesophageal reflux disease", "disease_or_condition", "GI_GASTROENTEROLOGY", synonyms_zh=("逆流性食道炎", "胃酸逆流"), lay_terms_zh=("火燒心", "胃酸逆流"), description_zh="胃酸或胃內容物逆流造成食道症狀。", source="cgmh_gastroenterology_scrape_manual_v1"),
        concept("GI_HEPATITIS_B", "B型肝炎", "Hepatitis B", "disease_or_condition", "GI_LIVER_DISEASE", synonyms_zh=("B型肝炎病毒", "B肝"), lay_terms_zh=("B肝",), description_zh="B型肝炎病毒感染與追蹤治療。", source="cgmh_gastroenterology_scrape_manual_v1"),
        concept("GI_HEPATITIS_C", "C型肝炎", "Hepatitis C", "disease_or_condition", "GI_LIVER_DISEASE", synonyms_zh=("C型肝炎", "C肝"), lay_terms_zh=("C肝",), description_zh="C型肝炎病毒感染與治療。", source="cgmh_gastroenterology_scrape_manual_v1"),
        concept("GI_LIVER_DISEASE", "肝臟疾病", "Liver disease", "disease_or_condition", "GI_GASTROENTEROLOGY", synonyms_zh=("肝臟學", "肝病", "肝膽"), lay_terms_zh=("肝臟問題",), description_zh="肝炎、脂肪肝、肝硬化或其他肝臟疾病。", source="cgmh_gastroenterology_scrape_manual_v1"),
        concept("GI_CHRONIC_HEPATITIS", "慢性肝炎", "Chronic hepatitis", "disease_or_condition", "GI_LIVER_DISEASE", synonyms_zh=("慢性肝炎", "Chronic hepatitis"), lay_terms_zh=("慢性肝發炎",), description_zh="長期肝臟發炎與相關併發症。", source="cgmh_gastroenterology_scrape_manual_v1"),
        concept("GI_CIRRHOSIS", "肝硬化", "Cirrhosis", "disease_or_condition", "GI_LIVER_DISEASE", synonyms_zh=("肝硬化"), lay_terms_zh=("肝變硬",), description_zh="慢性肝病造成肝臟纖維化與功能受損。", source="cgmh_gastroenterology_scrape_manual_v1"),
        concept("GI_FATTY_LIVER", "脂肪肝", "Fatty liver", "disease_or_condition", "GI_LIVER_DISEASE", synonyms_zh=("脂肪肝"), lay_terms_zh=("肝包油",), description_zh="肝臟脂肪堆積相關疾病。", source="cgmh_gastroenterology_scrape_manual_v1"),
        concept("GI_LIVER_CANCER", "肝癌", "Liver cancer", "disease_or_condition", "GI_LIVER_DISEASE", synonyms_zh=("肝癌", "肝細胞癌", "hepatocarcinogenesis", "hepatocellular carcinoma"), lay_terms_zh=("肝癌",), description_zh="肝臟惡性腫瘤。", source="cgmh_gastroenterology_scrape_manual_v1"),
        concept("GI_INFLAMMATORY_BOWEL_DISEASE", "發炎性腸道疾病", "Inflammatory bowel disease", "disease_or_condition", "GI_GASTROENTEROLOGY", synonyms_zh=("發炎性腸道疾病", "IBD"), lay_terms_zh=("腸道慢性發炎",), description_zh="包含克隆氏症、潰瘍性結腸炎等慢性腸道發炎疾病。", source="cgmh_gastroenterology_scrape_manual_v1"),
        concept("GI_GASTROINTESTINAL_CANCER", "消化道癌症", "Gastrointestinal cancer", "disease_or_condition", "GI_GASTROENTEROLOGY", synonyms_zh=("消化道癌症", "腸胃道腫瘤", "胃癌", "大腸癌", "大腸直腸癌"), lay_terms_zh=("腸胃道癌症",), description_zh="胃腸道相關惡性腫瘤。", source="cgmh_gastroenterology_scrape_manual_v1"),
        concept("GI_ENDOSCOPY", "胃腸道內視鏡", "Gastrointestinal endoscopy", "procedure", "GI_GASTROENTEROLOGY", synonyms_zh=("內視鏡", "胃鏡", "腸鏡", "大腸鏡", "胃腸道內視鏡治療"), lay_terms_zh=("胃鏡", "大腸鏡"), description_zh="以內視鏡檢查或治療消化道疾病。", source="cgmh_gastroenterology_scrape_manual_v1"),
        concept("GI_ENDOSCOPIC_ULTRASOUND", "內視鏡超音波", "Endoscopic ultrasound", "procedure", "GI_ENDOSCOPY", synonyms_zh=("內視鏡超音波"), lay_terms_zh=("內視鏡超音波"), description_zh="結合內視鏡與超音波評估消化道與周邊器官。", source="cgmh_gastroenterology_scrape_manual_v1"),
        concept("GI_BILIARY_PANCREATIC_DISEASE", "膽胰疾病", "Biliary and pancreatic disease", "disease_or_condition", "GI_GASTROENTEROLOGY", synonyms_zh=("膽道", "胰臟", "膽胰"), lay_terms_zh=("膽囊膽管胰臟問題",), description_zh="膽道、膽囊與胰臟相關疾病。", source="cgmh_gastroenterology_scrape_manual_v1"),
        concept("GI_ABDOMINAL_ULTRASOUND_INTERVENTION", "腹部超音波介入治療", "Abdominal ultrasound-guided intervention", "procedure", "GI_GASTROENTEROLOGY", synonyms_zh=("腹部超音波介入治療", "肝膽超音波檢查"), lay_terms_zh=("腹部超音波治療",), description_zh="以腹部或肝膽超音波進行檢查或介入治療。", source="cgmh_gastroenterology_scrape_manual_v1"),
        concept("GERI_GERIATRICS", "高齡醫學", "Geriatrics", "subspecialty", synonyms_zh=("老年醫學", "高齡醫學"), lay_terms_zh=("老人醫學", "長輩照護"), description_zh="高齡者慢性病、功能、用藥與整合照護。", source="cgmh_geriatrics_scrape_manual_v1"),
        concept("GERI_CHRONIC_DISEASE_CARE", "老年慢性病照護", "Geriatric chronic disease care", "subspecialty", "GERI_GERIATRICS", synonyms_zh=("常見老年慢性病", "慢性病診治"), lay_terms_zh=("長輩慢性病",), description_zh="高齡者常見慢性病整合照護。", source="cgmh_geriatrics_scrape_manual_v1"),
        concept("GERI_COMPREHENSIVE_GERIATRIC_ASSESSMENT", "周全性老年整合評估", "Comprehensive geriatric assessment", "procedure", "GERI_GERIATRICS", synonyms_zh=("周全性老年整合評估", "老年整合評估"), lay_terms_zh=("長輩整體評估",), description_zh="針對高齡者醫療、功能、心理與社會需求的整體評估。", source="cgmh_geriatrics_scrape_manual_v1"),
        concept("GERI_POLYPHARMACY", "藥物整合", "Medication reconciliation", "procedure", "GERI_GERIATRICS", synonyms_zh=("藥物整合", "多重用藥"), lay_terms_zh=("整理藥物", "藥太多"), description_zh="檢視與整合高齡者多重用藥。", source="cgmh_geriatrics_scrape_manual_v1"),
        concept("GERI_PREVENTIVE_MEDICINE", "預防醫學", "Preventive medicine", "subspecialty", "GERI_GERIATRICS", synonyms_zh=("預防醫學",), lay_terms_zh=("健康預防",), description_zh="疾病預防與健康促進。", source="cgmh_geriatrics_scrape_manual_v1"),
        concept("GYN_OBSTETRICS_GYNECOLOGY", "婦產科", "Obstetrics and gynecology", "subspecialty", synonyms_zh=("婦產科學", "一般婦產科"), lay_terms_zh=("婦產科問題", "婦科或產科問題"), description_zh="婦科、產科與女性生殖健康相關診療。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_GENERAL_GYNECOLOGY", "一般婦科疾病", "General gynecology", "subspecialty", "GYN_OBSTETRICS_GYNECOLOGY", synonyms_zh=("一般婦科疾病", "一般婦科疾患", "婦科疾病"), lay_terms_zh=("婦科問題",), description_zh="常見婦科疾病的診斷與治療。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_UROGYNECOLOGY", "婦女泌尿及骨盆醫學", "Urogynecology", "subspecialty", "GYN_OBSTETRICS_GYNECOLOGY", synonyms_zh=("婦女泌尿", "婦女骨盆疾病", "生殖泌尿道"), lay_terms_zh=("婦女泌尿問題", "骨盆底問題"), description_zh="女性泌尿、骨盆底與骨盆器官脫垂相關診療。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_URINARY_INCONTINENCE", "女性尿失禁", "Female urinary incontinence", "disease_or_condition", "GYN_UROGYNECOLOGY", synonyms_zh=("尿失禁", "婦女尿失禁"), lay_terms_zh=("漏尿", "咳嗽會漏尿"), description_zh="女性漏尿或尿液控制困難。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_PELVIC_ORGAN_PROLAPSE", "骨盆器官脫垂", "Pelvic organ prolapse", "disease_or_condition", "GYN_UROGYNECOLOGY", synonyms_zh=("骨盆底脫垂", "子宮脫垂", "膀胱脫垂", "直腸脫出", "子宮膀胱直腸脫出", "盆底鬆弛脫垂"), lay_terms_zh=("子宮掉下來", "陰道有東西掉出來"), description_zh="子宮、膀胱或直腸等骨盆器官支撐不足造成脫垂。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_PELVIC_FLOOR_DYSFUNCTION", "骨盆底肌功能異常", "Pelvic floor dysfunction", "disease_or_condition", "GYN_UROGYNECOLOGY", synonyms_zh=("骨盆底肌功能異常", "骨盆重建", "骨盆腔重建"), lay_terms_zh=("骨盆底無力",), description_zh="骨盆底肌肉或支撐功能異常。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_FREQUENT_URINATION", "頻尿急尿", "Urinary frequency and urgency", "symptom", "GYN_UROGYNECOLOGY", synonyms_zh=("頻尿", "急尿"), lay_terms_zh=("一直想尿尿", "尿急"), description_zh="排尿頻率增加或突然強烈尿意。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_URINARY_TRACT_INFECTION", "婦女尿路感染", "Female urinary tract infection", "disease_or_condition", "GYN_UROGYNECOLOGY", synonyms_zh=("婦女尿路感染", "尿路感染", "泌尿道感染"), lay_terms_zh=("女生尿道感染", "尿道發炎"), description_zh="女性泌尿道感染相關問題。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_INTERSTITIAL_CYSTITIS", "間質性膀胱炎", "Interstitial cystitis", "disease_or_condition", "GYN_UROGYNECOLOGY", synonyms_zh=("間質性膀胱炎",), lay_terms_zh=("膀胱反覆疼痛",), description_zh="慢性膀胱疼痛與頻尿急尿相關症候群。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_MENOPAUSE", "更年期症狀", "Menopausal symptoms", "disease_or_condition", "GYN_OBSTETRICS_GYNECOLOGY", synonyms_zh=("更年期症狀", "更年期症候群", "更年期生殖泌尿道徵候群"), lay_terms_zh=("更年期不舒服", "停經後不適"), description_zh="更年期相關身心、泌尿生殖或骨質變化。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_CONTRACEPTION", "避孕諮詢", "Contraception counseling", "procedure", "GYN_GENERAL_GYNECOLOGY", synonyms_zh=("避孕諮詢", "優生保健"), lay_terms_zh=("避孕", "想避孕"), description_zh="避孕方式與生育規劃諮詢。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_PREGNANCY_CARE", "產前檢查", "Prenatal care", "procedure", "GYN_OBSTETRICS_GYNECOLOGY", synonyms_zh=("產前檢查", "一般產檢", "產檢", "自然生產", "剖腹生產"), lay_terms_zh=("懷孕產檢", "懷孕檢查"), description_zh="懷孕期間例行追蹤、自然產或剖腹產相關照護。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_HIGH_RISK_PREGNANCY", "高危險妊娠", "High-risk pregnancy", "disease_or_condition", "GYN_PREGNANCY_CARE", synonyms_zh=("高危險妊娠", "高危妊娠"), lay_terms_zh=("高風險懷孕",), description_zh="需較密切追蹤的高風險孕產照護。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_PRENATAL_GENETIC_COUNSELING", "產前遺傳諮詢", "Prenatal genetic counseling", "procedure", "GYN_PREGNANCY_CARE", synonyms_zh=("產前遺傳諮詢", "產前基因遺傳諮詢", "產前優生遺傳諮詢", "羊膜穿刺", "絨毛膜取樣", "唐氏症篩檢"), lay_terms_zh=("胎兒基因檢查", "唐氏症檢查"), description_zh="懷孕期間胎兒染色體、基因或遺傳風險評估。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_FETAL_ULTRASOUND", "胎兒高層次超音波", "Detailed fetal ultrasound", "imaging_or_test", "GYN_PREGNANCY_CARE", synonyms_zh=("高層次超音波", "胎兒高層次超音波", "胎兒心臟超音波", "3D", "4D"), lay_terms_zh=("胎兒超音波", "高層次產檢"), description_zh="以超音波評估胎兒結構與發育。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_INFERTILITY", "不孕症", "Infertility", "disease_or_condition", "GYN_OBSTETRICS_GYNECOLOGY", synonyms_zh=("不孕症", "不孕症之診斷及治療"), lay_terms_zh=("想懷孕懷不上", "不容易懷孕"), description_zh="受孕困難相關評估與治療。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_ASSISTED_REPRODUCTION", "人工生殖", "Assisted reproduction", "procedure", "GYN_INFERTILITY", synonyms_zh=("人工生殖科技", "人工受孕", "人工授精", "胚胎植入", "取卵", "排卵誘導"), lay_terms_zh=("人工受孕", "做人工生殖"), description_zh="排卵誘導、人工授精、胚胎植入等生殖治療。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_IVF", "試管嬰兒", "In vitro fertilization", "procedure", "GYN_INFERTILITY", synonyms_zh=("試管嬰兒", "IVF"), lay_terms_zh=("做試管",), description_zh="體外受精與胚胎植入治療。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_REPRODUCTIVE_ENDOCRINOLOGY", "生殖內分泌", "Reproductive endocrinology", "subspecialty", "GYN_INFERTILITY", synonyms_zh=("生殖內分泌", "內分泌異常"), lay_terms_zh=("女性荷爾蒙問題",), description_zh="生殖相關荷爾蒙與排卵問題。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_PCOS", "多囊性卵巢症候群", "Polycystic ovary syndrome", "disease_or_condition", "GYN_REPRODUCTIVE_ENDOCRINOLOGY", synonyms_zh=("多囊性卵巢症候群", "多囊性卵囊症候群", "多囊性卵巢"), lay_terms_zh=("多囊",), description_zh="排卵、月經與代謝相關的生殖內分泌疾病。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_MENSTRUAL_DISORDER", "月經失調", "Menstrual disorder", "symptom", "GYN_REPRODUCTIVE_ENDOCRINOLOGY", synonyms_zh=("月經失調",), lay_terms_zh=("月經不規則", "經期亂"), description_zh="月經週期、出血量或規律性異常。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_ENDOMETRIOSIS", "子宮內膜異位症", "Endometriosis", "disease_or_condition", "GYN_GENERAL_GYNECOLOGY", synonyms_zh=("子宮內膜異位症", "巧克力囊腫"), lay_terms_zh=("經痛很嚴重", "巧克力囊腫"), description_zh="子宮內膜組織出現在子宮外造成疼痛、不孕或囊腫。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_UTERINE_FIBROIDS", "子宮肌瘤", "Uterine fibroids", "disease_or_condition", "GYN_GENERAL_GYNECOLOGY", synonyms_zh=("子宮肌瘤", "肌瘤"), lay_terms_zh=("子宮長肌瘤",), description_zh="子宮平滑肌良性腫瘤，可造成經血多或壓迫症狀。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_ADENOMYOSIS", "子宮肌腺症", "Adenomyosis", "disease_or_condition", "GYN_GENERAL_GYNECOLOGY", synonyms_zh=("子宮肌腺症", "子宮肌腺瘤", "腺瘤", "肌腺瘤"), lay_terms_zh=("子宮腺肌症",), description_zh="子宮內膜組織進入子宮肌層，可能造成經痛或經血過多。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_OVARIAN_TUMOR", "卵巢腫瘤", "Ovarian tumor", "disease_or_condition", "GYN_GENERAL_GYNECOLOGY", synonyms_zh=("卵巢腫瘤", "卵巢瘤", "卵巢囊腫"), lay_terms_zh=("卵巢長腫瘤", "卵巢囊腫"), description_zh="卵巢囊腫、良性或惡性腫瘤評估與治療。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_GYNECOLOGIC_ONCOLOGY", "婦科癌症", "Gynecologic oncology", "subspecialty", "GYN_OBSTETRICS_GYNECOLOGY", synonyms_zh=("婦科癌症", "婦癌", "婦科腫瘤", "婦科癌症手術"), lay_terms_zh=("婦科癌症", "婦癌"), description_zh="子宮頸、子宮內膜、卵巢等婦科癌症診療。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_CERVICAL_CANCER", "子宮頸癌", "Cervical cancer", "disease_or_condition", "GYN_GYNECOLOGIC_ONCOLOGY", synonyms_zh=("子宮頸癌", "子宮頸癌前期"), lay_terms_zh=("子宮頸癌",), description_zh="子宮頸惡性腫瘤或癌前病變。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_ENDOMETRIAL_CANCER", "子宮內膜癌", "Endometrial cancer", "disease_or_condition", "GYN_GYNECOLOGIC_ONCOLOGY", synonyms_zh=("子宮內膜癌", "子宮內膜癌症"), lay_terms_zh=("子宮內膜癌",), description_zh="子宮內膜惡性腫瘤。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_OVARIAN_CANCER", "卵巢癌", "Ovarian cancer", "disease_or_condition", "GYN_GYNECOLOGIC_ONCOLOGY", synonyms_zh=("卵巢癌",), lay_terms_zh=("卵巢癌",), description_zh="卵巢惡性腫瘤。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_HPV", "人類乳突病毒", "Human papillomavirus", "disease_or_condition", "GYN_CERVICAL_CANCER", synonyms_zh=("人類乳突病毒", "人類乳狀病毒", "HPV"), lay_terms_zh=("HPV", "子宮頸病毒"), description_zh="與子宮頸癌及癌前病變相關的病毒感染與篩檢。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_CHEMOTHERAPY", "婦癌化學治療", "Gynecologic cancer chemotherapy", "procedure", "GYN_GYNECOLOGIC_ONCOLOGY", synonyms_zh=("化療", "化學治療", "熱化學治療"), lay_terms_zh=("婦癌化療",), description_zh="婦科癌症相關化學治療。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_IMMUNOTHERAPY", "婦癌免疫治療", "Gynecologic cancer immunotherapy", "procedure", "GYN_GYNECOLOGIC_ONCOLOGY", synonyms_zh=("免疫治療", "免疫療法", "免疫檢查抑制"), lay_terms_zh=("婦癌免疫治療",), description_zh="婦科癌症相關免疫治療策略。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_MINIMALLY_INVASIVE_SURGERY", "婦科微創手術", "Gynecologic minimally invasive surgery", "procedure", "GYN_OBSTETRICS_GYNECOLOGY", synonyms_zh=("微創手術", "內視鏡微創手術", "微創式", "微創"), lay_terms_zh=("婦科微創手術",), description_zh="婦科以較小傷口或內視鏡方式進行手術。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_LAPAROSCOPIC_SURGERY", "婦科腹腔鏡手術", "Gynecologic laparoscopic surgery", "procedure", "GYN_MINIMALLY_INVASIVE_SURGERY", synonyms_zh=("腹腔鏡", "腹腔鏡手術", "腹腔鏡微創手術"), lay_terms_zh=("婦科腹腔鏡",), description_zh="以腹腔鏡進行婦科診斷或手術。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_HYSTEROSCOPY", "子宮鏡手術", "Hysteroscopy", "procedure", "GYN_MINIMALLY_INVASIVE_SURGERY", synonyms_zh=("子宮鏡", "子宮鏡手術", "子宮腔鏡", "子宮鏡檢查", "速潔刀"), lay_terms_zh=("子宮鏡",), description_zh="以子宮鏡檢查或治療子宮腔病灶。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_ROBOTIC_SURGERY", "達文西婦科手術", "Robotic gynecologic surgery", "procedure", "GYN_MINIMALLY_INVASIVE_SURGERY", synonyms_zh=("達文西", "達文西手術", "達文西機械手臂手術"), lay_terms_zh=("機器手臂手術",), description_zh="使用達文西機械手臂輔助婦科手術。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("GYN_HIFU", "海扶刀治療", "High-intensity focused ultrasound", "procedure", "GYN_MINIMALLY_INVASIVE_SURGERY", synonyms_zh=("海扶刀", "海扶刀無創手術", "消融手術", "微波消融"), lay_terms_zh=("無傷口肌瘤治療",), description_zh="以聚焦超音波或消融方式治療特定子宮肌瘤或腺瘤。", source="cgmh_gynecology_scrape_manual_v1"),
        concept("HEME_HEMATOLOGY", "血液科", "Hematology", "subspecialty", synonyms_zh=("血液病", "血液疾病"), lay_terms_zh=("血液問題",), description_zh="血液疾病、血球異常與血液腫瘤診療。", source="cgmh_hematology_scrape_manual_v1"),
        concept("HEME_GENERAL_INTERNAL_MEDICINE", "血液科一般內科", "General internal medicine in hematology", "subspecialty", "HEME_HEMATOLOGY", synonyms_zh=("內科",), lay_terms_zh=("一般內科問題",), description_zh="血液科門診中的一般內科評估。", source="cgmh_hematology_scrape_manual_v1"),
        concept("HEME_LYMPHOMA", "淋巴瘤", "Lymphoma", "disease_or_condition", "HEME_HEMATOLOGY", synonyms_zh=("淋巴瘤"), lay_terms_zh=("淋巴癌",), description_zh="淋巴系統惡性腫瘤。", source="cgmh_hematology_scrape_manual_v1"),
        concept("HEME_LEUKEMIA", "白血病", "Leukemia", "disease_or_condition", "HEME_HEMATOLOGY", synonyms_zh=("白血病", "血癌"), lay_terms_zh=("血癌",), description_zh="造血系統惡性疾病。", source="cgmh_hematology_scrape_manual_v1"),
        concept("HEME_ANEMIA", "貧血", "Anemia", "disease_or_condition", "HEME_HEMATOLOGY", synonyms_zh=("貧血"), lay_terms_zh=("血紅素低",), description_zh="紅血球或血紅素不足。", source="cgmh_hematology_scrape_manual_v1"),
        concept("HEME_HEMOPHILIA", "血友病", "Hemophilia", "disease_or_condition", "HEME_HEMATOLOGY", synonyms_zh=("血友病"), lay_terms_zh=("凝血異常",), description_zh="先天性凝血因子缺乏造成出血傾向。", source="cgmh_hematology_scrape_manual_v1"),
        concept("HEME_STEM_CELL_TRANSPLANT", "血液幹細胞移植", "Hematopoietic stem cell transplant", "procedure", "HEME_HEMATOLOGY", synonyms_zh=("血液幹細胞移植", "骨髓移植"), lay_terms_zh=("造血幹細胞移植",), description_zh="以造血幹細胞重建血液與免疫系統的治療。", source="cgmh_hematology_scrape_manual_v1"),
        concept("ID_INFECTIOUS_DISEASE", "感染醫學", "Infectious disease", "subspecialty", synonyms_zh=("感染科", "感染管制", "感染症"), lay_terms_zh=("感染問題",), description_zh="感染性疾病診斷、治療與感染管制。", source="cgmh_infectious_disease_scrape_manual_v1"),
        concept("ID_HIV", "愛滋病", "HIV infection", "disease_or_condition", "ID_INFECTIOUS_DISEASE", synonyms_zh=("HIV", "愛滋"), lay_terms_zh=("愛滋病",), description_zh="人類免疫缺乏病毒感染照護。", source="cgmh_infectious_disease_scrape_manual_v1"),
        concept("ID_MYCOBACTERIAL_INFECTION", "分枝桿菌感染", "Mycobacterial infection", "disease_or_condition", "ID_INFECTIOUS_DISEASE", synonyms_zh=("分枝桿菌",), lay_terms_zh=("分枝桿菌感染",), description_zh="分枝桿菌相關感染診治。", source="cgmh_infectious_disease_scrape_manual_v1"),
        concept("ID_MICROBIAL_INFECTION", "微生物感染", "Microbial infection", "disease_or_condition", "ID_INFECTIOUS_DISEASE", synonyms_zh=("微生物感染",), lay_terms_zh=("細菌病毒感染",), description_zh="微生物造成的感染性疾病。", source="cgmh_infectious_disease_scrape_manual_v1"),
        concept("ID_LIVER_ABSCESS", "肝膿瘍", "Liver abscess", "disease_or_condition", "ID_INFECTIOUS_DISEASE", synonyms_zh=("肝膿瘍", "克雷白氏菌肝膿瘍"), lay_terms_zh=("肝臟化膿感染",), description_zh="肝臟膿瘍或相關細菌感染。", source="cgmh_infectious_disease_scrape_manual_v1"),
        concept("ID_GENERAL_INTERNAL_MEDICINE", "內科疾病", "General internal medicine", "subspecialty", "ID_INFECTIOUS_DISEASE", synonyms_zh=("內科疾病",), lay_terms_zh=("一般內科問題",), description_zh="一般內科疾病評估。", source="cgmh_infectious_disease_scrape_manual_v1"),
        concept("ID_FEVER", "發燒", "Fever", "symptom", "ID_INFECTIOUS_DISEASE", synonyms_zh=("發熱",), lay_terms_zh=("發燒",), description_zh="體溫升高，常與感染或發炎相關。", source="cgmh_infectious_disease_scrape_manual_v1"),
        concept("ID_URINARY_TRACT_INFECTION", "泌尿道感染", "Urinary tract infection", "disease_or_condition", "ID_INFECTIOUS_DISEASE", synonyms_zh=("尿路感染", "泌尿道感染"), lay_terms_zh=("尿道感染",), description_zh="泌尿系統感染。", source="cgmh_infectious_disease_scrape_manual_v1"),
        concept("NEPHRO_NEPHROLOGY", "腎臟科", "Nephrology", "subspecialty", synonyms_zh=("腎臟疾病", "腎臟病"), lay_terms_zh=("腎臟問題",), description_zh="腎臟疾病、透析與腎臟移植相關診療。", source="cgmh_nephrology_scrape_manual_v1"),
        concept("NEPHRO_CKD", "慢性腎臟病", "Chronic kidney disease", "disease_or_condition", "NEPHRO_NEPHROLOGY", synonyms_zh=("慢性腎臟疾病", "急慢性腎臟疾病", "腎臟病"), lay_terms_zh=("腎功能不好",), description_zh="慢性腎功能下降與相關併發症。", source="cgmh_nephrology_scrape_manual_v1"),
        concept("NEPHRO_AKI", "急性腎損傷", "Acute kidney injury", "disease_or_condition", "NEPHRO_NEPHROLOGY", synonyms_zh=("急性腎臟疾病", "急性腎衰竭"), lay_terms_zh=("腎功能突然變差",), description_zh="短時間內腎功能急速惡化。", source="cgmh_nephrology_scrape_manual_v1"),
        concept("NEPHRO_HEMODIALYSIS", "血液透析", "Hemodialysis", "procedure", "NEPHRO_NEPHROLOGY", synonyms_zh=("洗腎", "血液透析"), lay_terms_zh=("洗腎",), description_zh="以血液透析替代部分腎臟功能。", source="cgmh_nephrology_scrape_manual_v1"),
        concept("NEPHRO_PERITONEAL_DIALYSIS", "腹膜透析", "Peritoneal dialysis", "procedure", "NEPHRO_NEPHROLOGY", synonyms_zh=("腹膜透析"), lay_terms_zh=("腹膜洗腎",), description_zh="以腹膜透析替代部分腎臟功能。", source="cgmh_nephrology_scrape_manual_v1"),
        concept("NEPHRO_KIDNEY_TRANSPLANT", "腎臟移植", "Kidney transplant", "procedure", "NEPHRO_NEPHROLOGY", synonyms_zh=("腎臟移植"), lay_terms_zh=("換腎",), description_zh="腎臟移植評估與追蹤。", source="cgmh_nephrology_scrape_manual_v1"),
        concept("NEPHRO_DIABETIC_KIDNEY_DISEASE", "糖尿病腎臟病變", "Diabetic kidney disease", "disease_or_condition", "NEPHRO_CKD", synonyms_zh=("糖尿病腎病變",), lay_terms_zh=("糖尿病影響腎臟",), description_zh="糖尿病造成的腎臟損傷。", source="cgmh_nephrology_scrape_manual_v1"),
        concept("NEPHRO_HYPERTENSION_KIDNEY_DISEASE", "高血壓腎臟病變", "Hypertensive kidney disease", "disease_or_condition", "NEPHRO_CKD", synonyms_zh=("高血壓腎病變",), lay_terms_zh=("高血壓影響腎臟",), description_zh="高血壓相關腎臟損傷。", source="cgmh_nephrology_scrape_manual_v1"),
        concept("NEPHRO_KIDNEY_FIBROSIS", "腎纖維化", "Kidney fibrosis", "disease_or_condition", "NEPHRO_CKD", synonyms_zh=("腎纖維化研究",), lay_terms_zh=("腎臟纖維化",), description_zh="腎臟慢性損傷後纖維化變化。", source="cgmh_nephrology_scrape_manual_v1"),
        concept("ONCO_ONCOLOGY", "腫瘤科", "Oncology", "subspecialty", synonyms_zh=("癌症治療", "固體腫瘤", "腫瘤學"), lay_terms_zh=("癌症", "腫瘤問題"), description_zh="惡性腫瘤與癌症治療諮詢。", source="cgmh_oncology_scrape_manual_v1"),
        concept("ONCO_GENERAL_INTERNAL_MEDICINE", "腫瘤科一般內科", "General internal medicine in oncology", "subspecialty", "ONCO_ONCOLOGY", synonyms_zh=("內科",), lay_terms_zh=("一般內科問題",), description_zh="腫瘤科門診中的一般內科評估。", source="cgmh_oncology_scrape_manual_v1"),
        concept("ONCO_GI_CANCER", "腸胃道腫瘤", "Gastrointestinal cancer", "disease_or_condition", "ONCO_ONCOLOGY", synonyms_zh=("腸胃道腫瘤", "大腸直腸癌", "大腸癌", "胃癌"), lay_terms_zh=("腸胃道癌症",), description_zh="胃腸道相關癌症。", source="cgmh_oncology_scrape_manual_v1"),
        concept("ONCO_BREAST_CANCER", "乳癌", "Breast cancer", "disease_or_condition", "ONCO_ONCOLOGY", synonyms_zh=("乳癌",), lay_terms_zh=("乳房癌症",), description_zh="乳房惡性腫瘤。", source="cgmh_oncology_scrape_manual_v1"),
        concept("ONCO_UROLOGIC_CANCER", "泌尿道腫瘤", "Urologic cancer", "disease_or_condition", "ONCO_ONCOLOGY", synonyms_zh=("泌尿道腫瘤", "泌尿道癌"), lay_terms_zh=("泌尿系統癌症",), description_zh="泌尿系統相關癌症。", source="cgmh_oncology_scrape_manual_v1"),
        concept("ONCO_LUNG_CANCER", "肺癌", "Lung cancer", "disease_or_condition", "ONCO_ONCOLOGY", synonyms_zh=("肺癌",), lay_terms_zh=("肺癌",), description_zh="肺部惡性腫瘤。", source="cgmh_oncology_scrape_manual_v1"),
        concept("ONCO_HEAD_AND_NECK_CANCER", "頭頸癌", "Head and neck cancer", "disease_or_condition", "ONCO_ONCOLOGY", synonyms_zh=("頭頸癌",), lay_terms_zh=("頭頸部癌症",), description_zh="頭頸部惡性腫瘤。", source="cgmh_oncology_scrape_manual_v1"),
        concept("ONCO_ESOPHAGEAL_CANCER", "食道癌", "Esophageal cancer", "disease_or_condition", "ONCO_ONCOLOGY", synonyms_zh=("食道癌",), lay_terms_zh=("食道癌",), description_zh="食道惡性腫瘤。", source="cgmh_oncology_scrape_manual_v1"),
        concept("ONCO_LIVER_CANCER", "肝癌", "Liver cancer", "disease_or_condition", "ONCO_ONCOLOGY", synonyms_zh=("肝癌",), lay_terms_zh=("肝癌",), description_zh="肝臟惡性腫瘤。", source="cgmh_oncology_scrape_manual_v1"),
        concept("ONCO_NEUROENDOCRINE_TUMOR", "神經內分泌瘤", "Neuroendocrine tumor", "disease_or_condition", "ONCO_ONCOLOGY", synonyms_zh=("神經內分泌瘤",), lay_terms_zh=("神經內分泌腫瘤",), description_zh="神經內分泌細胞來源的腫瘤。", source="cgmh_oncology_scrape_manual_v1"),
        concept("ONCO_MELANOMA", "黑色素癌", "Melanoma", "disease_or_condition", "ONCO_ONCOLOGY", synonyms_zh=("黑色素癌", "黑色素瘤"), lay_terms_zh=("黑色素癌",), description_zh="黑色素細胞惡性腫瘤。", source="cgmh_oncology_scrape_manual_v1"),
        concept("ONCO_IMMUNO_ONCOLOGY", "免疫腫瘤治療", "Immuno-oncology", "procedure", "ONCO_ONCOLOGY", synonyms_zh=("免疫腫瘤", "免疫治療"), lay_terms_zh=("癌症免疫治療",), description_zh="使用免疫相關治療策略治療癌症。", source="cgmh_oncology_scrape_manual_v1"),
        concept("ONCO_PALLIATIVE_CARE", "安寧療護", "Palliative care", "subspecialty", "ONCO_ONCOLOGY", synonyms_zh=("安寧療護",), lay_terms_zh=("安寧照護",), description_zh="針對嚴重疾病或癌症病人的症狀緩和與照護。", source="cgmh_oncology_scrape_manual_v1"),
        concept("RHEUM_RHEUMATOLOGY", "風濕免疫科", "Rheumatology and immunology", "subspecialty", synonyms_zh=("風濕科", "免疫風濕", "自體免疫疾病"), lay_terms_zh=("免疫風濕問題",), description_zh="自體免疫、風濕與過敏相關疾病診療。", source="cgmh_rheumatology_scrape_manual_v1"),
        concept("RHEUM_GENERAL_INTERNAL_MEDICINE", "風濕免疫科一般內科", "General internal medicine in rheumatology", "subspecialty", "RHEUM_RHEUMATOLOGY", synonyms_zh=("內科",), lay_terms_zh=("一般內科問題",), description_zh="風濕免疫科門診中的一般內科評估。", source="cgmh_rheumatology_scrape_manual_v1"),
        concept("RHEUM_GOUT", "痛風及高尿酸血症", "Gout and hyperuricemia", "disease_or_condition", "RHEUM_RHEUMATOLOGY", synonyms_zh=("痛風", "高尿酸", "痛風關節炎"), lay_terms_zh=("尿酸高", "痛風"), description_zh="尿酸過高造成痛風發作或關節炎。", source="cgmh_rheumatology_scrape_manual_v1"),
        concept("RHEUM_RHEUMATOID_ARTHRITIS", "類風濕關節炎", "Rheumatoid arthritis", "disease_or_condition", "RHEUM_RHEUMATOLOGY", synonyms_zh=("類風濕性關節炎", "類風濕關節炎門診"), lay_terms_zh=("類風濕",), description_zh="自體免疫造成慢性關節發炎。", source="cgmh_rheumatology_scrape_manual_v1"),
        concept("RHEUM_LUPUS", "紅斑性狼瘡", "Systemic lupus erythematosus", "disease_or_condition", "RHEUM_RHEUMATOLOGY", synonyms_zh=("紅斑性狼瘡",), lay_terms_zh=("狼瘡",), description_zh="全身性自體免疫疾病，可影響皮膚、關節、腎臟等器官。", source="cgmh_rheumatology_scrape_manual_v1"),
        concept("RHEUM_ANKYLOSING_SPONDYLITIS", "僵直性脊椎炎", "Ankylosing spondylitis", "disease_or_condition", "RHEUM_RHEUMATOLOGY", synonyms_zh=("下背痛脊椎炎", "僵直性脊椎炎門診"), lay_terms_zh=("僵直性脊椎炎", "發炎性下背痛"), description_zh="以脊椎與薦腸關節發炎為主的風濕免疫疾病。", source="cgmh_rheumatology_scrape_manual_v1"),
        concept("RHEUM_ALLERGY", "過敏", "Allergy", "disease_or_condition", "RHEUM_RHEUMATOLOGY", synonyms_zh=("過敏", "氣喘及過敏"), lay_terms_zh=("過敏問題",), description_zh="免疫系統對特定物質過度反應造成的症狀。", source="cgmh_rheumatology_scrape_manual_v1"),
        concept("RHEUM_AUTOIMMUNE_DISEASE", "自體免疫疾病", "Autoimmune disease", "disease_or_condition", "RHEUM_RHEUMATOLOGY", synonyms_zh=("自體免疫疾病",), lay_terms_zh=("免疫系統攻擊自己",), description_zh="免疫系統攻擊自身組織造成的疾病。", source="cgmh_rheumatology_scrape_manual_v1"),
    ]
)


MANUAL_RULES = [
    ("脊椎", "ORTHO_SPINE", "exact_keyword", 0.95, False),
    ("頸椎", "ORTHO_CERVICAL_SPINE", "exact_keyword", 0.95, False),
    ("腰椎", "ORTHO_LUMBAR_SPINE", "exact_keyword", 0.95, False),
    ("胸腰椎", "ORTHO_LUMBAR_SPINE", "synonym_keyword", 0.85, False),
    ("椎間盤突出", "ORTHO_SPINE_DISC_HERNIATION", "exact_keyword", 0.95, False),
    ("坐骨神經痛", "ORTHO_SPINE_SCIATICA", "exact_keyword", 0.95, False),
    ("下背痛", "ORTHO_SPINE_LOW_BACK_PAIN", "exact_keyword", 0.95, False),
    ("背痛", "ORTHO_SPINE_LOW_BACK_PAIN", "synonym_keyword", 0.85, False),
    ("腰痛", "ORTHO_SPINE_LOW_BACK_PAIN", "synonym_keyword", 0.85, False),
    ("肩頸痛", "ORTHO_SPINE_NECK_SHOULDER_PAIN", "exact_keyword", 0.95, False),
    ("頸痛", "ORTHO_SPINE_NECK_SHOULDER_PAIN", "synonym_keyword", 0.85, False),
    ("脊椎滑脫", "ORTHO_SPINE_SPONDYLOLISTHESIS", "exact_keyword", 0.95, False),
    ("腰椎退化性滑脫", "ORTHO_SPINE_SPONDYLOLISTHESIS", "synonym_keyword", 0.85, False),
    ("脊椎側彎", "ORTHO_SPINE_SCOLIOSIS", "exact_keyword", 0.95, False),
    ("腰椎退化性側彎", "ORTHO_SPINE_SCOLIOSIS", "synonym_keyword", 0.85, False),
    ("駝背", "ORTHO_SPINE_KYPHOSIS", "exact_keyword", 0.95, False),
    ("脊椎骨折", "ORTHO_SPINE_FRACTURE", "exact_keyword", 0.95, False),
    ("脊椎外傷", "ORTHO_SPINE_FRACTURE", "synonym_keyword", 0.85, False),
    ("壓迫性骨折", "ORTHO_SPINE_COMPRESSION_FRACTURE", "exact_keyword", 0.95, False),
    ("壓迫骨折", "ORTHO_SPINE_COMPRESSION_FRACTURE", "synonym_keyword", 0.85, False),
    ("脊椎腫瘤", "ORTHO_SPINE_TUMOR", "exact_keyword", 0.95, False),
    ("Metastatic spine disease", "ORTHO_SPINE_TUMOR", "synonym_keyword", 0.85, False),
    ("脊椎感染", "ORTHO_SPINE_INFECTION", "exact_keyword", 0.95, False),
    ("骨質疏鬆", "ORTHO_OSTEOPOROSIS", "exact_keyword", 0.95, False),
    ("骨鬆", "ORTHO_OSTEOPOROSIS", "synonym_keyword", 0.85, False),
    ("骨刺", "ORTHO_BONE_SPUR", "exact_keyword", 0.95, False),
    ("脊椎退化", "ORTHO_SPINE_DEGENERATIVE_DISEASE", "exact_keyword", 0.95, False),
    ("椎管狹窄", "ORTHO_SPINE_STENOSIS", "exact_keyword", 0.95, False),
    ("微創", "ORTHO_MINIMALLY_INVASIVE_SURGERY", "exact_keyword", 0.95, False),
    ("內視鏡", "ORTHO_ENDOSCOPIC_SURGERY", "exact_keyword", 0.95, False),
    ("脊椎內視鏡", "ORTHO_SPINE_ENDOSCOPIC_SURGERY", "exact_keyword", 0.95, False),
    ("椎間盤內視鏡", "ORTHO_SPINE_ENDOSCOPIC_SURGERY", "synonym_keyword", 0.85, False),
    ("融合", "ORTHO_SPINE_FUSION", "exact_keyword", 0.95, False),
    ("減壓", "ORTHO_SPINE_DECOMPRESSION", "exact_keyword", 0.95, False),
    ("骨水泥", "ORTHO_VERTEBROPLASTY", "synonym_keyword", 0.85, False),
    ("Vertebroplasty", "ORTHO_VERTEBROPLASTY", "synonym_keyword", 0.85, False),
    ("關節重建", "ORTHO_JOINT_RECONSTRUCTION", "exact_keyword", 0.95, False),
    ("關節炎", "ORTHO_OSTEOARTHRITIS", "exact_keyword", 0.95, False),
    ("骨關節退化", "ORTHO_OSTEOARTHRITIS", "synonym_keyword", 0.85, False),
    ("退化性關節炎", "ORTHO_OSTEOARTHRITIS", "exact_keyword", 0.95, False),
    ("膝部疾患", "ORTHO_KNEE_OSTEOARTHRITIS", "inferred_from_phrase", 0.70, True),
    ("髖部疾患", "ORTHO_HIP_OSTEOARTHRITIS", "inferred_from_phrase", 0.70, True),
    ("人工膝關節", "ORTHO_KNEE_ARTHROPLASTY", "exact_keyword", 0.95, False),
    ("人工髖關節", "ORTHO_HIP_ARTHROPLASTY", "exact_keyword", 0.95, False),
    ("人工關節置換", "ORTHO_ARTHROPLASTY", "exact_keyword", 0.95, False),
    ("人工關節重建", "ORTHO_ARTHROPLASTY", "synonym_keyword", 0.85, False),
    ("人工關節翻修", "ORTHO_REVISION_ARTHROPLASTY", "exact_keyword", 0.95, False),
    ("再置換", "ORTHO_REVISION_ARTHROPLASTY", "synonym_keyword", 0.85, False),
    ("人工關節感染", "ORTHO_PERIPROSTHETIC_JOINT_INFECTION", "exact_keyword", 0.95, False),
    ("人工關節毀損", "ORTHO_PROSTHESIS_LOOSENING", "inferred_from_phrase", 0.70, True),
    ("股骨頭缺血性壞死", "ORTHO_FEMORAL_HEAD_AVN", "exact_keyword", 0.95, False),
    ("股骨頭骨壞死", "ORTHO_FEMORAL_HEAD_AVN", "synonym_keyword", 0.85, False),
    ("運動傷害", "ORTHO_SPORTS_MEDICINE", "exact_keyword", 0.95, False),
    ("運動醫學", "ORTHO_SPORTS_MEDICINE", "synonym_keyword", 0.85, False),
    ("韌帶", "ORTHO_LIGAMENT_INJURY", "exact_keyword", 0.95, False),
    ("關節鏡", "ORTHO_ARTHROSCOPIC_SURGERY", "exact_keyword", 0.95, False),
    ("骨科外傷", "ORTHO_TRAUMA", "exact_keyword", 0.95, False),
    ("外傷", "ORTHO_TRAUMA", "synonym_keyword", 0.85, False),
    ("骨折", "ORTHO_FRACTURE", "exact_keyword", 0.95, False),
    ("複雜骨折", "ORTHO_COMPLEX_FRACTURE", "exact_keyword", 0.95, False),
    ("複雜性骨折", "ORTHO_COMPLEX_FRACTURE", "synonym_keyword", 0.85, False),
    ("爆裂性骨折", "ORTHO_COMPLEX_FRACTURE", "synonym_keyword", 0.85, False),
    ("骨盆骨折", "ORTHO_PELVIC_FRACTURE", "exact_keyword", 0.95, False),
    ("骨盆外傷", "ORTHO_PELVIC_FRACTURE", "synonym_keyword", 0.85, False),
    ("上肢", "ORTHO_UPPER_LIMB_FRACTURE", "inferred_from_phrase", 0.70, True),
    ("四肢骨折", "ORTHO_UPPER_LIMB_FRACTURE", "inferred_from_phrase", 0.70, True),
    ("四肢骨折", "ORTHO_LOWER_LIMB_FRACTURE", "inferred_from_phrase", 0.70, True),
    ("骨髓炎", "ORTHO_OSTEOMYELITIS", "exact_keyword", 0.95, False),
    ("骨科感染", "ORTHO_BONE_INFECTION", "exact_keyword", 0.95, False),
    ("感染性髖關節", "ORTHO_BONE_INFECTION", "synonym_keyword", 0.85, False),
    ("骨骼腫瘤", "ORTHO_BONE_TUMOR", "exact_keyword", 0.95, False),
    ("軟組織腫瘤", "ORTHO_BONE_TUMOR", "synonym_keyword", 0.85, False),
    ("手部", "ORTHO_HAND_DISORDERS", "exact_keyword", 0.95, False),
    ("手外科", "ORTHO_HAND_DISORDERS", "synonym_keyword", 0.85, False),
    ("腕關節", "ORTHO_WRIST_DISORDERS", "exact_keyword", 0.95, False),
    ("足踝", "ORTHO_FOOT_ANKLE", "exact_keyword", 0.95, False),
    ("糖尿病足", "ORTHO_DIABETIC_FOOT", "exact_keyword", 0.95, False),
    ("大姆趾外翻", "ORTHO_HALLUX_VALGUS", "exact_keyword", 0.95, False),
    ("小兒骨科", "ORTHO_PEDIATRIC_ORTHOPEDICS", "exact_keyword", 0.95, False),
    ("兒童先天疾患", "ORTHO_PEDIATRIC_ORTHOPEDICS", "synonym_keyword", 0.85, False),
    ("小兒骨折", "ORTHO_PEDIATRIC_FRACTURE", "exact_keyword", 0.95, False),
    ("兒童髖關節發育不良", "ORTHO_DDH", "exact_keyword", 0.95, False),
    ("腦性麻痺", "ORTHO_CEREBRAL_PALSY", "exact_keyword", 0.95, False),
    ("肩", "ORTHO_SHOULDER", "exact_keyword", 0.95, False),
    ("肩", "ORTHO_ROTATOR_CUFF_INJURY", "inferred_from_phrase", 0.70, True),
    ("肩", "ORTHO_SHOULDER_INSTABILITY", "inferred_from_phrase", 0.70, True),
    ("肘", "ORTHO_ELBOW", "exact_keyword", 0.95, False),
    ("腕", "ORTHO_WRIST", "exact_keyword", 0.95, False),
    ("手部", "ORTHO_HAND", "exact_keyword", 0.95, False),
    ("手外科", "ORTHO_HAND", "synonym_keyword", 0.85, False),
    ("髖", "ORTHO_HIP", "exact_keyword", 0.95, False),
    ("膝", "ORTHO_KNEE", "exact_keyword", 0.95, False),
    ("膝", "ORTHO_ACL_INJURY", "inferred_from_phrase", 0.70, True),
    ("膝", "ORTHO_MENISCUS_INJURY", "inferred_from_phrase", 0.70, True),
    ("踝", "ORTHO_FOOT_ANKLE_ANATOMY", "exact_keyword", 0.95, False),
    ("骨盆", "ORTHO_PELVIS", "exact_keyword", 0.95, False),
    ("高壓氧", "ORTHO_HYPERBARIC_OXYGEN", "exact_keyword", 0.95, False),
    ("超音波", "ORTHO_ULTRASOUND", "exact_keyword", 0.95, False),
    ("注射", "ORTHO_INJECTION_THERAPY", "exact_keyword", 0.95, False),
    ("玻尿酸", "ORTHO_INJECTION_THERAPY", "synonym_keyword", 0.85, False),
    ("PRP", "ORTHO_REGENERATIVE_MEDICINE", "synonym_keyword", 0.85, False),
    ("幹細胞", "ORTHO_REGENERATIVE_MEDICINE", "synonym_keyword", 0.85, False),
    ("再生醫學", "ORTHO_REGENERATIVE_MEDICINE", "exact_keyword", 0.95, False),
]

MANUAL_RULES.extend(
    [
        ("一般神經疾病", "NEURO_NEUROLOGY", "exact_keyword", 0.95, False),
        ("一般神經科", "NEURO_NEUROLOGY", "exact_keyword", 0.95, False),
        ("神經科", "NEURO_NEUROLOGY", "exact_keyword", 0.95, False),
        ("頭痛", "NEURO_HEADACHE", "exact_keyword", 0.95, False),
        ("偏頭痛", "NEURO_MIGRAINE", "exact_keyword", 0.95, False),
        ("頭暈", "NEURO_DIZZINESS_VERTIGO", "exact_keyword", 0.95, False),
        ("眩暈", "NEURO_DIZZINESS_VERTIGO", "exact_keyword", 0.95, False),
        ("巴金森", "NEURO_PARKINSON_DISEASE", "exact_keyword", 0.95, False),
        ("帕金森", "NEURO_PARKINSON_DISEASE", "synonym_keyword", 0.85, False),
        ("動作障礙", "NEURO_MOVEMENT_DISORDERS", "exact_keyword", 0.95, False),
        ("肌張力不全", "NEURO_DYSTONIA", "exact_keyword", 0.95, False),
        ("震顫", "NEURO_TREMOR", "exact_keyword", 0.95, False),
        ("顫抖", "NEURO_TREMOR", "synonym_keyword", 0.85, False),
        ("肌躍", "NEURO_MYOCONUS", "exact_keyword", 0.95, False),
        ("肌抽躍", "NEURO_MYOCONUS", "synonym_keyword", 0.85, False),
        ("共濟失調", "NEURO_ATAXIA", "exact_keyword", 0.95, False),
        ("小腦萎縮", "NEURO_ATAXIA", "synonym_keyword", 0.85, False),
        ("睡眠障礙", "NEURO_SLEEP_DISORDERS", "exact_keyword", 0.95, False),
        ("夜間不自主運動", "NEURO_SLEEP_DISORDERS", "synonym_keyword", 0.85, False),
        ("失智", "NEURO_DEMENTIA", "exact_keyword", 0.95, False),
        ("認知功能障礙", "NEURO_DEMENTIA", "exact_keyword", 0.95, False),
        ("退化性腦部疾病", "NEURO_DEMENTIA", "synonym_keyword", 0.85, False),
        ("阿茲海默", "NEURO_ALZHEIMER_DISEASE", "exact_keyword", 0.95, False),
        ("血管性失智", "NEURO_VASCULAR_DEMENTIA", "exact_keyword", 0.95, False),
        ("腦血管", "NEURO_CEREBROVASCULAR_DISEASE", "exact_keyword", 0.95, False),
        ("腦中風", "NEURO_STROKE", "exact_keyword", 0.95, False),
        ("中風", "NEURO_STROKE", "synonym_keyword", 0.85, False),
        ("癲癇", "NEURO_EPILEPSY", "exact_keyword", 0.95, False),
        ("頑固型癲癇", "NEURO_REFRACTORY_EPILEPSY", "exact_keyword", 0.95, False),
        ("癲癇外科手術", "NEURO_EPILEPSY_SURGERY_EVALUATION", "exact_keyword", 0.95, False),
        ("癲癇手術", "NEURO_EPILEPSY_SURGERY_EVALUATION", "exact_keyword", 0.95, False),
        ("立體定位", "NEURO_EPILEPSY_SURGERY_EVALUATION", "inferred_from_phrase", 0.70, True),
        ("神經性疼痛", "NEURO_NEUROPATHIC_PAIN", "exact_keyword", 0.95, False),
        ("神經疼痛", "NEURO_NEUROPATHIC_PAIN", "synonym_keyword", 0.85, False),
        ("神經痛", "NEURO_NEUROPATHIC_PAIN", "synonym_keyword", 0.85, False),
        ("週邊神經", "NEURO_PERIPHERAL_NERVE_DISEASE", "exact_keyword", 0.95, False),
        ("周邊神經", "NEURO_PERIPHERAL_NERVE_DISEASE", "exact_keyword", 0.95, False),
        ("神經肌肉", "NEURO_NEUROMUSCULAR_DISEASE", "exact_keyword", 0.95, False),
        ("肌肉病變", "NEURO_NEUROMUSCULAR_DISEASE", "synonym_keyword", 0.85, False),
        ("重症肌無力", "NEURO_MYASTHENIA_GRAVIS", "exact_keyword", 0.95, False),
        ("多發性硬化", "NEURO_MULTIPLE_SCLEROSIS", "exact_keyword", 0.95, False),
        ("視神經脊髓炎", "NEURO_NMOSD", "exact_keyword", 0.95, False),
        ("自體免疫性腦炎", "NEURO_AUTOIMMUNE_ENCEPHALITIS", "exact_keyword", 0.95, False),
        ("神經免疫", "NEURO_AUTOIMMUNE_ENCEPHALITIS", "inferred_from_phrase", 0.70, True),
        ("腦部腫瘤", "NEURO_BRAIN_TUMOR", "exact_keyword", 0.95, False),
        ("水腦症", "NEURO_HYDROCEPHALUS", "exact_keyword", 0.95, False),
        ("肉毒桿菌", "NEURO_BOTULINUM_TOXIN_INJECTION", "exact_keyword", 0.95, False),
        ("深層腦部刺激", "NEURO_DEEP_BRAIN_STIMULATION", "exact_keyword", 0.95, False),
        ("深部腦刺激", "NEURO_DEEP_BRAIN_STIMULATION", "synonym_keyword", 0.85, False),
        ("經顱磁刺激", "NEURO_TMS", "exact_keyword", 0.95, False),
        ("穿顱磁刺激", "NEURO_TMS", "synonym_keyword", 0.85, False),
        ("神經遺傳", "NEURO_NEUROGENETICS", "exact_keyword", 0.95, False),
        ("亨丁頓", "NEURO_NEUROGENETICS", "synonym_keyword", 0.85, False),
        ("心臟血管疾病", "CARDIO_CARDIOLOGY", "exact_keyword", 0.95, False),
        ("一般心臟", "CARDIO_CARDIOLOGY", "exact_keyword", 0.95, False),
        ("心臟內科", "CARDIO_CARDIOLOGY", "exact_keyword", 0.95, False),
        ("心血管", "CARDIO_CARDIOVASCULAR_DISEASE", "exact_keyword", 0.95, False),
        ("冠心病", "CARDIO_CORONARY_ARTERY_DISEASE", "exact_keyword", 0.95, False),
        ("冠狀動脈", "CARDIO_CORONARY_ARTERY_DISEASE", "exact_keyword", 0.95, False),
        ("心律不整", "CARDIO_ARRHYTHMIA", "exact_keyword", 0.95, False),
        ("電氣生理", "CARDIO_ELECTROPHYSIOLOGY", "exact_keyword", 0.95, False),
        ("電生理", "CARDIO_ELECTROPHYSIOLOGY", "synonym_keyword", 0.85, False),
        ("電燒", "CARDIO_ELECTROPHYSIOLOGY", "synonym_keyword", 0.85, False),
        ("心律調節器", "CARDIO_PACEMAKER", "exact_keyword", 0.95, False),
        ("心臟節律器", "CARDIO_PACEMAKER", "synonym_keyword", 0.85, False),
        ("心導管", "CARDIO_CATHETERIZATION", "exact_keyword", 0.95, False),
        ("介入性心導管", "CARDIO_INTERVENTIONAL_CARDIOLOGY", "exact_keyword", 0.95, False),
        ("心導管介入", "CARDIO_INTERVENTIONAL_CARDIOLOGY", "exact_keyword", 0.95, False),
        ("介入性治療", "CARDIO_INTERVENTIONAL_CARDIOLOGY", "synonym_keyword", 0.85, False),
        ("支架", "CARDIO_STENT", "exact_keyword", 0.95, False),
        ("高血壓", "CARDIO_HYPERTENSION", "exact_keyword", 0.95, False),
        ("心衰竭", "CARDIO_HEART_FAILURE", "exact_keyword", 0.95, False),
        ("心臟衰竭", "CARDIO_HEART_FAILURE", "exact_keyword", 0.95, False),
        ("心臟超音波", "CARDIO_ECHOCARDIOGRAPHY", "exact_keyword", 0.95, False),
        ("心臟血管超音波", "CARDIO_ECHOCARDIOGRAPHY", "exact_keyword", 0.95, False),
        ("心血管超音波", "CARDIO_ECHOCARDIOGRAPHY", "synonym_keyword", 0.85, False),
        ("週邊血管", "CARDIO_PERIPHERAL_VASCULAR_DISEASE", "exact_keyword", 0.95, False),
        ("周邊血管", "CARDIO_PERIPHERAL_VASCULAR_DISEASE", "exact_keyword", 0.95, False),
        ("週邊血流", "CARDIO_PERIPHERAL_VASCULAR_DISEASE", "synonym_keyword", 0.85, False),
        ("瓣膜", "CARDIO_VALVULAR_HEART_DISEASE", "exact_keyword", 0.95, False),
        ("二尖瓣", "CARDIO_VALVULAR_HEART_DISEASE", "exact_keyword", 0.95, False),
        ("三尖瓣", "CARDIO_VALVULAR_HEART_DISEASE", "exact_keyword", 0.95, False),
        ("結構性心臟病", "CARDIO_STRUCTURAL_HEART_DISEASE", "exact_keyword", 0.95, False),
        ("肺高壓", "CARDIO_PULMONARY_HYPERTENSION", "exact_keyword", 0.95, False),
        ("高血脂", "CARDIO_HYPERLIPIDEMIA", "exact_keyword", 0.95, False),
        ("肥胖", "CARDIO_OBESITY", "exact_keyword", 0.95, False),
        ("一般內科", "CARDIO_GENERAL_INTERNAL_MEDICINE", "exact_keyword", 0.95, False),
        ("內科", "CARDIO_GENERAL_INTERNAL_MEDICINE", "inferred_from_phrase", 0.70, True),
        ("重症醫療照護", "CARDIO_CRITICAL_CARE", "exact_keyword", 0.95, False),
    ]
)

MANUAL_RULES.extend(
    [
        ("胸腔", "CHEST_PULMONOLOGY", "exact_keyword", 0.95, False),
        ("肺部", "CHEST_PULMONOLOGY", "synonym_keyword", 0.85, False),
        ("氣喘", "CHEST_ASTHMA", "exact_keyword", 0.95, False),
        ("肺阻塞", "CHEST_COPD", "exact_keyword", 0.95, False),
        ("慢性阻塞性肺", "CHEST_COPD", "exact_keyword", 0.95, False),
        ("COPD", "CHEST_COPD", "synonym_keyword", 0.85, False),
        ("慢性咳嗽", "CHEST_CHRONIC_COUGH", "exact_keyword", 0.95, False),
        ("結核", "CHEST_TUBERCULOSIS", "exact_keyword", 0.95, False),
        ("感染性疾病", "CHEST_PULMONARY_INFECTION", "exact_keyword", 0.95, False),
        ("肺炎", "CHEST_PULMONARY_INFECTION", "exact_keyword", 0.95, False),
        ("肺癌", "CHEST_LUNG_CANCER", "exact_keyword", 0.95, False),
        ("肺部腫瘤", "CHEST_LUNG_CANCER", "exact_keyword", 0.95, False),
        ("睡眠呼吸中止", "CHEST_SLEEP_APNEA", "exact_keyword", 0.95, False),
        ("戒菸", "CHEST_SMOKING_CESSATION", "exact_keyword", 0.95, False),
        ("新陳代謝", "ENDO_ENDOCRINOLOGY", "exact_keyword", 0.95, False),
        ("內分泌", "ENDO_ENDOCRINOLOGY", "exact_keyword", 0.95, False),
        ("糖尿病", "ENDO_DIABETES", "exact_keyword", 0.95, False),
        ("血糖", "ENDO_DIABETES", "synonym_keyword", 0.85, False),
        ("糖尿病足", "ENDO_DIABETIC_FOOT", "exact_keyword", 0.95, False),
        ("代謝症候群", "ENDO_METABOLIC_SYNDROME", "exact_keyword", 0.95, False),
        ("甲狀腺", "ENDO_THYROID_DISEASE", "exact_keyword", 0.95, False),
        ("甲狀腺亢進", "ENDO_HYPERTHYROIDISM", "exact_keyword", 0.95, False),
        ("甲亢", "ENDO_HYPERTHYROIDISM", "synonym_keyword", 0.85, False),
        ("甲狀腺低下", "ENDO_HYPOTHYROIDISM", "exact_keyword", 0.95, False),
        ("甲低", "ENDO_HYPOTHYROIDISM", "synonym_keyword", 0.85, False),
        ("甲狀腺結節", "ENDO_THYROID_NODULE", "exact_keyword", 0.95, False),
        ("甲狀腺腫瘤", "ENDO_THYROID_NODULE", "synonym_keyword", 0.85, False),
        ("高血脂", "ENDO_HYPERLIPIDEMIA", "exact_keyword", 0.95, False),
        ("肥胖", "ENDO_OBESITY", "exact_keyword", 0.95, False),
        ("減重", "ENDO_OBESITY", "exact_keyword", 0.95, False),
        ("胃腸", "GI_GASTROENTEROLOGY", "exact_keyword", 0.95, False),
        ("腸胃", "GI_GASTROENTEROLOGY", "synonym_keyword", 0.85, False),
        ("肝膽", "GI_GASTROENTEROLOGY", "synonym_keyword", 0.85, False),
        ("胃腸疾病", "GI_BLOATING", "inferred_from_phrase", 0.70, True),
        ("胃腸肝膽疾病", "GI_BLOATING", "inferred_from_phrase", 0.70, True),
        ("腸道疾病", "GI_BLOATING", "inferred_from_phrase", 0.70, True),
        ("逆流性食道炎", "GI_GERD", "exact_keyword", 0.95, False),
        ("胃食道逆流", "GI_GERD", "exact_keyword", 0.95, False),
        ("胃酸逆流", "GI_GERD", "synonym_keyword", 0.85, False),
        ("B型肝炎", "GI_HEPATITIS_B", "exact_keyword", 0.95, False),
        ("B肝", "GI_HEPATITIS_B", "synonym_keyword", 0.85, False),
        ("C型肝炎", "GI_HEPATITIS_C", "exact_keyword", 0.95, False),
        ("C肝", "GI_HEPATITIS_C", "synonym_keyword", 0.85, False),
        ("肝臟", "GI_LIVER_DISEASE", "exact_keyword", 0.95, False),
        ("肝病", "GI_LIVER_DISEASE", "exact_keyword", 0.95, False),
        ("Hepatology", "GI_LIVER_DISEASE", "synonym_keyword", 0.85, False),
        ("肝炎", "GI_CHRONIC_HEPATITIS", "exact_keyword", 0.95, False),
        ("慢性肝炎", "GI_CHRONIC_HEPATITIS", "exact_keyword", 0.95, False),
        ("Chronic hepatitis", "GI_CHRONIC_HEPATITIS", "synonym_keyword", 0.85, False),
        ("肝硬化", "GI_CIRRHOSIS", "exact_keyword", 0.95, False),
        ("脂肪肝", "GI_FATTY_LIVER", "exact_keyword", 0.95, False),
        ("肝癌", "GI_LIVER_CANCER", "exact_keyword", 0.95, False),
        ("hepatocarcinogenesis", "GI_LIVER_CANCER", "synonym_keyword", 0.85, False),
        ("hepatocellular carcinoma", "GI_LIVER_CANCER", "synonym_keyword", 0.85, False),
        ("發炎性腸道疾病", "GI_INFLAMMATORY_BOWEL_DISEASE", "exact_keyword", 0.95, False),
        ("IBD", "GI_INFLAMMATORY_BOWEL_DISEASE", "synonym_keyword", 0.85, False),
        ("消化道癌症", "GI_GASTROINTESTINAL_CANCER", "exact_keyword", 0.95, False),
        ("腸胃道腫瘤", "GI_GASTROINTESTINAL_CANCER", "exact_keyword", 0.95, False),
        ("大腸直腸癌", "GI_GASTROINTESTINAL_CANCER", "exact_keyword", 0.95, False),
        ("胃腸道內視鏡", "GI_ENDOSCOPY", "exact_keyword", 0.95, False),
        ("內視鏡", "GI_ENDOSCOPY", "exact_keyword", 0.95, False),
        ("胃鏡", "GI_ENDOSCOPY", "synonym_keyword", 0.85, False),
        ("大腸鏡", "GI_ENDOSCOPY", "synonym_keyword", 0.85, False),
        ("腸鏡", "GI_ENDOSCOPY", "synonym_keyword", 0.85, False),
        ("內視鏡超音波", "GI_ENDOSCOPIC_ULTRASOUND", "exact_keyword", 0.95, False),
        ("腹部超音波介入", "GI_ABDOMINAL_ULTRASOUND_INTERVENTION", "exact_keyword", 0.95, False),
        ("肝膽超音波", "GI_ABDOMINAL_ULTRASOUND_INTERVENTION", "synonym_keyword", 0.85, False),
        ("膽道", "GI_BILIARY_PANCREATIC_DISEASE", "exact_keyword", 0.95, False),
        ("胰臟", "GI_BILIARY_PANCREATIC_DISEASE", "exact_keyword", 0.95, False),
        ("膽胰", "GI_BILIARY_PANCREATIC_DISEASE", "synonym_keyword", 0.85, False),
        ("高齡醫學", "GERI_GERIATRICS", "exact_keyword", 0.95, False),
        ("老年", "GERI_GERIATRICS", "exact_keyword", 0.95, False),
        ("老年慢性病", "GERI_CHRONIC_DISEASE_CARE", "exact_keyword", 0.95, False),
        ("慢性病診治", "GERI_CHRONIC_DISEASE_CARE", "exact_keyword", 0.95, False),
        ("周全性老年整合評估", "GERI_COMPREHENSIVE_GERIATRIC_ASSESSMENT", "exact_keyword", 0.95, False),
        ("藥物整合", "GERI_POLYPHARMACY", "exact_keyword", 0.95, False),
        ("預防醫學", "GERI_PREVENTIVE_MEDICINE", "exact_keyword", 0.95, False),
        ("婦產科", "GYN_OBSTETRICS_GYNECOLOGY", "exact_keyword", 0.95, False),
        ("婦產科學", "GYN_OBSTETRICS_GYNECOLOGY", "exact_keyword", 0.95, False),
        ("一般婦產科", "GYN_OBSTETRICS_GYNECOLOGY", "exact_keyword", 0.95, False),
        ("一般婦科", "GYN_GENERAL_GYNECOLOGY", "exact_keyword", 0.95, False),
        ("婦科疾病", "GYN_GENERAL_GYNECOLOGY", "exact_keyword", 0.95, False),
        ("婦科疾患", "GYN_GENERAL_GYNECOLOGY", "synonym_keyword", 0.85, False),
        ("婦女泌尿", "GYN_UROGYNECOLOGY", "exact_keyword", 0.95, False),
        ("婦女骨盆疾病", "GYN_UROGYNECOLOGY", "exact_keyword", 0.95, False),
        ("生殖泌尿道", "GYN_UROGYNECOLOGY", "exact_keyword", 0.95, False),
        ("尿失禁", "GYN_URINARY_INCONTINENCE", "exact_keyword", 0.95, False),
        ("骨盆底脫垂", "GYN_PELVIC_ORGAN_PROLAPSE", "exact_keyword", 0.95, False),
        ("盆底鬆弛脫垂", "GYN_PELVIC_ORGAN_PROLAPSE", "exact_keyword", 0.95, False),
        ("子宮脫垂", "GYN_PELVIC_ORGAN_PROLAPSE", "exact_keyword", 0.95, False),
        ("膀胱脫垂", "GYN_PELVIC_ORGAN_PROLAPSE", "exact_keyword", 0.95, False),
        ("直腸脫出", "GYN_PELVIC_ORGAN_PROLAPSE", "exact_keyword", 0.95, False),
        ("骨盆底肌功能異常", "GYN_PELVIC_FLOOR_DYSFUNCTION", "exact_keyword", 0.95, False),
        ("骨盆重建", "GYN_PELVIC_FLOOR_DYSFUNCTION", "synonym_keyword", 0.85, False),
        ("頻尿", "GYN_FREQUENT_URINATION", "exact_keyword", 0.95, False),
        ("急尿", "GYN_FREQUENT_URINATION", "exact_keyword", 0.95, False),
        ("尿路感染", "GYN_URINARY_TRACT_INFECTION", "exact_keyword", 0.95, False),
        ("泌尿道感染", "GYN_URINARY_TRACT_INFECTION", "synonym_keyword", 0.85, False),
        ("間質性膀胱炎", "GYN_INTERSTITIAL_CYSTITIS", "exact_keyword", 0.95, False),
        ("更年期", "GYN_MENOPAUSE", "exact_keyword", 0.95, False),
        ("避孕", "GYN_CONTRACEPTION", "exact_keyword", 0.95, False),
        ("優生保健", "GYN_CONTRACEPTION", "synonym_keyword", 0.85, False),
        ("產前檢查", "GYN_PREGNANCY_CARE", "exact_keyword", 0.95, False),
        ("一般產檢", "GYN_PREGNANCY_CARE", "exact_keyword", 0.95, False),
        ("產檢", "GYN_PREGNANCY_CARE", "exact_keyword", 0.95, False),
        ("自然生產", "GYN_PREGNANCY_CARE", "exact_keyword", 0.95, False),
        ("剖腹生產", "GYN_PREGNANCY_CARE", "exact_keyword", 0.95, False),
        ("高危險妊娠", "GYN_HIGH_RISK_PREGNANCY", "exact_keyword", 0.95, False),
        ("高危妊娠", "GYN_HIGH_RISK_PREGNANCY", "synonym_keyword", 0.85, False),
        ("產前遺傳諮詢", "GYN_PRENATAL_GENETIC_COUNSELING", "exact_keyword", 0.95, False),
        ("產前基因遺傳諮詢", "GYN_PRENATAL_GENETIC_COUNSELING", "exact_keyword", 0.95, False),
        ("產前優生遺傳諮詢", "GYN_PRENATAL_GENETIC_COUNSELING", "exact_keyword", 0.95, False),
        ("羊膜穿刺", "GYN_PRENATAL_GENETIC_COUNSELING", "exact_keyword", 0.95, False),
        ("絨毛膜取樣", "GYN_PRENATAL_GENETIC_COUNSELING", "exact_keyword", 0.95, False),
        ("唐氏症篩檢", "GYN_PRENATAL_GENETIC_COUNSELING", "exact_keyword", 0.95, False),
        ("高層次超音波", "GYN_FETAL_ULTRASOUND", "exact_keyword", 0.95, False),
        ("胎兒心臟超音波", "GYN_FETAL_ULTRASOUND", "exact_keyword", 0.95, False),
        ("不孕症", "GYN_INFERTILITY", "exact_keyword", 0.95, False),
        ("人工生殖", "GYN_ASSISTED_REPRODUCTION", "exact_keyword", 0.95, False),
        ("人工受孕", "GYN_ASSISTED_REPRODUCTION", "exact_keyword", 0.95, False),
        ("人工授精", "GYN_ASSISTED_REPRODUCTION", "synonym_keyword", 0.85, False),
        ("胚胎植入", "GYN_ASSISTED_REPRODUCTION", "exact_keyword", 0.95, False),
        ("取卵", "GYN_ASSISTED_REPRODUCTION", "exact_keyword", 0.95, False),
        ("排卵誘導", "GYN_ASSISTED_REPRODUCTION", "exact_keyword", 0.95, False),
        ("試管嬰兒", "GYN_IVF", "exact_keyword", 0.95, False),
        ("生殖內分泌", "GYN_REPRODUCTIVE_ENDOCRINOLOGY", "exact_keyword", 0.95, False),
        ("內分泌異常", "GYN_REPRODUCTIVE_ENDOCRINOLOGY", "synonym_keyword", 0.85, False),
        ("多囊性卵巢", "GYN_PCOS", "exact_keyword", 0.95, False),
        ("多囊性卵囊", "GYN_PCOS", "synonym_keyword", 0.85, False),
        ("月經失調", "GYN_MENSTRUAL_DISORDER", "exact_keyword", 0.95, False),
        ("子宮內膜異位", "GYN_ENDOMETRIOSIS", "exact_keyword", 0.95, False),
        ("巧克力囊腫", "GYN_ENDOMETRIOSIS", "synonym_keyword", 0.85, False),
        ("子宮肌瘤", "GYN_UTERINE_FIBROIDS", "exact_keyword", 0.95, False),
        ("肌瘤", "GYN_UTERINE_FIBROIDS", "synonym_keyword", 0.85, False),
        ("子宮肌腺症", "GYN_ADENOMYOSIS", "exact_keyword", 0.95, False),
        ("子宮肌腺瘤", "GYN_ADENOMYOSIS", "exact_keyword", 0.95, False),
        ("腺瘤", "GYN_ADENOMYOSIS", "synonym_keyword", 0.85, False),
        ("卵巢腫瘤", "GYN_OVARIAN_TUMOR", "exact_keyword", 0.95, False),
        ("卵巢瘤", "GYN_OVARIAN_TUMOR", "exact_keyword", 0.95, False),
        ("卵巢囊腫", "GYN_OVARIAN_TUMOR", "exact_keyword", 0.95, False),
        ("婦科癌症", "GYN_GYNECOLOGIC_ONCOLOGY", "exact_keyword", 0.95, False),
        ("婦癌", "GYN_GYNECOLOGIC_ONCOLOGY", "exact_keyword", 0.95, False),
        ("婦科腫瘤", "GYN_GYNECOLOGIC_ONCOLOGY", "exact_keyword", 0.95, False),
        ("子宮頸癌", "GYN_CERVICAL_CANCER", "exact_keyword", 0.95, False),
        ("子宮內膜癌", "GYN_ENDOMETRIAL_CANCER", "exact_keyword", 0.95, False),
        ("卵巢癌", "GYN_OVARIAN_CANCER", "exact_keyword", 0.95, False),
        ("人類乳突病毒", "GYN_HPV", "exact_keyword", 0.95, False),
        ("人類乳狀病毒", "GYN_HPV", "synonym_keyword", 0.85, False),
        ("HPV", "GYN_HPV", "synonym_keyword", 0.85, False),
        ("化療", "GYN_CHEMOTHERAPY", "exact_keyword", 0.95, False),
        ("化學治療", "GYN_CHEMOTHERAPY", "exact_keyword", 0.95, False),
        ("免疫治療", "GYN_IMMUNOTHERAPY", "synonym_keyword", 0.85, False),
        ("免疫療法", "GYN_IMMUNOTHERAPY", "synonym_keyword", 0.85, False),
        ("微創", "GYN_MINIMALLY_INVASIVE_SURGERY", "exact_keyword", 0.95, False),
        ("腹腔鏡", "GYN_LAPAROSCOPIC_SURGERY", "exact_keyword", 0.95, False),
        ("子宮鏡", "GYN_HYSTEROSCOPY", "exact_keyword", 0.95, False),
        ("子宮腔鏡", "GYN_HYSTEROSCOPY", "synonym_keyword", 0.85, False),
        ("速潔刀", "GYN_HYSTEROSCOPY", "synonym_keyword", 0.85, False),
        ("達文西", "GYN_ROBOTIC_SURGERY", "exact_keyword", 0.95, False),
        ("海扶刀", "GYN_HIFU", "exact_keyword", 0.95, False),
        ("消融", "GYN_HIFU", "synonym_keyword", 0.85, False),
        ("血液病", "HEME_HEMATOLOGY", "exact_keyword", 0.95, False),
        ("血液疾病", "HEME_HEMATOLOGY", "exact_keyword", 0.95, False),
        ("內科", "HEME_GENERAL_INTERNAL_MEDICINE", "inferred_from_phrase", 0.70, True),
        ("淋巴瘤", "HEME_LYMPHOMA", "exact_keyword", 0.95, False),
        ("白血病", "HEME_LEUKEMIA", "exact_keyword", 0.95, False),
        ("血癌", "HEME_LEUKEMIA", "synonym_keyword", 0.85, False),
        ("貧血", "HEME_ANEMIA", "exact_keyword", 0.95, False),
        ("血友病", "HEME_HEMOPHILIA", "exact_keyword", 0.95, False),
        ("血液幹細胞移植", "HEME_STEM_CELL_TRANSPLANT", "exact_keyword", 0.95, False),
        ("骨髓移植", "HEME_STEM_CELL_TRANSPLANT", "synonym_keyword", 0.85, False),
        ("感染醫學", "ID_INFECTIOUS_DISEASE", "exact_keyword", 0.95, False),
        ("感染管制", "ID_INFECTIOUS_DISEASE", "exact_keyword", 0.95, False),
        ("感染症", "ID_INFECTIOUS_DISEASE", "exact_keyword", 0.95, False),
        ("愛滋", "ID_HIV", "exact_keyword", 0.95, False),
        ("後天免疫不全", "ID_HIV", "synonym_keyword", 0.85, False),
        ("HIV", "ID_HIV", "synonym_keyword", 0.85, False),
        ("分枝桿菌", "ID_MYCOBACTERIAL_INFECTION", "exact_keyword", 0.95, False),
        ("微生物感染", "ID_MICROBIAL_INFECTION", "exact_keyword", 0.95, False),
        ("免疫學", "ID_INFECTIOUS_DISEASE", "inferred_from_phrase", 0.70, True),
        ("肝膿瘍", "ID_LIVER_ABSCESS", "exact_keyword", 0.95, False),
        ("克雷白氏菌", "ID_LIVER_ABSCESS", "synonym_keyword", 0.85, False),
        ("內科疾病", "ID_GENERAL_INTERNAL_MEDICINE", "exact_keyword", 0.95, False),
        ("發燒", "ID_FEVER", "exact_keyword", 0.95, False),
        ("發熱", "ID_FEVER", "synonym_keyword", 0.85, False),
        ("泌尿道感染", "ID_URINARY_TRACT_INFECTION", "exact_keyword", 0.95, False),
        ("尿路感染", "ID_URINARY_TRACT_INFECTION", "synonym_keyword", 0.85, False),
        ("腎臟", "NEPHRO_NEPHROLOGY", "exact_keyword", 0.95, False),
        ("腎臟疾病", "NEPHRO_NEPHROLOGY", "exact_keyword", 0.95, False),
        ("慢性腎臟", "NEPHRO_CKD", "exact_keyword", 0.95, False),
        ("急慢性腎臟疾病", "NEPHRO_CKD", "exact_keyword", 0.95, False),
        ("急性腎", "NEPHRO_AKI", "exact_keyword", 0.95, False),
        ("血液透析", "NEPHRO_HEMODIALYSIS", "exact_keyword", 0.95, False),
        ("洗腎", "NEPHRO_HEMODIALYSIS", "synonym_keyword", 0.85, False),
        ("腹膜透析", "NEPHRO_PERITONEAL_DIALYSIS", "exact_keyword", 0.95, False),
        ("腎臟移植", "NEPHRO_KIDNEY_TRANSPLANT", "exact_keyword", 0.95, False),
        ("糖尿病腎", "NEPHRO_DIABETIC_KIDNEY_DISEASE", "exact_keyword", 0.95, False),
        ("高血壓腎", "NEPHRO_HYPERTENSION_KIDNEY_DISEASE", "exact_keyword", 0.95, False),
        ("高血壓", "NEPHRO_HYPERTENSION_KIDNEY_DISEASE", "inferred_from_phrase", 0.70, True),
        ("腎纖維化", "NEPHRO_KIDNEY_FIBROSIS", "exact_keyword", 0.95, False),
        ("腫瘤學", "ONCO_ONCOLOGY", "exact_keyword", 0.95, False),
        ("固體腫瘤", "ONCO_ONCOLOGY", "exact_keyword", 0.95, False),
        ("癌症治療", "ONCO_ONCOLOGY", "exact_keyword", 0.95, False),
        ("內科", "ONCO_GENERAL_INTERNAL_MEDICINE", "inferred_from_phrase", 0.70, True),
        ("腸胃道腫瘤", "ONCO_GI_CANCER", "exact_keyword", 0.95, False),
        ("大腸直腸癌", "ONCO_GI_CANCER", "exact_keyword", 0.95, False),
        ("乳癌", "ONCO_BREAST_CANCER", "exact_keyword", 0.95, False),
        ("泌尿道腫瘤", "ONCO_UROLOGIC_CANCER", "exact_keyword", 0.95, False),
        ("泌尿道癌", "ONCO_UROLOGIC_CANCER", "synonym_keyword", 0.85, False),
        ("肺癌", "ONCO_LUNG_CANCER", "exact_keyword", 0.95, False),
        ("頭頸癌", "ONCO_HEAD_AND_NECK_CANCER", "exact_keyword", 0.95, False),
        ("食道癌", "ONCO_ESOPHAGEAL_CANCER", "exact_keyword", 0.95, False),
        ("肝癌", "ONCO_LIVER_CANCER", "exact_keyword", 0.95, False),
        ("神經內分泌瘤", "ONCO_NEUROENDOCRINE_TUMOR", "exact_keyword", 0.95, False),
        ("黑色素癌", "ONCO_MELANOMA", "exact_keyword", 0.95, False),
        ("黑色素瘤", "ONCO_MELANOMA", "synonym_keyword", 0.85, False),
        ("免疫腫瘤", "ONCO_IMMUNO_ONCOLOGY", "exact_keyword", 0.95, False),
        ("免疫治療", "ONCO_IMMUNO_ONCOLOGY", "synonym_keyword", 0.85, False),
        ("安寧療護", "ONCO_PALLIATIVE_CARE", "exact_keyword", 0.95, False),
        ("風濕", "RHEUM_RHEUMATOLOGY", "exact_keyword", 0.95, False),
        ("內科", "RHEUM_GENERAL_INTERNAL_MEDICINE", "inferred_from_phrase", 0.70, True),
        ("自體免疫", "RHEUM_AUTOIMMUNE_DISEASE", "exact_keyword", 0.95, False),
        ("痛風", "RHEUM_GOUT", "exact_keyword", 0.95, False),
        ("高尿酸", "RHEUM_GOUT", "exact_keyword", 0.95, False),
        ("類風濕", "RHEUM_RHEUMATOID_ARTHRITIS", "exact_keyword", 0.95, False),
        ("紅斑性狼瘡", "RHEUM_LUPUS", "exact_keyword", 0.95, False),
        ("狼瘡", "RHEUM_LUPUS", "synonym_keyword", 0.85, False),
        ("僵直性脊椎炎", "RHEUM_ANKYLOSING_SPONDYLITIS", "exact_keyword", 0.95, False),
        ("下背痛脊椎炎", "RHEUM_ANKYLOSING_SPONDYLITIS", "synonym_keyword", 0.85, False),
        ("過敏", "RHEUM_ALLERGY", "exact_keyword", 0.95, False),
        ("氣喘", "RHEUM_ALLERGY", "inferred_from_phrase", 0.70, True),
    ]
)


def normalize_text(value):
    return re.sub(r"\s+", "", (value or "")).lower()


def first_present(row, names):
    for name in names:
        if name in row and row[name] is not None:
            return row[name].strip()
    return ""


def read_raw_doctors():
    rows = []
    for dataset in DATASETS:
        with dataset["path"].open(newline="", encoding="utf-8-sig") as csv_file:
            reader = csv.DictReader(csv_file)
            for index, row in enumerate(reader, start=1):
                name = first_present(row, ("姓名", "醫師姓名", "doctor_name", "doctor_name_zh", "name"))
                specialty = first_present(row, ("專長", "specialty", "specialty_raw_zh", "raw_specialty", "raw_specialty_text"))
                source_url = first_present(row, ("source_url", "url", "profile_url", "來源網址"))
                subdepartment = first_present(row, ("subdepartment_zh", "次專科", "科別")) or dataset["subdepartment_zh"]
                if not name and not specialty:
                    continue
                rows.append(
                    {
                        "doctor_id": f"{dataset['id_prefix']}_{index:03d}",
                        "doctor_name_zh": name,
                        "hospital_zh": HOSPITAL_ZH,
                        "department_zh": dataset["department_zh"],
                        "subdepartment_zh": subdepartment,
                        "specialty_raw_zh": specialty,
                        "source_url": source_url,
                    }
                )
    return rows


def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_rule_table():
    concept_by_id = {item["concept_id"]: item for item in CONCEPTS}
    rules = []
    seen = set()
    for keyword, concept_id, match_type, confidence, needs_review in MANUAL_RULES:
        key = (normalize_text(keyword), concept_id)
        if key in seen:
            continue
        if concept_id not in concept_by_id:
            raise ValueError(f"Rule references unknown concept_id: {concept_id}")
        rules.append(
            {
                "keyword": keyword,
                "keyword_norm": normalize_text(keyword),
                "concept_id": concept_id,
                "match_type": match_type,
                "confidence": confidence,
                "needs_review": needs_review,
            }
        )
        seen.add(key)
    return rules


def doctor_scope(doctor_id):
    for dataset in DATASETS:
        prefix = dataset["id_prefix"].replace("CGMH_LINKOU_", "", 1)
        if doctor_id.startswith(f"{dataset['id_prefix']}_"):
            return prefix
    return ""


def build_doctor_concept_map(doctors):
    concept_by_id = {item["concept_id"]: item for item in CONCEPTS}
    rules = build_rule_table()
    mappings_by_doctor_concept = {}

    for doctor in doctors:
        raw = doctor["specialty_raw_zh"]
        raw_norm = normalize_text(raw)
        scope = doctor_scope(doctor["doctor_id"])
        for rule in rules:
            concept_scope = rule["concept_id"].split("_", 1)[0]
            if concept_scope != scope:
                continue
            if rule["keyword_norm"] and rule["keyword_norm"] in raw_norm:
                key = (doctor["doctor_id"], rule["concept_id"])
                existing = mappings_by_doctor_concept.get(key)
                if existing and float(existing["confidence"]) >= rule["confidence"]:
                    continue
                concept_row = concept_by_id[rule["concept_id"]]
                mappings_by_doctor_concept[key] = {
                    "doctor_id": doctor["doctor_id"],
                    "doctor_name_zh": doctor["doctor_name_zh"],
                    "concept_id": rule["concept_id"],
                    "concept_name_zh": concept_row["canonical_name_zh"],
                    "source_phrase_zh": rule["keyword"],
                    "match_type": rule["match_type"],
                    "confidence": f"{rule['confidence']:.2f}",
                    "needs_review": "true" if rule["needs_review"] else "false",
                }

    return sorted(
        mappings_by_doctor_concept.values(),
        key=lambda row: (row["doctor_id"], row["concept_id"]),
    )


def print_quality_checks(doctors, concepts, mappings):
    mapped_doctor_ids = {row["doctor_id"] for row in mappings}
    mapped_concept_ids = {row["concept_id"] for row in mappings}
    zero_doctors = [row for row in doctors if row["doctor_id"] not in mapped_doctor_ids]
    zero_concepts = [row for row in concepts if row["concept_id"] not in mapped_concept_ids]
    review_mappings = [row for row in mappings if row["needs_review"] == "true"]

    mappings_by_doctor = defaultdict(int)
    for row in mappings:
        mappings_by_doctor[row["doctor_id"]] += 1

    print(f"number of doctors: {len(doctors)}")
    print(f"number of medical concepts: {len(concepts)}")
    print(f"number of doctor-concept mappings: {len(mappings)}")
    print(
        "doctors with zero mapped concepts: "
        + (
            ", ".join(f"{row['doctor_id']} {row['doctor_name_zh']}" for row in zero_doctors)
            if zero_doctors
            else "none"
        )
    )
    print(
        "concepts with zero mapped doctors: "
        + (
            ", ".join(row["concept_id"] for row in zero_concepts)
            if zero_concepts
            else "none"
        )
    )
    print(f"mappings marked needs_review=true: {len(review_mappings)}")


def main():
    doctors = read_raw_doctors()
    mappings = build_doctor_concept_map(doctors)
    concepts = sorted(CONCEPTS, key=lambda row: row["concept_id"])

    write_csv(DOCTORS_NORMALIZED_CSV, doctors, DOCTOR_COLUMNS)
    write_csv(MEDICAL_CONCEPTS_CSV, concepts, CONCEPT_COLUMNS)
    write_csv(DOCTOR_CONCEPT_MAP_CSV, mappings, MAP_COLUMNS)
    print_quality_checks(doctors, concepts, mappings)


if __name__ == "__main__":
    main()
