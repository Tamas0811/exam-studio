"""Builds the question bank for Exam Studio Oral from the original course files.

Every answer that can be checked is computed here from the same files students
download, so the "Check my answer" values and the examiner's model answers are
never typed in by hand.

Usage:  python3 tools/build_bank.py <folder with the course materials> <output folder>
The course folder must have the same layout as the ExamStudio materials
(Excel part 1..4, SQL part 1..2).
"""
import json, os, re, sqlite3, sys, random, zipfile, shutil
import numpy as np
import pandas as pd

SRC, OUT = sys.argv[1], sys.argv[2]
FILES = os.path.join(OUT, "files")
os.makedirs(FILES, exist_ok=True)

# ---------------------------------------------------------------------------
# Key points: what an examiner wants to hear when you explain your work.
# Each has keywords (used by the offline examiner) and a nudge question
# (asked once if the student is on the right track but misses the point).
# ---------------------------------------------------------------------------
def kp(text, keywords, hint):
    return {"text": text, "keywords": keywords, "hint": hint}

K = {
 "import_csv": kp("Imports the file as delimited text (Data > From Text/CSV) with comma as the delimiter",
     ["delimit", "comma", "from text", "import", "power query", "text import", "csv"],
     "When you opened the .txt file, how did Excel know where one column ends and the next begins?"),
 "import_pipe": kp("Recognises that the file is pipe-delimited even though it is called .csv, and sets | as the delimiter",
     ["pipe", "|", "vertical", "delimit", "other"],
     "Open the file in a text editor. Which character actually separates the fields?"),
 "qualifier": kp("Text qualifiers (double quotes) stop commas inside a field from splitting it into extra columns",
     ["quote", "qualifier", "quotation", "\""],
     "Some fields contain commas themselves. Why don't they spill over into new columns?"),
 "dates": kp("Dates are converted to real Excel dates in US month/day/year order, not left as text",
     ["date", "month", "us format", "mdy", "locale", "serial", "datevalue", "text to date"],
     "The file uses 7/18/2016. What could go wrong if your computer expects day/month?"),
 "filter_two": kp("Applies both conditions at the same time (event type and borough / year)",
     ["filter", "countifs", "averageifs", "and", "both", "criteria", "where", "condition"],
     "Which two conditions must a row meet to be included?"),
 "pivot": kp("Uses a pivot table or COUNTIFS/SUMIFS to summarise by group",
     ["pivot", "countifs", "sumifs", "averageifs", "group", "summar"],
     "Which Excel tool summarises many rows into one number per group?"),
 "duration": kp("Duration = EndDateTime − StartDateTime; Excel stores time in days, so multiply by 24 for hours",
     ["24", "subtract", "minus", "end", "difference", "days"],
     "If you subtract two date-times in Excel, what unit is the result in?"),
 "text_search": kp("Case-insensitive 'contains' search: SEARCH/ISNUMBER, or COUNTIF with *BROADWAY* wildcards",
     ["search", "wildcard", "*", "isnumber", "contains", "like", "case"],
     "BROADWAY can appear anywhere in the text. How do you match part of a cell?"),
 "count_blank": kp("Counts truly empty cells (COUNTBLANK or a filter on blanks), separately from invalid values",
     ["blank", "empty", "missing", "countblank", "null"],
     "What is the difference between a missing zip code and an invalid one?"),
 "validate": kp("Defines what 'valid' means (a 5-digit zip) and tests each value against that rule",
     ["5", "five", "digit", "len", "length", "valid", "rule"],
     "What does a valid US zip code look like?"),
 "leading_zero": kp("Codes such as 001 or zip codes must be stored as text so leading zeros are not lost",
     ["leading", "zero", "text", "001", "format"],
     "What happens to the code 001 if Excel treats it as a number?"),
 "extract": kp("Splits the combined code with LEFT/MID/RIGHT/FIND (or text-to-columns / Flash Fill)",
     ["left", "mid", "right", "find", "text to column", "flash fill", "split", "extract"],
     "Which text functions would you use to pull pieces out of the code?"),
 "messy_extract": kp("Handles variable lengths: finds where letters end and digits start (FIND/MIN/ISNUMBER) instead of fixed positions",
     ["variable", "length", "find", "min", "isnumber", "position", "not fixed", "different length"],
     "Here 'Japan' and 'US' have different lengths. Why does LEFT(code,3) no longer work?"),
 "standardise": kp("Standardises inconsistent values (We→W, Mo→M; 'A M Z N'→AMZN) before counting",
     ["standard", "consistent", "clean", "replace", "trim", "same", "mo", "we"],
     "M and Mo mean the same thing. What do you do before counting them?"),
 "unique_key": kp("Builds a combined key (e.g. Location & '-' & PlantID) because a plant number alone is not unique",
     ["unique", "&", "concat", "combine", "key", "identifier"],
     "Plant 12 exists in several countries. How do you tell them apart?"),
 "lookup": kp("Joins the tables on a shared key with XLOOKUP/VLOOKUP/INDEX-MATCH (or a JOIN)",
     ["xlookup", "vlookup", "index", "match", "join", "lookup", "key", "merge"],
     "The account type is in another tab. How do you bring it next to each line?"),
 "join_type": kp("Thinks about rows without a match (left vs inner join) so nothing is silently dropped",
     ["left join", "inner", "no match", "missing", "#n/a", "dropped", "all rows"],
     "What happens to a journal line whose account number is not in the chart of accounts?"),
 "balance": kp("Uses double-entry logic: a journal entry balances when total debits equal total credits (Amount sums to zero)",
     ["debit", "credit", "balance", "zero", "equal", "double"],
     "In double-entry bookkeeping, what must be true for every journal entry?"),
 "agg_level": kp("Notices that 2015 and 2016 are recorded at different levels and brings both to a common level (job code) before comparing",
     ["level", "aggregat", "different system", "common", "same basis", "comparable", "job code"],
     "2015 has one row per pay date; 2016 has no dates. How do you make them comparable?"),
 "gross_def": kp("Uses the right definition of gross pay: Reg_Pay + OT_Pay in 2015 equals Gross_Wages in 2016",
     ["reg_pay", "ot_pay", "overtime", "gross", "regular", "sum"],
     "Gross_Wages exists only in 2016. What is the 2015 equivalent?"),
 "data_quality": kp("Flags data-quality problems (e.g. an invalid job code) instead of silently including them",
     ["invalid", "error", "outside", "quality", "check", "exception", "flag"],
     "Job codes must be 001 to 012. What do you do with a row that breaks that rule?"),
 "merge_dates": kp("Merges the sheets on date so every day has sales, weather and game information in one row",
     ["merge", "date", "lookup", "xlookup", "vlookup", "join", "combine"],
     "Sales, weather and games are in three sheets. What do they have in common?"),
 "daily_total": kp("Aggregates line items to one total per day before using it as the dependent variable",
     ["daily", "per day", "sum", "aggregat", "total", "pivot"],
     "The sales sheet has one row per menu item per day. What is one observation in your regression?"),
 "regression_tool": kp("Runs the regression with Data Analysis ToolPak (or LINEST) with the right Y and X ranges",
     ["toolpak", "data analysis", "linest", "regression", "y range", "x range"],
     "Which Excel tool produces the coefficient table?"),
 "coef_meaning": kp("Interprets the coefficient in units: change in daily sales for a one-unit change in X",
     ["per", "one", "increase", "unit", "dollar", "each", "degree"],
     "In plain words, what does that number mean for Bob?"),
 "significance": kp("Uses the p-value (below 0.05) to judge whether the effect is statistically significant",
     ["p-value", "p value", "signific", "0.05", "5%"],
     "How do you know whether that effect is real or just noise?"),
 "dummy": kp("Interprets a 0/1 dummy as the difference versus the reference group (non-game days)",
     ["dummy", "0", "1", "reference", "compared", "difference", "versus"],
     "Game day is either 0 or 1. Compared to what is the coefficient measured?"),
 "interaction": kp("Builds an interaction term (X × gameDay) and explains that it changes the slope on game days",
     ["interaction", "multiply", "×", "*", "product", "slope", "depends"],
     "How do you let last year's sales matter more on a game day?"),
 "sql_select": kp("SELECT only the needed columns FROM the right table",
     ["select", "from", "column", "table"],
     "Which table holds this information, and which columns do you return?"),
 "sql_where": kp("Filters rows with WHERE (correct operators, quotes around text)",
     ["where", "=", ">", "<", "and", "or", "between", "in ("],
     "How do you keep only the rows that meet the condition?"),
 "sql_order": kp("Sorts with ORDER BY (DESC for largest first) and LIMIT when only the top rows are needed",
     ["order by", "desc", "asc", "limit", "sort"],
     "How do you make sure the largest value comes first?"),
 "sql_agg": kp("Uses an aggregate (COUNT/SUM/AVG/MAX) and GROUP BY for one row per group",
     ["count", "sum", "avg", "max", "min", "group by", "aggregate"],
     "How do you turn many rows into one number per group?"),
 "sql_having": kp("Filters groups with HAVING, because WHERE runs before grouping",
     ["having", "after group", "before group"],
     "You want only people above a threshold total. Why can't WHERE do that?"),
 "sql_join": kp("Joins tables through their key columns (e.g. movies.id = stars.movie_id)",
     ["join", " on ", "key", "foreign", "id ="],
     "The name is in one table and the fact in another. How do you connect them?"),
 "sql_like": kp("Uses LIKE with % wildcards for partial text matches",
     ["like", "%", "wildcard", "contains"],
     "How do you match text that only contains a word, not equals it?"),
 "sql_distinct": kp("Uses DISTINCT (or COUNT(DISTINCT ...)) so repeated rows are counted once",
     ["distinct", "unique", "duplicate", "once"],
     "The same person can appear several times. How do you count them once?"),
 "sql_null": kp("Knows COUNT(column) skips NULLs while COUNT(*) counts all rows",
     ["null", "count(*)", "empty", "missing"],
     "Some customers have no company. How does COUNT treat those rows?"),
 "sql_dates": kp("Handles dates with SQLite date functions (strftime/julianday) or by parsing the text format",
     ["strftime", "julianday", "date(", "substr", "format", "text date"],
     "Dates are stored as text here. How do you get the year or the weekday out?"),
 "sql_sub": kp("Uses a subquery (or CTE) for a value computed from the data itself, e.g. the average",
     ["subquery", "select avg", "nested", "with ", "cte", "("],
     "How do you compare each row with an average you have not computed yet?"),
 "returns_negative": kp("Knows that returns are recorded as negative amounts and filters/signs them correctly",
     ["negative", "< 0", "minus", "return", "sign", "abs"],
     "How does a returned item show up in the Amount column?"),
 "flag_not_violation": kp("Treats flagged rows as higher-risk items for follow-up, not as proven violations",
     ["follow", "not necessarily", "investigat", "risk", "doesn't mean", "does not mean", "explain", "evidence"],
     "If the query returns 12 rows, have 12 employees broken the rules?"),
 "control_link": kp("Links the query to the internal control it tests (limit, splitting, prohibited purchase)",
     ["control", "limit", "policy", "split", "guideline", "rule"],
     "Which P-card rule is this query testing, and why does that rule exist?"),
 "pct_change": kp("Computes percentage change as (new − base) / base × 100",
     ["base", "divide", "/", "percent", "100", "minus"],
     "What is the formula for a percentage change relative to 2011?"),
}

