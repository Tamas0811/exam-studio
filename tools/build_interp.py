"""Builds the data interpretation (regression) exams.

Each exam has four questions, each with its own model:
  1. prediction   2. continuous coefficient   3. dummy coefficient   4. significance
Usage: python3 tools/build_interp.py <output folder>
"""
import json, os, random, sys

OUT = sys.argv[1]
rnd = random.Random(42)

def kp(id_, text, keywords, hint):
    return {"id": id_, "text": text, "keywords": keywords, "hint": hint}

# y, y unit, x name, x unit, x range, dummy name, dummy 1 label, dummy 0 label,
# intercept range, slope range, dummy effect range
S = [
 ("Daily restaurant sales", "USD/day", "Maximum temperature", "°F", (30, 95), "Game day", "a home football game day", "a day without a game", (2500, 3500), (5, 15), (800, 1800)),
 ("Monthly audit hours", "hours/month", "Number of client entities", "entities", (5, 40), "First-year client", "a first-year audit client", "a returning client", (60, 120), (6, 14), (25, 60)),
 ("Invoice processing time", "minutes/invoice", "Number of invoice lines", "lines", (1, 30), "Paper invoice", "a paper invoice", "an e-invoice", (3, 8), (0.3, 1.2), (4, 10)),
 ("Weekly overtime hours", "hours/week", "Open job orders", "orders", (10, 60), "Peak season", "a peak-season week", "an off-season week", (5, 15), (0.2, 0.6), (6, 14)),
 ("Monthly P-card spending", "USD/month", "Department headcount", "employees", (5, 80), "Grant-funded department", "a grant-funded department", "a non-grant department", (1500, 4000), (60, 160), (900, 2500)),
 ("Days sales outstanding", "days", "Average invoice size", "thousand USD", (1, 50), "Public-sector customer", "a public-sector customer", "a private customer", (25, 40), (0.2, 0.8), (8, 20)),
 ("Coworking desks occupied", "desks/day", "Daily desk price", "EUR/day", (10, 40), "Near train station", "a workspace near a train station", "a workspace away from a station", (80, 110), (-2.0, -0.8), (8, 18)),
 ("Hotel rooms sold", "rooms/night", "Room rate", "EUR/night", (60, 180), "Conference week", "a conference week", "a normal week", (180, 240), (-0.9, -0.3), (25, 60)),
 ("Monthly electricity cost", "EUR/month", "Production hours", "hours", (100, 600), "Winter month", "a winter month", "a non-winter month", (2000, 5000), (8, 20), (600, 1500)),
 ("Expense claims submitted", "claims/week", "Employees travelling", "employees", (5, 50), "After policy change", "a week after the new travel policy", "a week before the change", (10, 30), (0.8, 2.0), (-12, -4)),
 ("Bakery bread sold", "loaves/day", "Price per loaf", "DKK", (15, 45), "Weekend", "a weekend day", "a weekday", (300, 450), (-6, -2), (40, 110)),
 ("Customer complaints", "complaints/week", "Orders shipped", "hundred orders", (5, 40), "New warehouse system", "a week after the new warehouse system", "a week before", (3, 10), (0.4, 1.2), (-6, -2)),
 ("Bike rentals", "rentals/day", "Daily rainfall", "mm", (0, 30), "Cruise ship in port", "a day with a cruise ship in port", "a day without one", (220, 320), (-6, -2), (40, 100)),
 ("Gym check-ins", "check-ins/day", "Outdoor temperature", "°C", (-5, 30), "January", "a day in January", "a day in another month", (350, 500), (-6, -2), (60, 140)),
 ("Accounts payable errors", "errors/month", "Invoices processed", "hundred invoices", (2, 30), "Automated matching", "a month with automated three-way matching", "a month without it", (4, 12), (0.5, 1.5), (-8, -3)),
 ("Concert tickets sold", "tickets/show", "Ticket price", "EUR", (20, 90), "Saturday show", "a Saturday show", "a show on another day", (1100, 1600), (-12, -5), (150, 350)),
 ("Ice cream sales", "USD/day", "Maximum temperature", "°C", (10, 35), "School holiday", "a school-holiday day", "a school day", (300, 600), (30, 70), (150, 400)),
 ("Payroll processing time", "hours/run", "Employees on payroll", "employees", (50, 400), "New hires this run", "a run that includes new hires", "a run without new hires", (2, 5), (0.01, 0.03), (1.5, 4)),
 ("Coffee cups sold", "cups/day", "Students on campus", "hundred students", (5, 60), "Exam period", "an exam-period day", "a normal teaching day", (100, 200), (4, 10), (60, 150)),
 ("Warehouse picking errors", "errors/day", "Orders picked", "hundred orders", (2, 25), "Temporary staff", "a day with temporary staff", "a day with only permanent staff", (1, 4), (0.3, 0.9), (2, 6)),
]

