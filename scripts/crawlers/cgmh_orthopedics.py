import pandas as pd

url = "https://www.cgmh.org.tw/tw/Systems/BranchInfo/3/32700"

tables = pd.read_html(url)
df = None

for table in tables:
    if "姓名" in table.columns and "專長" in table.columns:
        df = table[["姓名", "專長"]].copy()
        break

df = df.dropna(subset=["姓名", "專長"])
df.to_csv("data/raw/cgmh_linkou_orthopedics_doctors.csv", index=False, encoding="utf-8-sig")

print(df.head())