def pts(*keys):
    return [dict(K[k], id=k) for k in keys]

# Follow-up questions an examiner might ask after the main explanation.
FOLLOW = {
 "nyc": ["The file is .txt but comma-separated. What would happen if you opened it by double-clicking?",
         "Why is EventAgency useless for analysis in this file?",
         "If a colleague re-ran your analysis next month, how would you make it repeatable?",
         "Why might Excel show some start dates as text after import?"],
 "case1": ["Why does the AICPA Audit Data Standard recommend the pipe as delimiter?",
           "How would you document these cleaning steps for an auditor?",
           "Why are negative numbers in brackets a problem for analysis?"],
 "emp": ["Why do old systems store several fields in one code?",
         "Would you keep the extracted columns as formulas or paste them as values? Why?",
         "What could go wrong with text-to-columns on the messy data?"],
 "je": ["Which join would show all journal lines, even those without account details?",
        "Why is checking that entries balance a useful audit test?",
        "What other journal-entry tests would an auditor run on this data?"],
 "pay": ["Why is it risky to compare data coming from two different accounting systems?",
         "Which question would you ask Noah before starting the analysis?",
         "Would Excel still be the right tool if there were a million payroll rows?",
         "Name one of the four V's of data and how it applies here."],
 "larry": ["How confident would you be in a prediction for a day far outside your data?",
           "What does R-squared tell Bob, and what does it not tell him?",
           "Correlation or causation: can you say game days cause higher sales?"],
 "chinook": ["How would you check your answer without SQL, to be sure it is right?",
             "What is the difference between WHERE and HAVING?",
             "Why do we join InvoiceLine to Track instead of storing the track name on every line?"],
 "songs": ["Why shouldn't you hard-code Drake's artist_id?",
           "What does a NULL do inside AVG?"],
 "movies": ["Why are stars and directors stored in separate tables?",
            "Some movies have no rating. Inner join or left join, and what changes?",
            "How would you avoid listing the same person twice?"],
 "pcard": ["A flagged transaction is not automatically a violation. What would you do next?",
           "Why might an employee split a purchase across two days or two vendors?",
           "Which of your findings would you put first in the audit report, and why?",
           "How could OSU prevent this, instead of detecting it afterwards?"],
}

DATASETS = {}
def dataset(key, name, file, desc, case):
    DATASETS[key] = {"key": key, "name": name, "file": file, "desc": desc, "case": case}

Q = []
def add(subject, ds, prompt, answer, method, keys, est=90, tags=(), follow=None):
    Q.append({
        "id": f"Q{len(Q)+1:03d}", "subject": subject, "dataset": ds, "prompt": prompt,
        "answer": answer, "method": method, "keyPoints": pts(*keys),
        "followUps": follow or FOLLOW.get(ds, []), "est": est, "tags": list(tags)})

def num(v, dec=2, tol=None, unit="", plain=False):
    v = float(v)
    t = tol if tol is not None else (0.5 * 10 ** -dec if dec > 0 else 0.5)
    return {"type": "number", "value": round(v, dec), "tol": t, "unit": unit,
            "display": (str(int(round(v))) if plain else (f"{v:,.{dec}f}" if dec else f"{int(round(v)):,}")) + (f" {unit}" if unit else "")}

def text(v, alts=()):
    return {"type": "text", "value": str(v), "alts": [str(a) for a in alts], "display": str(v)}

def open_(summary):
    return {"type": "open", "display": summary}

# ===========================================================================
# Excel part 1 – NYC film permits
# ===========================================================================
dataset("nyc", "NYC film permits", "NYC_Film_Permits.txt",
        "33,502 film permits issued in New York City. Comma-separated text with quoted fields.", "Excel part 1")
shutil.copy(f"{SRC}/Excel part 1/NYC_Film_Permits.txt", FILES)
n = pd.read_csv(f"{SRC}/Excel part 1/NYC_Film_Permits.txt", dtype=str)
for c in ["StartDateTime", "EndDateTime", "EnteredOn"]:
    n[c] = pd.to_datetime(n[c], format="%m/%d/%Y %H:%M")
n["hours"] = (n.EndDateTime - n.StartDateTime).dt.total_seconds() / 3600
shoot = n[n.EventType == "Shooting Permit"]

add("Excel", "nyc", "Import the permit file into Excel. How many records (rows of data, excluding the header) does it contain?",
    num(len(n), 0), "Data > From Text/CSV, comma delimiter, double quote as text qualifier. Count rows below the header (e.g. =ROWS(table) or the status bar count).",
    ["import_csv", "qualifier", "dates"], 120, ["import"])
add("Excel", "nyc", "How many records have a missing value for ZipCode?",
    num(n.ZipCode.isna().sum(), 0), "Filter ZipCode on (Blanks) or =COUNTBLANK(ZipCode column).",
    ["count_blank", "import_csv"], 60, ["data quality"])
bad_zip = (~n.ZipCode.dropna().str.fullmatch(r"\d{5}(,\s*\d{5})*")).sum()
add("Excel", "nyc", "How many records have an invalid (non-empty but not five-digit) ZipCode?",
    num(bad_zip, 0), "Sort or filter ZipCode and look for values that are not 5 digits (e.g. =LEN(cell)<>5 on non-blank cells; some cells hold lists of valid zips).",
    ["validate", "leading_zero", "count_blank"], 90, ["data quality"])
add("Excel", "nyc", "Which column has the same value for every record? Give the exact column name.",
    text("EventAgency"), "Check each column with a pivot table or =COUNTA(UNIQUE(column)); EventAgency has a single value.",
    ["pivot", "import_csv"], 60, ["profiling"])
add("Excel", "nyc", "What is the oldest EnteredOn value? Give the date and time (m/d/yyyy h:mm).",
    text(n.EnteredOn.min().strftime("%-m/%-d/%Y %-H:%M"), [n.EnteredOn.min().strftime("%m/%d/%Y %H:%M"), n.EnteredOn.min().strftime("%Y-%m-%d %H:%M")]),
    "Make sure EnteredOn is a real date, then =MIN(EnteredOn) or sort ascending.",
    ["dates", "import_csv"], 60, ["dates"])