def r(a, b, dec):
    return round(rnd.uniform(a, b), dec)

def pv(sig=True):
    return round(rnd.uniform(0.001, 0.04), 3) if sig else round(rnd.uniform(0.12, 0.65), 3)

def fmt(v):
    return f"{v:,.2f}".rstrip("0").rstrip(".") if isinstance(v, float) else f"{v:,}"

def model(s):
    y, yu, x, xu, (lo, hi), d, d1, d0, b0r, b1r, b2r = s
    dec = 2 if abs(b1r[1]) < 3 else 1
    b0, b1, b2 = r(*b0r, 1 if b0r[1] < 50 else 0), r(*b1r, dec), r(*b2r, 1 if b2r[1] < 50 else 0)
    if b0 == int(b0): b0 = int(b0)
    if b2 == int(b2): b2 = int(b2)
    return dict(y=y, yu=yu, x=x, xu=xu, lo=lo, hi=hi, d=d, d1=d1, d0=d0, b0=b0, b1=b1, b2=b2)

FOLLOW = [
 "Would you trust this model to predict for a value far outside the data range? Why?",
 "Does a significant coefficient prove that X causes Y?",
 "What does the intercept mean here, and is it meaningful on its own?",
 "What would R-squared add to what you have told me?",
 "What other variable would you add to this model, and why?",
]

def q_predict(m, qid):
    x = round(rnd.uniform(m["lo"] + (m["hi"] - m["lo"]) * .2, m["hi"] - (m["hi"] - m["lo"]) * .2))
    dval = rnd.choice([0, 1])
    pred = m["b0"] + m["b1"] * x + m["b2"] * dval
    grp = m["d1"] if dval else m["d0"]
    return {"id": qid, "kind": "predict",
            "prompt": f"Predict {m['y'].lower()} for {grp} when {m['x'].lower()} is {x} {m['xu']}.",
            "answer": {"type": "number", "value": round(pred, 2), "tol": max(0.01, abs(pred) * 0.001), "unit": m["yu"],
                       "display": f"{pred:,.2f} {m['yu']}"},
            "method": f"{fmt(m['b0'])} + ({fmt(m['b1'])} × {x}) + ({fmt(m['b2'])} × {dval}) = {pred:,.2f} {m['yu']}.",
            "keyPoints": [
                kp("plug", "Plugs the values into the equation: intercept + slope × X + dummy coefficient × (0 or 1)", ["plug", "equation", "intercept", "multiply", "times", "×", "+"], "Which numbers go into the equation, and where?"),
                kp("dummy01", f"Sets the dummy correctly: {m['d']} = {dval} for {grp}", ["1", "0", "dummy", "zero", "one", "reference"], f"For {grp}, what value does {m['d']} take?"),
                kp("units", f"States the result in units ({m['yu']})", m["yu"].replace("/", " ").split() + ["per", "units"], "What is the unit of your answer?"),
                kp("range", f"Notes that X = {x} lies inside the data range ({m['lo']}–{m['hi']}), so this is not extrapolation", ["range", "extrapolat", "inside", "within", "data"], f"The data covers {m['lo']}–{m['hi']} {m['xu']}. Why does that matter for your prediction?"),
            ]}

def q_slope(m, qid, p):
    direction = "increase" if m["b1"] > 0 else "decrease"
    return {"id": qid, "kind": "slope",
            "prompt": f"Interpret the coefficient on {m['x']} ({fmt(m['b1'])}). Is it statistically significant at the 5% level?",
            "answer": {"type": "open", "display": f"A one-{m['xu']} increase in {m['x'].lower()} is associated with a {abs(m['b1'])} {m['yu']} {direction} in {m['y'].lower()}, holding {m['d'].lower()} constant. p = {p} < 0.05, so it is significant at 5%."},
            "method": "Coefficient = change in Y for a one-unit change in X, other variables held constant; compare p-value with 0.05.",
            "keyPoints": [
                kp("oneunit", f"A one-unit ({m['xu']}) increase in {m['x'].lower()} changes {m['y'].lower()} by {fmt(m['b1'])} {m['yu']}", ["one", "each", "per", "unit", "increase", "additional"], f"If {m['x'].lower()} goes up by one {m['xu']}, what happens?"),
                kp("ceteris", f"Holding {m['d'].lower()} constant (ceteris paribus)", ["holding", "constant", "ceteris", "other", "same", "controlling"], "What are you assuming about the other variable in the model?"),
                kp("sig", f"p = {p} is below 0.05, so the effect is statistically significant at the 5% level", ["p-value", "p value", "signific", "0.05", "5%", "below"], "How do you decide whether this coefficient is significant?"),
                kp("assoc", "Speaks of association, not proven causation", ["associat", "correlat", "not caus", "doesn't prove", "does not prove", "related"], "Does the regression prove that X causes the change?"),
            ]}

