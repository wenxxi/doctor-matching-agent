from pathlib import Path

import pandas as pd

url = "https://www.cgmh.org.tw/tw/Services/DeptInfo/3/4A000/4AW00"
output_path = Path("data/raw/cgmh_linkou_pediatric_doctors.csv")

tables = pd.read_html(url)
df = None

for table in tables:
    if "醫師姓名" in table.columns and "專長" in table.columns:
        df = table[["醫師姓名", "專長"]].copy()
        break

df = df.dropna(subset=["醫師姓名", "專長"])

file_exists = output_path.exists()
df.to_csv(
    output_path,
    mode="a" if file_exists else "w",
    header=not file_exists,
    index=False,
    encoding="utf-8-sig",
)

print(df.head())