for b in ["Brooklyn", "Manhattan", "Queens", "Bronx", "Staten Island"]:
    s = shoot[shoot.Borough == b]
    add("Excel", "nyc", f"How many shooting permits were issued in {b}?",
        num(len(s), 0), f'=COUNTIFS(EventType,"Shooting Permit",Borough,"{b}") or a pivot table with both filters.',
        ["filter_two", "pivot"], 60, ["conditional count"])
    add("Excel", "nyc", f"What is the average duration in hours of shooting permits in {b}? Round to two decimals.",
        num(s.hours.mean(), 2, 0.01, "hours"), "Add a column =(EndDateTime-StartDateTime)*24, then AVERAGEIFS on EventType and Borough.",
        ["duration", "filter_two", "dates"], 90, ["date arithmetic"])
    add("Excel", "nyc", f"How many shooting permits in {b} lasted longer than 24 hours?",
        num((s.hours > 24).sum(), 0), 'Duration column in hours, then =COUNTIFS(EventType,"Shooting Permit",Borough,"' + b + '",Hours,">24").',
        ["duration", "filter_two"], 90, ["date arithmetic"])
    add("Excel", "nyc", f"How many shooting permits in {b} have BROADWAY anywhere in ParkingHeld (ignoring case)?",
        num(s.ParkingHeld.str.contains("broadway", case=False, na=False).sum(), 0),
        'COUNTIFS with "*BROADWAY*" wildcard (COUNTIF is not case-sensitive) plus the EventType and Borough conditions.',
        ["text_search", "filter_two", "qualifier"], 90, ["text filter"])
for y in [2013, 2014, 2015, 2016]:
    s = shoot[shoot.StartDateTime.dt.year == y]
    add("Excel", "nyc", f"How many shooting permits started in {y}?",
        num(len(s), 0), "Add =YEAR(StartDateTime) and count with COUNTIFS, or group dates by year in a pivot table.",
        ["dates", "filter_two", "pivot"], 60, ["date filter"])
    lead = (s.StartDateTime - s.EnteredOn).dt.total_seconds() / 86400
    add("Excel", "nyc", f"What is the average lead time in days between EnteredOn and StartDateTime for shooting permits starting in {y}? Round to two decimals.",
        num(lead.mean(), 2, 0.01, "days"), "Lead time =StartDateTime-EnteredOn (already in days), then AVERAGEIFS on event type and year.",
        ["dates", "duration", "filter_two"], 90, ["date arithmetic"])

# ===========================================================================
# Excel part 2 – ETL cases 1-4
# ===========================================================================
dataset("case1", "ETL Case 1 – balance sheet extract", "Analytics_mindset_case_studies_ETL_Case1.csv",
        "Balance-sheet data for several companies with typical messy-data problems.", "Excel part 2")
shutil.copy(f"{SRC}/Excel part 2/Analytics_mindset_case_studies_ETL_Case1.csv", FILES)
add("Excel", "case1", "Open the Case 1 file. List the data problems you would fix before analysing it.",
    open_("Commas inside the company name 'Apple, Inc.' (needs quotes), mixed units (M, K, plain numbers), numbers stored with thousands separators in quotes, negatives in brackets vs minus signs, missing tickers, blanks and dashes for zero, inconsistent tickers (A M Z N, AM ZN), and a duplicated APVO 2018 row."),
    "Inspect the file in a text editor and in Excel; list each problem and how you would fix it.",
    ["qualifier", "standardise", "validate"], 120, ["data quality"],
    FOLLOW["case1"])
add("Excel", "case1", "After cleaning, what is Apple's 2016 cash in dollars?",
    num(20_500_000_000, 0, unit="USD"), "'20500 M' means 20,500 million: strip the unit and multiply by 1,000,000.",
    ["standardise", "validate"], 60, ["units"])
add("Excel", "case1", "After cleaning, what is Aehr Test Systems' 2017 cash in dollars?",
    num(17_800_000, 0, unit="USD"), "'17800 K' means 17,800 thousand: multiply by 1,000.",
    ["standardise", "validate"], 60, ["units"])
add("Excel", "case1", "How many fully duplicated rows does the Case 1 file contain?",
    num(1, 0), "Data > Remove Duplicates (or COUNTIFS on all columns) shows APVO 2018 twice.",
    ["validate", "standardise"], 60, ["duplicates"])
add("Excel", "case1", "How many distinct companies are in the file once tickers are cleaned (use the Name column)?",
    num(7, 0), "Ticker is unreliable (blank for Armada Hoffler, spaces in AMZN), so count unique Name values or fix the tickers first.",
    ["standardise", "unique_key"], 60, ["unique identifiers"])

dataset("emp2", "ETL Case 2 – employee codes", "Analytics_mindset_case_studies_ETL_Case2_Excel.xlsx",
        "597 employees with a combined code such as JAP1080-19M (location, employee ID, plant, pay period).", "Excel part 2")
shutil.copy(f"{SRC}/Excel part 2/Analytics_mindset_case_studies_ETL_Case2_Excel.xlsx", FILES)
e2 = pd.read_excel(f"{SRC}/Excel part 2/Analytics_mindset_case_studies_ETL_Case2_Excel.xlsx", sheet_name="Case 2")
p = e2.EmployeeCode.str.extract(r"^([A-Z]{3})(\d+)-(\d+)([A-Z])$")
e2["loc"], e2["emp"], e2["plant"], e2["pay"] = p[0], p[1], p[2], p[3]
e2["lp"] = e2["loc"] + "-" + e2["plant"]
for loc in ["GER", "JAP", "USA"]:
    add("Excel", "emp2", f"How many employees work in location {loc}?",
        num((e2["loc"] == loc).sum(), 0), "=LEFT(EmployeeCode,3) for Location, then COUNTIF.",
        ["extract", "pivot"], 60, ["text extraction"], FOLLOW["emp"])
add("Excel", "emp2", "How many employees are paid weekly?",
    num((e2.pay == "W").sum(), 0), "=RIGHT(EmployeeCode,1) gives the pay period; COUNTIF on \"W\".",
    ["extract", "pivot"], 60, ["text extraction"], FOLLOW["emp"])
add("Excel", "emp2", "How many distinct LocationPlantID values (e.g. USA-12) are there?",
    num(e2.lp.nunique(), 0), "PlantID =MID(code,FIND(\"-\",code)+1,2); LocationPlantID =Location&\"-\"&PlantID; count unique values.",
    ["unique_key", "extract"], 90, ["unique identifiers"], FOLLOW["emp"])
r = e2.iloc[10]
add("Excel", "emp2", f"What is the LocationPlantID of {r.FirstName} {r.LastName}?",
    text(r.lp), "Extract Location and PlantID with LEFT, MID and FIND and join them with &\"-\"&.",
    ["extract", "unique_key"], 60, ["text extraction"], FOLLOW["emp"])

dataset("emp3", "ETL Case 3 – messy employee codes", "Analytics_mindset_case_studies_ETL_Case3_Excel.xlsx",
        "Same employees, messier codes: variable-length locations (Japan, US) and pay periods (M/Mo, W/We).", "Excel part 2")
shutil.copy(f"{SRC}/Excel part 2/Analytics_mindset_case_studies_ETL_Case3_Excel.xlsx", FILES)
e3 = pd.read_excel(f"{SRC}/Excel part 2/Analytics_mindset_case_studies_ETL_Case3_Excel.xlsx", sheet_name="Case 3 data")
p = e3.EmployeeCode.str.extract(r"^([A-Za-z]+)(\d+)-(\d+)([A-Za-z]+)$")
assert p.notna().all().all()
e3["loc"], e3["plant"] = p[0], p[2]
e3["pay"] = p[3].str[0].str.upper()
e3["lp"] = e3["loc"] + "-" + e3["plant"]
add("Excel", "emp3", "How many employees work in Canada?",
    num((e3["loc"] == "Canada").sum(), 0), "Location ends where the first digit starts: =LEFT(code,MIN(FIND({0,1,...,9},code&\"0123456789\"))-1).",
    ["messy_extract", "extract"], 90, ["text extraction"], FOLLOW["emp"])
add("Excel", "emp3", "How many employees are paid monthly (M or Mo)?",
    num((e3.pay == "M").sum(), 0), "Take the letters after the plant number and standardise Mo→M and We→W, then COUNTIF.",
    ["standardise", "messy_extract"], 90, ["standardising"], FOLLOW["emp"])
add("Excel", "emp3", "How many distinct LocationPlantID values are there in Case 3?",
    num(e3.lp.nunique(), 0), "Extract location and plant with variable-length formulas, join with \"-\", count unique.",
    ["unique_key", "messy_extract"], 120, ["unique identifiers"], FOLLOW["emp"])

