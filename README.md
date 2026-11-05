# Exam Studio Oral

A practice website for **Data Analytics in Accounting** (SDU). Students practise the oral exam:
a data manipulation exam (Excel + SQL) and a data interpretation exam (regression), followed by
an **oral examiner** that asks them to explain their work under exam timing.

## What is on the site

| Part | Contents |
|---|---|
| Data manipulation exams | 150 exams, each 3 Excel + 3 SQL questions on two data files, 8-minute timer |
| Question bank | 125 questions from all six cases (NYC film permits, ETL cases 1–4, IntegrateCo payroll, Larry's Commissary, Chinook, CS50 songs/movies, OSU P-cards) |
| Data interpretation exams | 20 exams × 4 regression questions (prediction, slope, dummy, significance), 5-minute timer |
| Answer checking | Every question with a single result can be checked; model method shown on request |
| **Oral examiner** (the added functionality) | Explain your answer by voice or typing: 10 s to start, ~60 s to answer (soft limits), one hint if you are on the right track, two follow-up questions, then a rating against the question's key points plus your timing |

## The improvement: oral examiner mode

The exam is oral, but practice sites only train producing a result. The examiner trains the part
that is actually graded orally: explaining *why* (delimiters, text qualifiers, leading zeros, joins,
WHERE vs HAVING, flagged ≠ violation, reference groups, p-values) and handling follow-up questions.
See the "Why oral mode?" page on the site for the full argument.

- **AI examiner:** `/api/examine` in `src/worker.js` sends the question, its key points and the
  student's transcript to Gemini and receives JSON (points covered, optional nudge, follow-up,
  grading). The API key is a Cloudflare secret and never reaches the browser.
- **Offline examiner:** if the AI is unavailable, a keyword-based examiner in `public/examiner.js`
  uses the same key points and pre-written hints, so the mode never breaks.
- **Voice:** the browser's Web Speech API (Chrome, Edge). Typing always works.

## How the questions are made

`tools/build_bank.py` reads the original course files and computes every answer from the same
files students download (nothing is typed in by hand). `tools/build_interp.py` generates the
regression exams. Large files are reduced to fit Cloudflare's 25 MiB per-file limit:
`pcards.db` is zipped (all rows kept) and `movies.db` is a practice subset (movies with ≥ 1,000
IMDb votes); answers are computed on the files as published.

```bash
python3 tools/build_bank.py "/path/to/ExamStudio" public/data
python3 tools/build_interp.py public/data
```

## Deploying on Cloudflare

1. Cloudflare dashboard → **Workers & Pages → Create → Import a repository** → pick this repo.
2. Build command: *(leave empty)* · Deploy command: `npx wrangler deploy`.
3. After the first deploy: the Worker → **Settings → Variables and Secrets → Add** →
   type **Secret**, name `GEMINI_API_KEY`, value = your Google AI Studio key.
4. Optional: change `GEMINI_MODEL` in `wrangler.jsonc` (default `gemini-3.5-flash-lite`, chosen for its higher free-tier daily limit; the worker
   falls back to any available Flash model automatically).

Every push to `main` redeploys the site.

## Files

```
public/            static site (index.html, app.js, examiner.js, styles.css)
public/data/       bank.json, interpretation.json, files/ (downloads)
src/worker.js      Cloudflare Worker: static assets + /api/examine (Gemini)
tools/             generators for the question bank and regression exams
```
