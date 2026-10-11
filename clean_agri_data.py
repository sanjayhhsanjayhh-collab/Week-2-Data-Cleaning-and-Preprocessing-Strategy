"""Clean a deliberately messy hypothetical agribusiness CSV.

This script demonstrates the proposed strategy; it is not a universal cleaner for
all crops or states. It preserves a raw copy, standardizes common units, keeps
quality flags, and does not silently drop suspicious observations.
Run: python clean_agri_data.py
Requires: pandas (pip install pandas)
"""
from pathlib import Path
import pandas as pd
import numpy as np

BASE = Path(__file__).resolve().parent
INPUT = BASE / "hypothetical_agri_raw.csv"
OUTPUT = BASE / "cleaned_agri_example.csv"
ISSUES = BASE / "quality_issues_log.csv"

raw = pd.read_csv(INPUT)
df = raw.copy(deep=True)  # preserve raw source separately; never overwrite it
issues = []

def add_issue(record_id, field, issue, action):
    issues.append({"Record_ID": record_id, "Field": field, "Issue": issue, "Action_or_Status": action})

# Trim whitespace and normalize text case through explicit dictionaries.
for col in ["Farm_ID", "District", "Crop", "Season", "Area_Unit", "Production_Unit", "Price_Unit"]:
    df[col] = df[col].astype("string").str.strip()

df["District"] = df["District"].replace({"Davanagere": "Davangere"})
df["Crop"] = df["Crop"].str.title().replace({"<NA>": pd.NA, "Nan": pd.NA})
df["Season"] = df["Season"].str.title()
df["Area_Unit"] = df["Area_Unit"].str.lower()
df["Production_Unit"] = df["Production_Unit"].str.lower()

# Parse source date formats; invalid values become NaT and are logged, not guessed.
df["Observation_Date_Parsed"] = pd.to_datetime(df["Observation_Date"], format="mixed", dayfirst=True, errors="coerce")
for idx in df.index[df["Observation_Date_Parsed"].isna()]:
    add_issue(df.loc[idx, "Record_ID"], "Observation_Date", "Invalid or unparseable date", "Retain with flag; exclude from time-series analysis until verified")

# Numeric coercion makes malformed strings visible as missing values.
num_cols = ["Area_Value", "Production_Value", "Reported_Yield_t_ha", "Rainfall_mm", "Farmgate_Price_Value", "Fertilizer_kg_ha"]
for col in num_cols:
    df[col + "_raw"] = df[col]
    df[col] = pd.to_numeric(df[col], errors="coerce")
    bad = df[col].isna() & df[col + "_raw"].notna()
    for idx in df.index[bad]:
        add_issue(df.loc[idx, "Record_ID"], col, "Non-numeric value", "Set parsed value to missing; request source correction")

# Unit conversions: area -> ha, production -> tonnes, price -> INR per quintal.
area_factor = {"ha": 1.0, "hectare": 1.0, "hectares": 1.0, "acre": 0.404686, "acres": 0.404686}
prod_factor = {"tonne": 1.0, "tonnes": 1.0, "t": 1.0, "kg": 0.001, "kilogram": 0.001, "kilograms": 0.001}
price_factor = {"inr/quintal": 1.0, "rs/quintal": 1.0, "inr/kg": 100.0, "rs/kg": 100.0}

def factor(row, unit_col, mapping, record_id, field):
    unit = str(row[unit_col]).strip().lower()
    if unit in mapping:
        return mapping[unit]
    add_issue(record_id, unit_col, f"Unrecognized unit: {unit}", "Leave standardized field missing; verify source unit")
    return np.nan

df["Area_ha"] = [v * factor(row, "Area_Unit", area_factor, row["Record_ID"], "Area_ha") if pd.notna(v) else np.nan for (_, row), v in zip(df.iterrows(), df["Area_Value"])]
df["Production_t"] = [v * factor(row, "Production_Unit", prod_factor, row["Record_ID"], "Production_t") if pd.notna(v) else np.nan for (_, row), v in zip(df.iterrows(), df["Production_Value"])]
df["Price_INR_quintal"] = [v * factor(row, "Price_Unit", price_factor, row["Record_ID"], "Price_INR_quintal") if pd.notna(v) else np.nan for (_, row), v in zip(df.iterrows(), df["Farmgate_Price_Value"])]

# Duplicate business event check after date and category normalization.
# The key is illustrative; production systems must select a key matching their data grain.
df["Duplicate_Business_Key"] = df.duplicated(subset=["Farm_ID", "Observation_Date_Parsed", "Crop", "Season"], keep="first")
for idx in df.index[df["Duplicate_Business_Key"]]:
    add_issue(df.loc[idx, "Record_ID"], "Record", "Repeated farm-date-crop-season key", "Flag duplicate; retain in output for traceability; exclude from analytical copy after review")

# Domain and cross-field validation.
df["Quality_Flags"] = ""
def flag(idx, value):
    current = df.at[idx, "Quality_Flags"]
    df.at[idx, "Quality_Flags"] = (current + "; " if current else "") + value