dataset("je", "ETL Case 4 – journal entries", "Analytics_mindset_case_studies_ETL_Case4_Excel.xlsx",
        "789 journal-entry lines for a hotel, plus chart of accounts, business units, preparers and sources.", "Excel part 2")
shutil.copy(f"{SRC}/Excel part 2/Analytics_mindset_case_studies_ETL_Case4_Excel.xlsx", FILES)
jx = pd.read_excel(f"{SRC}/Excel part 2/Analytics_mindset_case_studies_ETL_Case4_Excel.xlsx", sheet_name=None)
je = jx["JELineItems"].merge(jx["ChartOfAccounts"], on="GLAccountNumber", how="left").merge(jx["BusinessUnits"], on="BusinessUnitID", how="left")
debit = pd.to_numeric(je.Debit, errors="coerce").fillna(0)
add("Excel", "je", "How many distinct journal entries (JENumber) are in the file?",
    num(je.JENumber.nunique(), 0), "=COUNTA(UNIQUE(JENumber)) or a pivot table with JENumber as rows.",
    ["pivot", "sql_distinct"], 60, ["unique identifiers"])
add("Excel", "je", "What is the total of all debits? Round to two decimals.",
    num(debit.sum(), 2, 0.01, "USD"), "=SUM(Debit column); blanks count as zero.",
    ["balance", "pivot"], 60, ["aggregate"])
bal = je.groupby("JENumber").Amount.sum().round(2)
add("Excel", "je", "How many journal entries do not balance (debits ≠ credits)?",
    num((bal.abs() > 0.004).sum(), 0), "Pivot JENumber with SUM(Amount); entries whose sum is not 0 are unbalanced.",
    ["balance", "pivot"], 90, ["audit test"])
exp = je[je.AccountType == "Expenses"].Amount.sum()
add("Excel", "je", "After joining the chart of accounts, what is the total Amount posted to Expenses accounts? Round to two decimals.",
    num(exp, 2, 0.01, "USD"), "XLOOKUP AccountType from ChartOfAccounts on GLAccountNumber, then SUMIFS(Amount, AccountType, \"Expenses\").",
    ["lookup", "join_type", "pivot"], 120, ["join"])
bu = je.groupby("BusinessUnit").JENumber.nunique().sort_values(ascending=False)
add("Excel", "je", "Which business unit has the most journal entries?",
    text(bu.index[0]), "Lookup BusinessUnit by BusinessUnitID, then a pivot of distinct JENumber per business unit.",
    ["lookup", "pivot"], 90, ["join"])
add("Excel", "je", f"How many journal lines are posted by preparer ID 101?",
    num((je.PreparerID == 101).sum(), 0), "COUNTIF on PreparerID. Note: PreparerID is not unique in PreparerInfo (one ID per business unit), so you need ID and BusinessUnitID to get a name.",
    ["lookup", "unique_key"], 60, ["unique identifiers"])

# ===========================================================================
# Excel part 3 – IntegrateCo payroll
# ===========================================================================
dataset("pay", "IntegrateCo payroll 2015 & 2016", "IntegrateCo_payroll.zip",
        "Pipe-delimited payroll from two different systems (2015 per pay date, 2016 aggregated), job codes and locations.", "Excel part 3")
with zipfile.ZipFile(os.path.join(FILES, "IntegrateCo_payroll.zip"), "w", zipfile.ZIP_DEFLATED) as z:
    for f in ["2015payroll", "2016payroll", "jobcodes", "locations"]:
        fn = f"Analytics_mindset_case_studies_IntegrateCo_{f}.csv"
        z.write(f"{SRC}/Excel part 3/{fn}", fn)
p15 = pd.read_csv(f"{SRC}/Excel part 3/Analytics_mindset_case_studies_IntegrateCo_2015payroll.csv", sep="|", dtype={"Job": str})
p16 = pd.read_csv(f"{SRC}/Excel part 3/Analytics_mindset_case_studies_IntegrateCo_2016payroll.csv", sep="|", dtype={"Project": str})
rx = r"^\d{2}[A-Z]?(\d{3})[A-Z]*$"
p15["code"] = p15.Job.str.extract(rx)[0]
p16["code"] = p16.Project.str.extract(rx)[0]
p15["gross"] = p15.Reg_Pay + p15.OT_Pay
g15, g16 = p15.gross.sum(), p16.Gross_Wages.sum()
add("Excel", "pay", "What is total gross pay in the first half of 2015? Round to two decimals.",
    num(g15, 2, 0.01, "USD"), "Import with | as delimiter; gross pay 2015 = Reg_Pay + OT_Pay; SUM over all rows.",
    ["import_pipe", "gross_def"], 90, ["import", "aggregate"])
add("Excel", "pay", "What is total gross pay in the first half of 2016? Round to two decimals.",
    num(g16, 2, 0.01, "USD"), "Import with | as delimiter and SUM(Gross_Wages).",
    ["import_pipe", "gross_def"], 60, ["import", "aggregate"])
add("Excel", "pay", "By how much did gross pay increase from H1 2015 to H1 2016? Round to two decimals.",
    num(g16 - g15, 2, 0.01, "USD"), "SUM(2016 Gross_Wages) − SUM(2015 Reg_Pay + OT_Pay). Matches Noah's ~$266,000.",
    ["gross_def", "agg_level", "import_pipe"], 120, ["comparison"])
add("Excel", "pay", "How many 2015 payroll rows have an invalid job code (cannot be split into a three-digit code 001–012)?",
    num(p15.code.isna().sum(), 0), "Extract the job code with MID after the year (and optional H/S); flag rows where the result is not 001–012.",
    ["data_quality", "extract", "leading_zero"], 120, ["data quality"])
for c in ["005", "009", "012"]:
    a, b = p15[p15.code == c].gross.sum(), p16[p16.code == c].Gross_Wages.sum()
    add("Excel", "pay", f"What is the change in gross pay for job code {c} from H1 2015 to H1 2016 (2016 minus 2015)? Round to two decimals.",
        num(b - a, 2, 0.01, "USD"), f"Extract job code from Job/Project (digits 3-5 after an optional H/S), keep it as text ('{c}'), SUMIFS per year, subtract.",
        ["extract", "leading_zero", "agg_level"], 150, ["text extraction", "comparison"])
diff = (p16.groupby("code").Gross_Wages.sum() - p15.groupby("code").gross.sum()).sort_values(ascending=False)
add("Excel", "pay", "Which job code explains the largest increase in gross pay from 2015 to 2016? Give the three-digit code.",
    text(diff.index[0], [str(int(diff.index[0]))]), "Build the job-code comparison table (2015 vs 2016 gross pay per code) and sort by difference.",
    ["agg_level", "extract", "pivot"], 150, ["comparison"])
add("Excel", "pay", "How many distinct employees (Emp_No / Employee_Number) were paid in H1 2015 and in H1 2016? Answer as 2015/2016, e.g. 50/60.",
    text(f"{p15.Emp_No.nunique()}/{p16.Employee_Number.nunique()}"), "Count unique Emp_No in 2015 and Employee_Number in 2016 (=COUNTA(UNIQUE(...))).",
    ["agg_level", "sql_distinct"], 90, ["unique identifiers"])
oh15, oh16 = p15.OT_Hrs.sum(), p16.OT_Hours.sum()
add("Excel", "pay", "How many more overtime hours were worked in H1 2016 than in H1 2015? Round to two decimals.",
    num(oh16 - oh15, 2, 0.01, "hours"), "SUM(OT_Hours 2016) − SUM(OT_Hrs 2015).",
    ["agg_level", "gross_def"], 60, ["comparison"])
hrs15, hrs16 = (p15.Reg_Hrs + p15.OT_Hrs).sum(), (p16.Hours + p16.OT_Hours).sum()
add("Excel", "pay", "What was the average gross pay per hour worked (regular + overtime hours) in H1 2016? Round to two decimals.",
    num(g16 / hrs16, 2, 0.01, "USD/hour"), "SUM(Gross_Wages) / SUM(Hours + OT_Hours).",
    ["gross_def", "agg_level"], 90, ["ratio"])

# ===========================================================================
# Excel part 4 – Larry's Commissary (regression)
# ===========================================================================
dataset("larry", "Larry's Commissary sales", "data.xlsm",
        "2018 daily sales per menu item, weather and football game days for a restaurant (Bob).", "Excel part 4")
