#!/usr/bin/env python3
import csv
import re
from collections import defaultdict
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
RAW_CSV = ROOT_DIR / "data" / "raw" / "cgmh_linkou_orthopedics_doctors.csv"
PROCESSED_DIR = ROOT_DIR / "data" / "processed"
DOCTORS_NORMALIZED_CSV = PROCESSED_DIR / "doctors_normalized.csv"
MEDICAL_CONCEPTS_CSV = PROCESSED_DIR / "medical_concepts.csv"
DOCTOR_CONCEPT_MAP_CSV = PROCESSED_DIR / "doctor_concept_map.csv"

SOURCE = "cgmh_orthopedics_scrape_manual_v1"
HOSPITAL_ZH = "林口長庚紀念醫院"
DEPARTMENT_ZH = "骨科部"

DOCTOR_COLUMNS = [
    "doctor_id",
    "doctor_name_zh",
    "hospital_zh",
    "department_zh",
    "subdepartment_zh",
    "specialty_raw_zh",
    "source_url",
    "notes",
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
    "is_patient_facing",
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
    "needs_review",
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
    patient=True,
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
        "is_patient_facing": "true" if patient else "false",
        "source": SOURCE,
    }


CONCEPTS = [
    concept("ORTHO_ORTHOPEDICS", "骨科", "Orthopedics", "subspecialty", lay_terms_zh=("骨科一般疾病",), description_zh="骨骼、關節、肌肉與韌帶相關疾病與外傷。"),
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
    concept("ORTHO_MENISCUS_INJURY", "半月板損傷", "Meniscus injury", "disease_or_condition", "ORTHO_SPORTS_MEDICINE", synonyms_zh=("半月軟骨損傷",), lay_terms_zh=("膝蓋半月板受傷",), description_zh="膝關節半月板撕裂或退化。"),
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
    concept("ORTHO_FOOT_ANKLE", "足踝疾病", "Foot and ankle disorders", "subspecialty", synonyms_zh=("足踝病變", "足踝疾患", "足踝關節重建"), lay_terms_zh=("腳踝問題", "足踝問題"), description_zh="足部與踝關節疾病、變形或外傷。"),
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
    concept("ORTHO_FRACTURE_FIXATION", "骨折固定手術", "Fracture fixation", "procedure", "ORTHO_FRACTURE", synonyms_zh=("骨折重建手術", "骨折外傷手術", "骨折外傷微創手術"), lay_terms_zh=("骨折開刀固定",), description_zh="使用鋼板、鋼釘、螺絲或其他方式固定骨折。"),
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
    ("肘", "ORTHO_ELBOW", "exact_keyword", 0.95, False),
    ("腕", "ORTHO_WRIST", "exact_keyword", 0.95, False),
    ("手部", "ORTHO_HAND", "exact_keyword", 0.95, False),
    ("手外科", "ORTHO_HAND", "synonym_keyword", 0.85, False),
    ("髖", "ORTHO_HIP", "exact_keyword", 0.95, False),
    ("膝", "ORTHO_KNEE", "exact_keyword", 0.95, False),
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


def normalize_text(value):
    return re.sub(r"\s+", "", (value or "")).lower()


def first_present(row, names):
    for name in names:
        if name in row and row[name] is not None:
            return row[name].strip()
    return ""


def read_raw_doctors():
    with RAW_CSV.open(newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        rows = []
        for index, row in enumerate(reader, start=1):
            name = first_present(row, ("姓名", "doctor_name", "doctor_name_zh", "name"))
            specialty = first_present(row, ("專長", "specialty", "specialty_raw_zh", "raw_specialty", "raw_specialty_text"))
            source_url = first_present(row, ("source_url", "url", "profile_url", "來源網址"))
            subdepartment = first_present(row, ("subdepartment_zh", "次專科", "科別")) or DEPARTMENT_ZH
            notes = first_present(row, ("notes", "備註"))
            if not name and not specialty:
                continue
            rows.append(
                {
                    "doctor_id": f"CGMH_LINKOU_ORTHO_{index:03d}",
                    "doctor_name_zh": name,
                    "hospital_zh": HOSPITAL_ZH,
                    "department_zh": DEPARTMENT_ZH,
                    "subdepartment_zh": subdepartment,
                    "specialty_raw_zh": specialty,
                    "source_url": source_url,
                    "notes": notes,
                }
            )
        return rows


def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
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


def build_doctor_concept_map(doctors):
    concept_by_id = {item["concept_id"]: item for item in CONCEPTS}
    rules = build_rule_table()
    mappings_by_doctor_concept = {}

    for doctor in doctors:
        raw = doctor["specialty_raw_zh"]
        raw_norm = normalize_text(raw)
        for rule in rules:
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