def q_dummy(m, qid, p):
    more = "higher" if m["b2"] > 0 else "lower"
    return {"id": qid, "kind": "dummy",
            "prompt": f"Interpret the coefficient on {m['d']} ({fmt(m['b2'])}).",
            "answer": {"type": "open", "display": f"For {m['d1']}, {m['y'].lower()} is {abs(m['b2'])} {m['yu']} {more} than for {m['d0']} (the reference group), holding {m['x'].lower()} constant. p = {p} < 0.05, so the difference is significant."},
            "method": "A 0/1 dummy coefficient is the difference between the group coded 1 and the reference group coded 0.",
            "keyPoints": [
                kp("ref", f"Compares {m['d1']} with the reference group: {m['d0']}", ["reference", "compared", "versus", "vs", "than", "baseline", "0"], "Compared to which group is this difference measured?"),
                kp("size", f"States the size and direction: {abs(m['b2'])} {m['yu']} {more}", [str(abs(m["b2"])).split(".")[0], more, "higher" if more == "higher" else "lower", "more" if more == "higher" else "less"], "By how much, and in which direction?"),
                kp("ceteris", f"Holding {m['x'].lower()} constant", ["holding", "constant", "ceteris", "same", "controlling"], f"What do you assume about {m['x'].lower()} when you compare the two groups?"),
                kp("sig", f"p = {p} < 0.05: the difference is statistically significant", ["p-value", "p value", "signific", "0.05", "5%"], "Is the difference statistically significant?"),
            ]}

def q_sig(m, qid, p1, p2):
    ns = m["x"] if p1 > 0.05 else m["d"]
    pns = p1 if p1 > 0.05 else p2
    return {"id": qid, "kind": "significance",
            "prompt": "Which explanatory variable is NOT statistically significant at the 5% level, and what does that mean for the conclusion you can draw?",
            "answer": {"type": "text", "value": ns, "alts": [ns.lower()], "display": f"{ns} (p = {pns} > 0.05): we cannot conclude that its effect differs from zero. That is not proof of no effect."},
            "method": "Compare each p-value with 0.05. A p-value above 0.05 means the coefficient is not significantly different from zero.",
            "keyPoints": [
                kp("compare", f"Compares each p-value with 0.05 and identifies {ns} (p = {pns})", ["0.05", "5%", "p-value", "p value", "above", "greater", "higher"], "Which number do you compare with 0.05?"),
                kp("zero", "Not significant means we cannot rule out that the true effect is zero", ["zero", "rule out", "no evidence", "cannot conclude", "can't conclude", "not different"], "What does 'not significant' mean about the true coefficient?"),
                kp("notnoeffect", "This is not proof that there is no effect (e.g. small sample)", ["not proof", "doesn't mean", "does not mean", "sample", "absence", "might still"], "Does a non-significant result prove the variable has no effect at all?"),
            ]}

EXAMS = []
for i in range(20):
    picks = rnd.sample(S, 4)
    qs = []
    m = model(picks[0]); p = [pv(), pv(), pv()]
    qs.append(dict(q_predict(m, f"REG{i+1:03d}-1"), model=m, pvals=p))
    m = model(picks[1]); p = [pv(), pv(), pv()]
    qs.append(dict(q_slope(m, f"REG{i+1:03d}-2", p[1]), model=m, pvals=p))
    m = model(picks[2]); p = [pv(), pv(), pv()]
    qs.append(dict(q_dummy(m, f"REG{i+1:03d}-3", p[2]), model=m, pvals=p))
    m = model(picks[3]); first = rnd.choice([True, False])
    p = [pv(), pv(not first), pv(first)]
    qs.append(dict(q_sig(m, f"REG{i+1:03d}-4", p[1], p[2]), model=m, pvals=p))
    for q in qs: q["followUps"] = FOLLOW
    EXAMS.append({"id": f"REG{i+1:03d}", "title": picks[0][0], "minutes": 5, "questions": qs})

json.dump({"exams": EXAMS}, open(os.path.join(OUT, "interpretation.json"), "w"), indent=1, ensure_ascii=False)
print(len(EXAMS), "interpretation exams")