shutil.copy(f"{SRC}/Excel part 4/data.xlsm", FILES)
lx = pd.read_excel(f"{SRC}/Excel part 4/data.xlsm", sheet_name=None)
sd = lx["salesData"]
daily = sd.groupby("date").agg(sales=("netTotal", "sum"), sales364=("netTotal_364", "sum")).reset_index()
daily = daily.merge(lx["weatherData"], on="date", how="left").merge(lx["gameData"][["date", "gameDay"]], on="date", how="left")
daily["gameDay"] = daily.gameDay.fillna(0)
def ols(y, cols):
    X = np.column_stack([np.ones(len(y))] + [daily[c].values for c in cols])
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    return b
add("Excel", "larry", "Merge the sheets into one row per day. How many days have sales data?",
    num(len(daily), 0), "Pivot salesData by date (sum of netTotal), then XLOOKUP weather and game data on date.",
    ["daily_total", "merge_dates"], 90, ["merge"])
add("Excel", "larry", "What are total net sales (netTotal) for the whole year? Round to the nearest dollar.",
    num(daily.sales.sum(), 0, 0.5, "USD"), "=SUM(netTotal) over all line items.",
    ["daily_total"], 60, ["aggregate"])
gd = daily[daily.gameDay == 1].sales.mean(); ngd = daily[daily.gameDay == 0].sales.mean()
add("Excel", "larry", "What is the average daily net sales on game days? Round to two decimals.",
    num(gd, 2, 0.01, "USD"), "Daily totals, gameDay looked up (missing = 0), then AVERAGEIFS(sales, gameDay, 1).",
    ["daily_total", "merge_dates", "dummy"], 90, ["merge"])
d = daily.dropna(subset=["tmax"])
X = np.column_stack([np.ones(len(d)), d.tmax]); b = np.linalg.lstsq(X, d.sales.values, rcond=None)[0]
add("Excel", "larry", "Regress daily net sales on the maximum temperature (tmax). What is the slope coefficient? Round to two decimals.",
    num(b[1], 2, 0.05, "USD per °F"), "Daily totals merged with weather; Data Analysis > Regression with Y = daily sales, X = tmax (days without weather excluded).",
    ["merge_dates", "regression_tool", "coef_meaning", "significance"], 150, ["regression"])
b = ols(daily.sales.values, ["gameDay"])
add("Excel", "larry", "Regress daily net sales on gameDay (1 = game day, 0 = otherwise). What is the gameDay coefficient? Round to two decimals.",
    num(b[1], 2, 0.05, "USD"), "Merge game data (non-game days = 0) and regress daily sales on gameDay. The coefficient equals the difference in average sales.",
    ["merge_dates", "regression_tool", "dummy", "significance"], 150, ["regression"])
daily["inter"] = daily.sales364 * daily.gameDay
b = ols(daily.sales.values, ["sales364", "gameDay", "inter"])
add("Excel", "larry", "Regress daily net sales on last year's sales (sum of netTotal_364), gameDay and their interaction. What is the interaction coefficient? Round to four decimals.",
    num(b[3], 4, 0.0005), "Create Interaction = sales364 × gameDay and include all three X columns in one regression.",
    ["interaction", "regression_tool", "coef_meaning"], 180, ["regression"])

# ===========================================================================
# SQL part 1 – Chinook (PwC) and CS50 songs/movies
# ===========================================================================
dataset("chinook", "Chinook music store", "Chinook_Sqlite.sqlite",
        "A digital music store: customers, invoices, invoice lines, tracks, albums, genres, employees.", "SQL part 1")
shutil.copy(f"{SRC}/SQL part 1/pwc assignment/Chinook_Sqlite.sqlite", FILES)
ch = sqlite3.connect(f"{SRC}/SQL part 1/pwc assignment/Chinook_Sqlite.sqlite")
one = lambda con, sql: con.execute(sql).fetchone()[0]
def sq(prompt, sql, ans, keys, est=60, tags=(), con=ch, ds="chinook"):
    add("SQL", ds, prompt, ans, sql, keys, est, tags)
sq("How many columns does the Customer table have?", "PRAGMA table_info(Customer);  -- count the rows",
   num(len(ch.execute("PRAGMA table_info(Customer)").fetchall()), 0), ["sql_select"], 45, ["schema"])
sq("Select the first 5 rows of Customer (by CustomerId). What is the Country in the fifth row?",
   "SELECT Country FROM Customer ORDER BY CustomerId LIMIT 5;",
   text(ch.execute("SELECT Country FROM Customer ORDER BY CustomerId LIMIT 5").fetchall()[-1][0]), ["sql_select", "sql_order"], 45, ["limit"])
sq("Sort customers by LastName. What is the LastName in the third row?",
   "SELECT LastName FROM Customer ORDER BY LastName LIMIT 1 OFFSET 2;",
   text(ch.execute("SELECT LastName FROM Customer ORDER BY LastName LIMIT 3").fetchall()[-1][0]), ["sql_order", "sql_select"], 45, ["sort"])
sq("How many rows are in the Invoice table?", "SELECT COUNT(*) FROM Invoice;", num(one(ch, "SELECT COUNT(*) FROM Invoice"), 0), ["sql_agg"], 30, ["count"])
sq("How many invoices have a Total greater than $20?", "SELECT COUNT(*) FROM Invoice WHERE Total > 20;",
   num(one(ch, "SELECT COUNT(*) FROM Invoice WHERE Total > 20"), 0), ["sql_where", "sql_agg"], 45, ["filter"])
sq("How many invoices have a Total greater than $10 and less than $20?", "SELECT COUNT(*) FROM Invoice WHERE Total > 10 AND Total < 20;",
   num(one(ch, "SELECT COUNT(*) FROM Invoice WHERE Total > 10 AND Total < 20"), 0), ["sql_where", "sql_agg"], 45, ["filter"])
sq("How many invoices are from customers in Brazil, Argentina or Chile (use BillingCountry)?",
   "SELECT COUNT(*) FROM Invoice WHERE BillingCountry IN ('Brazil','Argentina','Chile');",
   num(one(ch, "SELECT COUNT(*) FROM Invoice WHERE BillingCountry IN ('Brazil','Argentina','Chile')"), 0), ["sql_where", "sql_agg"], 45, ["filter"])
sq("How many invoices have a BillingCountry that starts with 'C'?", "SELECT COUNT(*) FROM Invoice WHERE BillingCountry LIKE 'C%';",
   num(one(ch, "SELECT COUNT(*) FROM Invoice WHERE BillingCountry LIKE 'C%'"), 0), ["sql_like", "sql_agg"], 45, ["text filter"])
sq("How many customers list a company?", "SELECT COUNT(Company) FROM Customer;  -- COUNT(column) skips NULLs",
   num(one(ch, "SELECT COUNT(Company) FROM Customer"), 0), ["sql_null", "sql_agg"], 45, ["nulls"])
sq("How many employees does Chinook have?", "SELECT COUNT(*) FROM Employee;", num(one(ch, "SELECT COUNT(*) FROM Employee"), 0), ["sql_agg"], 30, ["count"])
sq("How many characters long is the longest customer LastName?", "SELECT MAX(LENGTH(LastName)) FROM Customer;",
   num(one(ch, "SELECT MAX(LENGTH(LastName)) FROM Customer"), 0), ["sql_agg", "sql_select"], 45, ["text functions"])
sq("How many employees were born on a Sunday?", "SELECT COUNT(*) FROM Employee WHERE strftime('%w', BirthDate) = '0';",
   num(one(ch, "SELECT COUNT(*) FROM Employee WHERE strftime('%w', BirthDate) = '0'"), 0), ["sql_dates", "sql_where"], 60, ["dates"])
age = one(ch, "SELECT MAX((julianday(HireDate) - julianday(BirthDate)) / 365.25) FROM Employee")
sq("How old (in whole years) was the oldest employee when hired?",
   "SELECT MAX(CAST((julianday(HireDate) - julianday(BirthDate)) / 365.25 AS INT)) FROM Employee;",
   num(int(age), 0), ["sql_dates", "sql_agg"], 90, ["dates"])
top = ch.execute("SELECT BillingCountry, SUM(Total) s FROM Invoice GROUP BY BillingCountry ORDER BY s DESC").fetchall()
sq("List countries by total invoice value in descending order. Which country is first, and what is its total? Answer as Country, total (e.g. Norway, 12.34).",
   "SELECT BillingCountry, SUM(Total) AS TotalValue FROM Invoice GROUP BY BillingCountry ORDER BY TotalValue DESC;",
   text(f"{top[0][0]}, {top[0][1]:.2f}", [f"{top[0][0]} {top[0][1]:.2f}", f"{top[0][0]},{top[0][1]:.2f}"]), ["sql_agg", "sql_order"], 90, ["group by"])
