# ExamTopics PDF Exporter

Turn any ExamTopics exam page into a single, clean, merged **PDF** — with the
"Reveal Solution" answer boxes already open — in one command.

```
$ python export.py --headed --qpp 50
aws-certified-cloud-practitioner-clf-c02:  27%|██▋      | 4/15 [00:41<01:53, q#4]
```

Built on **Playwright** + **pypdf**. Zero cloud, zero paid extensions, uses
your own logged-in Chrome session.

---

## Features

- **One command, one PDF.** Per-question PDFs are merged into `<exam-slug>.pdf` and cleaned up.
- **Answers already revealed** in the output — no clicking required.
- **Session settings automation.** Sets *Questions Per Page* (15–50) via the site's slider.
- **Cookie reuse.** First run headed to log in; every next run headless.
- **Empty-page filter.** Blank pages are dropped during merge.
- **Progress bar** with live question counter (`tqdm`).
- **Single log file** at `<out-dir>/export.log`.
- **Any ExamTopics exam** via `--url`.
- **A4** paper, tight margins, layout-preserving CSS overrides.
- Optional: keep per-page PDFs (`--keep-pages`) and PNG screenshots (`--keep-png`).

---

## Install

```bash
git clone <this-repo>
cd examtopics_pdf_exporter
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

---

## First run (log in once)

```bash
python export.py --headed
```

A Chromium window opens. Log in to ExamTopics, then press **Enter** in the terminal.
Your session is saved to a dedicated Chrome profile at
`~/Library/Application Support/Google/Chrome/ClaudeAutomation` and reused on every
subsequent run.

## Subsequent runs (headless)

```bash
python export.py
```

Runs silently, shows a progress bar, drops the merged PDF into `~/Downloads/<exam-slug>/`.

---

## Usage

```
python export.py [--url URL] [--qpp N] [--max-pages N]
                 [--headed] [--out-dir DIR]
                 [--keep-pages] [--keep-png]
```

| Flag           | Default                        | What it does                                             |
| -------------- | ------------------------------ | -------------------------------------------------------- |
| `--url`        | AWS CLF-C02                    | Exam base URL (up to the exam slug).                     |
| `--qpp`        | `50`                           | Questions per page, 15–50. Sets via the site's slider.   |
| `--max-pages`  | `9999`                         | Cap number of pages exported (useful for testing).       |
| `--headed`     | off                            | Show the browser — required for first-time login.        |
| `--out-dir`    | `~/Downloads/<exam-slug>`      | Output directory.                                        |
| `--keep-pages` | off                            | Keep per-page PDF files after merge.                     |
| `--keep-png`   | off                            | Also save a full-page PNG per page.                      |
| `--help`       |                                | Show all options.                                        |

Run `python export.py --help` for the full help screen.

---

## Examples

```bash
# Default: AWS Cloud Practitioner, 50 q/page, headless
python export.py

# Different exam
python export.py --url https://www.examtopics.com/exams/amazon/aws-certified-solutions-architect-associate-saa-c03

# Quick smoke test (3 pages, keep artifacts for inspection)
python export.py --headed --max-pages 3 --keep-pages --keep-png

# Fewer questions per page, custom output folder
python export.py --qpp 25 --out-dir ~/Documents/exam-pdfs/clf-c02
```

---

## Output

```
~/Downloads/aws-certified-cloud-practitioner-clf-c02/
├── aws-certified-cloud-practitioner-clf-c02.pdf   # the merged deliverable
└── export.log                                     # every step, timestamped
```

With `--keep-pages` a `pages/` sub-folder is preserved with `page_0001.pdf`, `page_0002.pdf`, …

---

## How it works

1. Opens `custom-view/`, moves the *Questions Per Page* range slider to `--qpp`,
   submits **Set Session Settings**.
2. Loads `view/1/`.
3. On each question page:
   - Force-shows all answer panels (no click cascade — clicking the reveal
     button navigates and blanks the DOM on this site).
   - Removes cosmetic chrome: `#scrollUp`, `.full-width-header`,
     `#rs-footer` (visibility hidden).
   - Overrides Bootstrap's `.container` max-width so PDFs use the full A4 width.
   - Renders `page.pdf({format: 'A4', scale: 0.85, margin: 3–5mm})`.
4. Clicks **Next Questions** and repeats until the button is gone.
5. Merges every produced PDF, dropping pages whose extractable text is under
   40 characters.

---

## Troubleshooting

**Empty PDF / crashes right away.** Run headed first — you're probably not logged in yet:

```bash
python export.py --headed --max-pages 1
```

Check `export.log` in the output directory.

**Playwright complains about a missing browser.** Re-run:

```bash
playwright install chromium
```

**`qpp slider not found` warning.** Site A/B test or layout change — the run
continues with the site's default (usually 25). Open the site once headed to
verify the custom-view page still has a `<input type="range">`.

---

## What this deliberately doesn't do

- No GoFullPage extension juggling — Playwright's built-in `page.pdf()` is
  simpler and reliable.
- No CDP fiddling for print emulation — `screen` media is what preserves
  ExamTopics' layout (they hide content in `@media print`).
- No cookie extraction from your daily Chrome profile — that profile is locked
  while Chrome runs. The dedicated automation profile solves it with zero pain.

---

## License

MIT.
