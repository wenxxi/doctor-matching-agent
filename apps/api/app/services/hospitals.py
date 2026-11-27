ALIASES = {
    "林口長庚": "林口長庚", "林口長庚紀念醫院": "林口長庚",
    "台北榮總": "台北榮總", "臺北榮總": "台北榮總", "榮總": "台北榮總", "北榮": "台北榮總", "臺北榮民總醫院": "台北榮總",
    "Taipei Veterans General Hospital": "台北榮總", "兩院皆可": "兩院皆可", "醫院不限": "兩院皆可",
}


def matches_hospital(doctor, hospital):
    selected = ALIASES.get(hospital, hospital)
    if selected == "兩院皆可" or hospital is None:
        return True
    expected = {"林口長庚": "林口長庚紀念醫院", "台北榮總": "臺北榮民總醫院"}.get(selected)
    return doctor["hospital_zh"] == expected