sq("How many invoice line items are there?", "SELECT COUNT(*) FROM InvoiceLine;", num(one(ch, "SELECT COUNT(*) FROM InvoiceLine"), 0), ["sql_agg"], 30, ["count"])
sq("How many distinct unit prices appear in InvoiceLine?", "SELECT COUNT(DISTINCT UnitPrice) FROM InvoiceLine;",
   num(one(ch, "SELECT COUNT(DISTINCT UnitPrice) FROM InvoiceLine"), 0), ["sql_distinct", "sql_agg"], 45, ["distinct"])
pp = ch.execute("SELECT UnitPrice, SUM(Quantity) FROM InvoiceLine GROUP BY UnitPrice ORDER BY UnitPrice").fetchall()
sq("How many downloads (sum of Quantity) happened at the price $1.99?",
   "SELECT UnitPrice, SUM(Quantity) FROM InvoiceLine GROUP BY UnitPrice;",
   num(dict(pp)[1.99], 0), ["sql_agg", "sql_where"], 60, ["group by"])
sq("What is the range of invoice dates? Give the first and last InvoiceDate as yyyy-mm-dd to yyyy-mm-dd.",
   "SELECT MIN(InvoiceDate), MAX(InvoiceDate) FROM Invoice;",
   text(f"{one(ch,'SELECT date(MIN(InvoiceDate)) FROM Invoice')} to {one(ch,'SELECT date(MAX(InvoiceDate)) FROM Invoice')}"), ["sql_agg", "sql_dates"], 45, ["dates"])
sq("How many distinct albums have at least one track that was downloaded?",
   "SELECT COUNT(DISTINCT t.AlbumId) FROM InvoiceLine il JOIN Track t ON il.TrackId = t.TrackId;",
   num(one(ch, "SELECT COUNT(DISTINCT t.AlbumId) FROM InvoiceLine il JOIN Track t ON il.TrackId = t.TrackId"), 0), ["sql_join", "sql_distinct"], 90, ["join"])
g = ch.execute("SELECT g.Name, SUM(il.Quantity) q FROM InvoiceLine il JOIN Track t ON il.TrackId=t.TrackId JOIN Genre g ON t.GenreId=g.GenreId GROUP BY g.Name ORDER BY q DESC").fetchall()
sq("Which genre has the most downloads?",
   "SELECT g.Name, SUM(il.Quantity) AS Downloads FROM InvoiceLine il JOIN Track t ON il.TrackId = t.TrackId JOIN Genre g ON t.GenreId = g.GenreId GROUP BY g.Name ORDER BY Downloads DESC LIMIT 1;",
   text(g[0][0]), ["sql_join", "sql_agg", "sql_order"], 120, ["join", "group by"])
sq("What is the highest number of times a single track has been downloaded?",
   "SELECT TrackId, SUM(Quantity) AS n FROM InvoiceLine GROUP BY TrackId ORDER BY n DESC LIMIT 1;",
   num(one(ch, "SELECT MAX(n) FROM (SELECT SUM(Quantity) n FROM InvoiceLine GROUP BY TrackId)"), 0), ["sql_agg", "sql_order"], 60, ["group by"])

dataset("songs", "Spotify songs (CS50)", "songs.db", "Top 100 songs with audio features and artists.", "SQL part 1")
shutil.copy(f"{SRC}/SQL part 1/cs50 assignment/songs/songs.db", FILES)
so = sqlite3.connect(f"{SRC}/SQL part 1/cs50 assignment/songs/songs.db")
sq("List the names of the 3 longest songs. What is the name of the longest one?",
   "SELECT name FROM songs ORDER BY duration_ms DESC LIMIT 3;", text(one(so, "SELECT name FROM songs ORDER BY duration_ms DESC LIMIT 1")),
   ["sql_order", "sql_select"], 45, ["sort"], so, "songs")
sq("How many songs have danceability, energy and valence all greater than 0.6?",
   "SELECT COUNT(*) FROM songs WHERE danceability > 0.6 AND energy > 0.6 AND valence > 0.6;",
   num(one(so, "SELECT COUNT(*) FROM songs WHERE danceability > 0.6 AND energy > 0.6 AND valence > 0.6"), 0), ["sql_where", "sql_agg"], 45, ["filter"], so, "songs")
sq("What is the average tempo of all songs? Round to two decimals.", "SELECT AVG(tempo) FROM songs;",
   num(one(so, "SELECT AVG(tempo) FROM songs"), 2, 0.01), ["sql_agg"], 30, ["aggregate"], so, "songs")
sq("How many songs are by Drake? Do not assume Drake's artist_id.",
   "SELECT COUNT(*) FROM songs WHERE artist_id = (SELECT id FROM artists WHERE name = 'Drake');",
   num(one(so, "SELECT COUNT(*) FROM songs WHERE artist_id = (SELECT id FROM artists WHERE name='Drake')"), 0), ["sql_sub", "sql_join"], 60, ["subquery"], so, "songs")
sq("What is the average energy of songs by Post Malone? Round to three decimals.",
   "SELECT AVG(energy) FROM songs JOIN artists ON songs.artist_id = artists.id WHERE artists.name = 'Post Malone';",
   num(one(so, "SELECT AVG(energy) FROM songs JOIN artists ON songs.artist_id=artists.id WHERE artists.name='Post Malone'"), 3, 0.001), ["sql_join", "sql_agg"], 60, ["join"], so, "songs")
sq("How many songs feature other artists ('feat.' in the name)?", "SELECT COUNT(*) FROM songs WHERE name LIKE '%feat.%';",
   num(one(so, "SELECT COUNT(*) FROM songs WHERE name LIKE '%feat.%'"), 0), ["sql_like", "sql_agg"], 45, ["text filter"], so, "songs")

# Movies: the original database is 69 MB, so students get a practice subset
# (movies with at least 1,000 IMDb votes, and everyone linked to them).
dataset("movies", "IMDb movies (CS50) · practice subset", "movies_subset.zip",
        "Movies with at least 1,000 IMDb votes, their stars, directors and ratings (subset of CS50 movies.db).", "SQL part 1")
mpath = os.path.join(OUT, "_movies_subset.db")
if os.path.exists(mpath): os.remove(mpath)
mv = sqlite3.connect(mpath)
mv.execute(f"ATTACH DATABASE '{SRC}/SQL part 1/cs50 assignment/movies/movies.db' AS src")
mv.executescript("""
CREATE TABLE movies (id INTEGER, title TEXT NOT NULL, year NUMERIC, PRIMARY KEY(id));
CREATE TABLE ratings (movie_id INTEGER NOT NULL, rating REAL NOT NULL, votes INTEGER NOT NULL, FOREIGN KEY(movie_id) REFERENCES movies(id));
CREATE TABLE people (id INTEGER, name TEXT NOT NULL, birth NUMERIC, PRIMARY KEY(id));
CREATE TABLE stars (movie_id INTEGER NOT NULL, person_id INTEGER NOT NULL, FOREIGN KEY(movie_id) REFERENCES movies(id), FOREIGN KEY(person_id) REFERENCES people(id));
CREATE TABLE directors (movie_id INTEGER NOT NULL, person_id INTEGER NOT NULL, FOREIGN KEY(movie_id) REFERENCES movies(id), FOREIGN KEY(person_id) REFERENCES people(id));
INSERT INTO movies SELECT m.* FROM src.movies m JOIN src.ratings r ON r.movie_id = m.id WHERE r.votes >= 1000;
INSERT INTO ratings SELECT r.* FROM src.ratings r WHERE r.movie_id IN (SELECT id FROM movies);
INSERT INTO stars SELECT s.* FROM src.stars s WHERE s.movie_id IN (SELECT id FROM movies);
INSERT INTO directors SELECT d.* FROM src.directors d WHERE d.movie_id IN (SELECT id FROM movies);
INSERT INTO people SELECT p.* FROM src.people p WHERE p.id IN (SELECT person_id FROM stars UNION SELECT person_id FROM directors);
""")
mv.commit(); mv.execute("DETACH DATABASE src"); mv.execute("VACUUM"); mv.commit()
with zipfile.ZipFile(os.path.join(FILES, "movies_subset.zip"), "w", zipfile.ZIP_DEFLATED) as z:
    z.write(mpath, "movies.db")
def mq(prompt, sql, ans, keys, est=60, tags=()):
    add("SQL", "movies", prompt, ans, sql, keys, est, tags)
mq("How many movies in the database were released in 2007?", "SELECT COUNT(*) FROM movies WHERE year = 2007;",
   num(one(mv, "SELECT COUNT(*) FROM movies WHERE year = 2007"), 0), ["sql_where", "sql_agg"], 45, ["filter"])
mq("What is Johnny Depp's birth year?", "SELECT birth FROM people WHERE name = 'Johnny Depp';",
   num(one(mv, "SELECT birth FROM people WHERE name='Johnny Depp'"), 0, plain=True), ["sql_where", "sql_select"], 30, ["filter"])
