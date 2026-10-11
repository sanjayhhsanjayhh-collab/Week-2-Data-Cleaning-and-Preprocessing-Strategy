# Week 2 — Data Cleaning and Preprocessing Strategy

Student: SANJAY H H  
USN: 1MJ24CD041  
5th Semester, CSE — Data Science  
MVJ College of Engineering, Bengaluru

## Files
- `Week_2_Data_Cleaning_Preprocessing_Strategy_Sanjay_HH.docx` — final editable report
- `Week_2_Data_Cleaning_Preprocessing_Strategy_Sanjay_HH.pdf` — printable report (created after rendering)
- `hypothetical_agri_raw.csv` — deliberately messy **synthetic** example data; not real farm data
- `clean_agri_data.py` — reproducible pandas processing script
- `cleaned_agri_example.csv` — example standardized output with quality flags
- `quality_issues_log.csv` — row/field issue log with proposed actions
- `preprocessing_workflow.png` — visual workflow included in the report

## Re-run
Python 3.10+ recommended. Install pandas: `python -m pip install pandas`.
Run: `python clean_agri_data.py`
This re-creates the cleaned sample and issue log in this directory. The raw file is not overwritten.

## Important assumptions
All rows and values in the CSV are hypothetical. The script demonstrates the strategy, not universal production rules. In particular, the yield thresholds are demonstration flags only. Real use requires crop-/region-specific definitions, verified source units and domain rules, and careful review of flagged observations.