for idx, row in df.iterrows():
    if pd.isna(row["Crop"]):
        flag(idx, "Missing crop")
        add_issue(row["Record_ID"], "Crop", "Missing category", "Do not infer crop by mode; exclude from crop-specific analysis until resolved")
    if pd.notna(row["Area_ha"]) and row["Area_ha"] < 0:
        flag(idx, "Negative area")
        add_issue(row["Record_ID"], "Area_ha", "Negative area", "Reject from analysis pending correction")
    if pd.notna(row["Area_ha"]) and row["Area_ha"] == 0 and pd.notna(row["Production_t"]) and row["Production_t"] > 0:
        flag(idx, "Zero area with positive production")
        add_issue(row["Record_ID"], "Area_ha/Production_t", "Logical inconsistency", "Do not calculate yield; verify area and production source")
    if pd.notna(row["Rainfall_mm"]) and row["Rainfall_mm"] < 0:
        flag(idx, "Negative rainfall")
        add_issue(row["Record_ID"], "Rainfall_mm", "Outside physical domain", "Set analytical rainfall to missing pending source correction; retain raw value in raw file")
    if pd.notna(row["Fertilizer_kg_ha"]) and row["Fertilizer_kg_ha"] < 0:
        flag(idx, "Negative fertilizer intensity")
        add_issue(row["Record_ID"], "Fertilizer_kg_ha", "Outside physical domain", "Verify source value")
    if pd.notna(row["Reported_Yield_t_ha"]) and row["Reported_Yield_t_ha"] > 20:
        flag(idx, "Yield exceeds demo review threshold")
        add_issue(row["Record_ID"], "Reported_Yield_t_ha", "Potential outlier (>20 t/ha demo threshold)", "Review against crop, units and source; threshold is illustrative, not universal")

# Treat physically impossible rainfall as missing in the analysis field only.
# The raw file remains unchanged for audit.
df["Rainfall_mm"] = df["Rainfall_mm"].mask(df["Rainfall_mm"] < 0, np.nan)

# Derive yield only when its inputs pass basic checks. Never divide by zero.
valid_inputs = df["Area_ha"].gt(0) & df["Production_t"].ge(0) & df["Area_ha"].notna() & df["Production_t"].notna()
df["Calculated_Yield_t_ha"] = np.where(valid_inputs, df["Production_t"] / df["Area_ha"], np.nan)
# A large discrepancy is a review flag, not grounds for automatic deletion.
compare = df["Reported_Yield_t_ha"].notna() & df["Calculated_Yield_t_ha"].notna() & df["Calculated_Yield_t_ha"].ne(0)
df["Yield_Discrepancy_Pct"] = np.where(compare, 100 * abs(df["Reported_Yield_t_ha"] - df["Calculated_Yield_t_ha"]) / abs(df["Calculated_Yield_t_ha"]), np.nan)
for idx in df.index[df["Yield_Discrepancy_Pct"] > 10]:
    flag(idx, "Reported/calculated yield discrepancy >10%")
    add_issue(df.loc[idx, "Record_ID"], "Yield", "Reported and calculated yield differ by >10%", "Verify units and source; keep both values and document chosen analytical value")

# Missing rainfall: demonstrative crop-season median imputation only when possible.
# A production use case should first look for a nearby validated weather station.
df["Rainfall_Was_Missing"] = df["Rainfall_mm"].isna()
medians = df.groupby(["Crop", "Season"], dropna=True)["Rainfall_mm"].transform("median")
fill = df["Rainfall_mm"].isna() & medians.notna()
df.loc[fill, "Rainfall_mm"] = medians[fill]
for idx in df.index[fill]:
    flag(idx, "Rainfall imputed by crop-season median (demo)")
    add_issue(df.loc[idx, "Record_ID"], "Rainfall_mm", "Missing weather value", "Filled by crop-season median for demonstration; replace with station data if available")
for idx in df.index[df["Rainfall_mm"].isna() & df["Rainfall_Was_Missing"]]:
    add_issue(df.loc[idx, "Record_ID"], "Rainfall_mm", "Missing/unresolved weather value", "No valid crop-season median available; retrieve verified weather data or retain missing")
for idx in df.index[df["Reported_Yield_t_ha"].isna()]:
    add_issue(df.loc[idx, "Record_ID"], "Reported_Yield_t_ha", "Source yield missing", "Keep reported field missing; derive a separate yield only when valid area and production are available")

# Do not impute missing outcome/target columns such as production; keep a training eligibility flag.
df["Eligible_For_Time_Series"] = df["Observation_Date_Parsed"].notna() & df["Crop"].notna() & ~df["Duplicate_Business_Key"]
df["Eligible_For_Yield_Model"] = df["Eligible_For_Time_Series"] & df["Calculated_Yield_t_ha"].notna() & df["Quality_Flags"].fillna("").str.contains("Zero area|Yield exceeds|Missing crop", case=False, regex=True).eq(False)

# Generate an issue log and a compact cleaned sample; keep raw file intact.
issue_df = pd.DataFrame(issues, columns=["Record_ID", "Field", "Issue", "Action_or_Status"])
issue_df.to_csv(ISSUES, index=False)
keep = ["Record_ID","Farm_ID","Observation_Date_Parsed","District","Crop","Season","Area_ha","Production_t","Reported_Yield_t_ha","Calculated_Yield_t_ha","Yield_Discrepancy_Pct","Rainfall_mm","Rainfall_Was_Missing","Price_INR_quintal","Fertilizer_kg_ha","Duplicate_Business_Key","Quality_Flags","Eligible_For_Time_Series","Eligible_For_Yield_Model"]
df[keep].to_csv(OUTPUT, index=False)
print(f"Input rows: {len(raw)} | Output rows retained with flags: {len(df)} | Issue-log entries: {len(issue_df)}")
print(f"Wrote {OUTPUT.name} and {ISSUES.name}")