mq("How many movies have an IMDb rating greater than 9.0?", "SELECT COUNT(*) FROM ratings WHERE rating > 9.0;",
   num(one(mv, "SELECT COUNT(*) FROM ratings WHERE rating > 9.0"), 0), ["sql_where", "sql_agg"], 45, ["filter"])
mq("List all Toy Story movies in chronological order. In which year was the latest one released?",
   "SELECT title, year FROM movies WHERE title LIKE 'Toy Story%' ORDER BY year;",
   num(one(mv, "SELECT MAX(year) FROM movies WHERE title LIKE 'Toy Story%'"), 0, plain=True), ["sql_like", "sql_order"], 45, ["text filter"])
mq("What is the average rating of movies released in 2013? Round to two decimals.",
   "SELECT AVG(rating) FROM ratings JOIN movies ON ratings.movie_id = movies.id WHERE year = 2013;",
   num(one(mv, "SELECT AVG(rating) FROM ratings JOIN movies ON ratings.movie_id=movies.id WHERE year=2013"), 2, 0.01), ["sql_join", "sql_agg"], 60, ["join"])
top11 = mv.execute("SELECT title FROM movies JOIN ratings ON movies.id=ratings.movie_id WHERE year=2011 ORDER BY rating DESC, title LIMIT 1").fetchone()[0]
mq("List movies released in 2011 with their ratings, highest first (ties alphabetical). Which title is first?",
   "SELECT title, rating FROM movies JOIN ratings ON movies.id = ratings.movie_id WHERE year = 2011 ORDER BY rating DESC, title;",
   text(top11), ["sql_join", "sql_order"], 60, ["join", "sort"])
mq("How many people starred in Harry Potter and the Sorcerer's Stone?",
   "SELECT COUNT(*) FROM stars JOIN movies ON stars.movie_id = movies.id WHERE title = 'Harry Potter and the Sorcerer''s Stone';",
   num(one(mv, "SELECT COUNT(*) FROM stars JOIN movies ON stars.movie_id=movies.id WHERE title='Harry Potter and the Sorcerer''s Stone'"), 0), ["sql_join", "sql_where"], 60, ["join"])
mq("How many different people starred in a movie released in 2003 (count each person once)?",
   "SELECT COUNT(DISTINCT person_id) FROM stars JOIN movies ON stars.movie_id = movies.id WHERE year = 2003;",
   num(one(mv, "SELECT COUNT(DISTINCT person_id) FROM stars JOIN movies ON stars.movie_id=movies.id WHERE year=2003"), 0), ["sql_join", "sql_distinct"], 90, ["distinct"])
mq("How many different people directed a movie with a rating of at least 9.0?",
   "SELECT COUNT(DISTINCT d.person_id) FROM directors d JOIN ratings r ON d.movie_id = r.movie_id WHERE r.rating >= 9.0;",
   num(one(mv, "SELECT COUNT(DISTINCT d.person_id) FROM directors d JOIN ratings r ON d.movie_id=r.movie_id WHERE r.rating >= 9.0"), 0), ["sql_join", "sql_distinct", "sql_where"], 90, ["join"])
hbc = mv.execute("SELECT title FROM movies JOIN stars ON movies.id=stars.movie_id JOIN people ON people.id=stars.person_id JOIN ratings ON ratings.movie_id=movies.id WHERE name='Helena Bonham Carter' ORDER BY rating DESC LIMIT 1").fetchone()[0]
mq("What is the highest-rated movie Helena Bonham Carter starred in?",
   "SELECT title FROM movies JOIN stars ON movies.id = stars.movie_id JOIN people ON people.id = stars.person_id JOIN ratings ON ratings.movie_id = movies.id WHERE name = 'Helena Bonham Carter' ORDER BY rating DESC LIMIT 1;",
   text(hbc), ["sql_join", "sql_order"], 90, ["join"])
both = one(mv, """SELECT COUNT(*) FROM (SELECT movie_id FROM stars JOIN people ON people.id=stars.person_id WHERE name='Johnny Depp'
                  INTERSECT SELECT movie_id FROM stars JOIN people ON people.id=stars.person_id WHERE name='Helena Bonham Carter')""")
mq("In how many movies did both Johnny Depp and Helena Bonham Carter star?",
   "SELECT movie_id FROM stars JOIN people ON people.id = stars.person_id WHERE name = 'Johnny Depp' INTERSECT SELECT movie_id FROM stars JOIN people ON people.id = stars.person_id WHERE name = 'Helena Bonham Carter';",
   num(both, 0), ["sql_join", "sql_sub"], 120, ["subquery"])
kb = one(mv, """SELECT COUNT(DISTINCT person_id) FROM stars WHERE movie_id IN (SELECT movie_id FROM stars JOIN people ON people.id=stars.person_id
                WHERE name='Kevin Bacon' AND birth=1958) AND person_id NOT IN (SELECT id FROM people WHERE name='Kevin Bacon' AND birth=1958)""")
mq("How many different people starred in a movie with Kevin Bacon (born 1958), excluding Kevin Bacon himself?",
   "SELECT COUNT(DISTINCT person_id) FROM stars WHERE movie_id IN (SELECT movie_id FROM stars JOIN people ON people.id = stars.person_id WHERE name = 'Kevin Bacon' AND birth = 1958) AND person_id <> (SELECT id FROM people WHERE name = 'Kevin Bacon' AND birth = 1958);",
   num(kb, 0), ["sql_sub", "sql_distinct", "sql_join"], 150, ["subquery"])
mv.close(); os.remove(mpath)

# ===========================================================================
# SQL part 2 – P-cards (Oklahoma State University)
# ===========================================================================
dataset("pcard", "OSU purchasing cards", "pcards.zip",
        "All Oklahoma State University P-card transactions 2010–2014 (489,178 rows). Returns are negative amounts.", "SQL part 2")
with zipfile.ZipFile(os.path.join(FILES, "pcards.zip"), "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    z.write(f"{SRC}/SQL part 2/pcards.db", "pcards.db")
pc = sqlite3.connect(f"{SRC}/SQL part 2/pcards.db")
def pq(prompt, sql, ans, keys, est=90, tags=(), check=None):
    add("SQL", "pcard", prompt, ans, sql, keys, est, tags)
pq("What is the total number of P-card transactions in the database? (label TotalTrans)", "SELECT COUNT(*) AS TotalTrans FROM pcards;",
   num(one(pc, "SELECT COUNT(*) FROM pcards"), 0), ["sql_agg"], 30, ["count"])
pq("How many transactions are for $5,000 or more? (label TotalTransGT5k)", "SELECT COUNT(*) AS TotalTransGT5k FROM pcards WHERE Amount >= 5000;",
   num(one(pc, "SELECT COUNT(*) FROM pcards WHERE Amount >= 5000"), 0), ["sql_where", "sql_agg", "control_link"], 45, ["filter"])
pq("What is the total dollar amount of returns from January to March 2014? Round to two decimals (returns are negative).",
   "SELECT SUM(Amount) AS TotalReturns2014Q1 FROM pcards WHERE Year = 2014 AND Month BETWEEN 1 AND 3 AND Amount < 0;",
   num(one(pc, "SELECT SUM(Amount) FROM pcards WHERE Year=2014 AND Month BETWEEN 1 AND 3 AND Amount < 0"), 2, 0.01, "USD"), ["returns_negative", "sql_where", "sql_agg"], 90, ["returns"])
pq("How many transactions occurred in 2014 for more than $3,000 at a vendor with 'Amazon' anywhere in the name?",
   "SELECT COUNT(*) FROM pcards WHERE Year = 2014 AND Amount > 3000 AND Vendor LIKE '%amazon%';",
   num(one(pc, "SELECT COUNT(*) FROM pcards WHERE Year=2014 AND Amount > 3000 AND Vendor LIKE '%amazon%'"), 0), ["sql_like", "sql_where"], 60, ["text filter"])
top = pc.execute("SELECT FullName, COUNT(*) n FROM pcards WHERE Year=2014 GROUP BY FullName ORDER BY n DESC LIMIT 1").fetchone()
pq("Which cardholder had the most transactions in 2014, and how many? Answer as Name, count.",
   "SELECT FullName, COUNT(*) AS NumTrans FROM pcards WHERE Year = 2014 GROUP BY FullName ORDER BY NumTrans DESC LIMIT 1;",
   text(f"{top[0]}, {top[1]}", [f"{top[0]} {top[1]}"]), ["sql_agg", "sql_order"], 60, ["group by"])
pq("How many cardholders had more than 10 transactions in 2014?",
   "SELECT COUNT(*) FROM (SELECT FullName FROM pcards WHERE Year = 2014 GROUP BY FullName HAVING COUNT(*) > 10);",
   num(one(pc, "SELECT COUNT(*) FROM (SELECT FullName FROM pcards WHERE Year=2014 GROUP BY FullName HAVING COUNT(*) > 10)"), 0), ["sql_having", "sql_agg"], 90, ["having"])
pq("How many people returned more than $1,000 worth of goods in 2014?",
   "SELECT COUNT(*) FROM (SELECT FullName FROM pcards WHERE Year = 2014 AND Amount < 0 GROUP BY FullName HAVING -SUM(Amount) > 1000);",
   num(one(pc, "SELECT COUNT(*) FROM (SELECT FullName FROM pcards WHERE Year=2014 AND Amount<0 GROUP BY FullName HAVING -SUM(Amount) > 1000)"), 0), ["returns_negative", "sql_having"], 120, ["having", "returns"])
tax = pc.execute("SELECT Year, SUM(Amount)*0.045 FROM pcards GROUP BY Year ORDER BY Year DESC").fetchall()
pq("Assuming a 4.5% state sales tax rate, how much sales tax did OSU avoid on P-card transactions in 2014? Round to two decimals.",
   "SELECT Year, SUM(Amount) AS TotalSpent, ROUND(SUM(Amount) * 0.045, 2) AS SalesTaxSaved FROM pcards GROUP BY Year ORDER BY Year DESC;",
   num(dict(tax)[2014], 2, 0.01, "USD"), ["sql_agg", "control_link"], 90, ["calculated field"])
ae = one(pc, "SELECT SUM(CASE WHEN Amount >= 500 THEN Amount*0.0075 ELSE Amount*0.005 END) FROM pcards WHERE Year=2014 AND Vendor='Amazon.com' COLLATE NOCASE")
pq("For 2014 transactions at the vendor Amazon.com (any capitalisation), OSU would earn 0.75% on transactions of $500 or more and 0.50% on smaller ones. What is the total (AmazonEarnings)? Round to two decimals.",
   "SELECT SUM(CASE WHEN Amount >= 500 THEN Amount * 0.0075 ELSE Amount * 0.005 END) AS AmazonEarnings FROM pcards WHERE Year = 2014 AND Vendor = 'Amazon.com' COLLATE NOCASE;",
   num(ae, 2, 0.01, "USD"), ["sql_where", "sql_agg", "returns_negative"], 120, ["case when"])
pq("How many 2014 transactions are above the average 2014 transaction amount?",
   "SELECT COUNT(*) FROM pcards WHERE Year = 2014 AND Amount > (SELECT AVG(Amount) FROM pcards WHERE Year = 2014);",
   num(one(pc, "SELECT COUNT(*) FROM pcards WHERE Year=2014 AND Amount > (SELECT AVG(Amount) FROM pcards WHERE Year=2014)"), 0), ["sql_sub", "sql_where"], 90, ["subquery"])
pct = one(pc, "SELECT ROUND((SELECT COUNT(*) FROM pcards WHERE Year=2014)*100.0/(SELECT COUNT(*) FROM pcards WHERE Year=2011) - 100, 2)")
pq("What is the percentage change in the number of transactions in 2014 relative to 2011? Round to two decimals.",
   "SELECT ROUND((COUNT(CASE WHEN Year = 2014 THEN 1 END) - COUNT(CASE WHEN Year = 2011 THEN 1 END)) * 100.0 / COUNT(CASE WHEN Year = 2011 THEN 1 END), 2) FROM pcards;",
   num(pct, 2, 0.01, "%"), ["pct_change", "sql_agg", "sql_null"], 120, ["calculated field"])
# Task 5 – internal control tests (2014 only)
q1 = pc.execute("SELECT FullName, SUM(Amount) s FROM pcards WHERE Year=2014 GROUP BY FullName HAVING s > 50000").fetchall()
pq("Control: a user shall not spend more than $50,000 per year. How many employees spent more than $50,000 in 2014?",
   "SELECT FullName, SUM(Amount) AS Total FROM pcards WHERE Year = 2014 GROUP BY FullName HAVING SUM(Amount) > 50000 ORDER BY Total DESC;",
   num(len(q1), 0), ["sql_having", "control_link", "flag_not_violation"], 120, ["internal control"])
q2 = pc.execute("SELECT FullName, Month, SUM(Amount) s FROM pcards WHERE Year=2014 GROUP BY FullName, Month HAVING s > 10000").fetchall()
pq("Control: no more than $10,000 per month without approval. How many employee-months in 2014 exceed $10,000?",
   "SELECT FullName, Month, SUM(Amount) AS Total FROM pcards WHERE Year = 2014 GROUP BY FullName, Month HAVING SUM(Amount) > 10000 ORDER BY Month, Total DESC;",
   num(len(q2), 0), ["sql_having", "sql_agg", "control_link", "flag_not_violation"], 150, ["internal control"])
pq("Control: no single transaction above $5,000. How many 2014 transactions were for more than $5,000?",
   "SELECT Amount, FullName, Description, Vendor, TransactionDate, PostedDate, MCC FROM pcards WHERE Year = 2014 AND Amount > 5000 ORDER BY Amount;",
   num(one(pc, "SELECT COUNT(*) FROM pcards WHERE Year=2014 AND Amount > 5000"), 0), ["sql_where", "control_link", "flag_not_violation"], 60, ["internal control"])
sp = pc.execute("""SELECT COUNT(*) FROM (SELECT FullName, Vendor, TransactionDate FROM pcards WHERE Year=2014
                   GROUP BY FullName, Vendor, TransactionDate HAVING COUNT(*) > 1 AND SUM(Amount) > 5000)""").fetchone()[0]
pq("Split-purchase test: same cardholder, same vendor, same day, more than one transaction, combined total above $5,000. How many such person-vendor-days are there in 2014?",
   "SELECT FullName, Vendor, TransactionDate, COUNT(*) AS n, SUM(Amount) AS Total FROM pcards WHERE Year = 2014 GROUP BY FullName, Vendor, TransactionDate HAVING COUNT(*) > 1 AND SUM(Amount) > 5000 ORDER BY TransactionDate;",
   num(sp, 0), ["sql_having", "control_link", "flag_not_violation"], 180, ["internal control"])
def todate(col):
    # 'm/d/yyyy 0:00:00' -> yyyy-mm-dd inside SQLite
    return (f"date(substr({col}, instr(substr({col}, instr({col},'/')+1), '/') + instr({col},'/') + 1, 4) || '-' || "
            f"printf('%02d', substr({col}, 1, instr({col},'/')-1)) || '-' || "
            f"printf('%02d', substr(substr({col}, instr({col},'/')+1), 1, instr(substr({col}, instr({col},'/')+1), '/')-1)))")
mx = one(pc, f"SELECT MAX(julianday({todate('PostedDate')}) - julianday({todate('TransactionDate')})) FROM pcards WHERE Year=2014 AND Month=11")
assert mx is not None
pq("For November 2014, what is the largest number of days between TransactionDate and PostedDate?",
   "-- Dates are text like '7/26/2014 0:00:00': convert them to yyyy-mm-dd first (or import with proper date types), then\nSELECT MAX(julianday(posted) - julianday(trans)) AS TimeDif FROM ... WHERE Year = 2014 AND Month = 11;",
   num(mx, 0), ["sql_dates", "sql_agg"], 150, ["dates"])

# ---------------------------------------------------------------------------
# Data manipulation exams: 3 Excel + 3 SQL questions, two data files each.
# ---------------------------------------------------------------------------
rnd = random.Random(2026)
excel_ds = sorted({q["dataset"] for q in Q if q["subject"] == "Excel"})
sql_ds = sorted({q["dataset"] for q in Q if q["subject"] == "SQL"})
by_ds = {}
for q in Q: by_ds.setdefault(q["dataset"], []).append(q["id"])
EXAMS, seen = [], set()
while len(EXAMS) < 150:
    e, s = rnd.choice(excel_ds), rnd.choice(sql_ds)
    if len(by_ds[e]) < 3 or len(by_ds[s]) < 3: continue
    ids = sorted(rnd.sample(by_ds[e], 3)) + sorted(rnd.sample(by_ds[s], 3))
    if tuple(ids) in seen: continue
    seen.add(tuple(ids))
    EXAMS.append({"id": f"E{len(EXAMS)+1:03d}", "datasets": [e, s], "questions": ids, "minutes": 8})

json.dump({"datasets": DATASETS, "questions": Q, "exams": EXAMS}, open(os.path.join(OUT, "bank.json"), "w"), indent=1, ensure_ascii=False)
print(len(Q), "questions;", len(EXAMS), "exams")
for k in DATASETS: print(k, len(by_ds.get(k, [])))
for f in sorted(os.listdir(FILES)): print(f, os.path.getsize(os.path.join(FILES, f)) // 1024, "KB")
