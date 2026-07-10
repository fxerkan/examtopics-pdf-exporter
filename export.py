"""ExamTopics -> single merged PDF.

Reuses your Chrome profile for cookies. Renders each question page to PDF via
Playwright's built-in `page.pdf()`, then merges into ALL.pdf and drops empty pages.
"""
import argparse, asyncio, logging, pathlib, re, subprocess, sys, tempfile


def _ensure_deps():
    req = pathlib.Path(__file__).parent / "requirements.txt"
    try:
        import playwright, pypdf, tqdm  # noqa: F401
    except ImportError:
        print("Installing Python dependencies...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "-r", str(req)])
    try:
        from playwright.async_api import async_playwright  # noqa: F401
        # ponytail: chromium install is idempotent and fast when already present
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"],
                              stdout=subprocess.DEVNULL)
    except Exception as e:
        print(f"Playwright browser install failed: {e}", file=sys.stderr); raise


_ensure_deps()

from playwright.async_api import async_playwright
from pypdf import PdfReader, PdfWriter
from tqdm import tqdm

PROFILE = pathlib.Path.home() / "Library/Application Support/Google/Chrome/ClaudeAutomation"

REVEAL_JS = r"""
(reveal) => {
if (reveal) {
  document.querySelectorAll('.reveal-solution').forEach(b => b.style.display = 'none');
  document.querySelectorAll(
    '.question-answer, .correct-answer-box, .answer-description, .question-answer-block, .answer-hidden'
  ).forEach(e => { e.style.display = 'block'; e.hidden = false; e.removeAttribute('hidden'); });
}
const f = document.getElementById('rs-footer'); if (f) f.style.visibility = 'hidden';
['#scrollUp', '.full-width-header']
  .forEach(sel => document.querySelectorAll(sel).forEach(e => e.remove()));
const css = document.createElement('style');
css.textContent = `
  .container, .container-fluid { max-width: 100% !important; width: 100% !important;
    padding-left: 4px !important; padding-right: 4px !important; }
  body { margin: 0 !important; }
  .sec-spacer { padding: 0 !important; }
  .question-answer, .correct-answer-box, .answer-description,
  .question-answer-block, .answer-hidden { display: block !important; }
`;
document.head.appendChild(css);
}
"""

SET_QPP_JS = """
(qpp) => {
  const s = document.querySelector('input[type=range]');
  if (!s) return false;
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
  setter.call(s, String(qpp));
  s.dispatchEvent(new Event('input', {bubbles: true}));
  s.dispatchEvent(new Event('change', {bubbles: true}));
  return true;
}
"""

NEXT_SEL = 'a.btn.btn-success:has-text("Next Questions"), a:has-text("Next Questions")'
log = logging.getLogger("examtopics")


def slug_from_url(url: str) -> str:
    # ponytail: last non-empty path segment after /exams/<vendor>/<slug>
    parts = [p for p in url.rstrip("/").split("/") if p]
    return parts[-1] if parts else "exam"


async def run(args):
    base = args.url.rstrip("/")
    if not re.match(r"^https?://.+/exams/[^/]+/[^/]+/?$", base):
        base = re.sub(r"/(view|custom-view)(/.*)?$", "", base)
    start_url = f"{base}/view/1/"
    custom_url = f"{base}/custom-view/"

    slug = slug_from_url(base)
    out_dir = pathlib.Path(args.out_dir).expanduser() if args.out_dir else pathlib.Path.home() / "Downloads" / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    PROFILE.mkdir(parents=True, exist_ok=True)

    log_file = out_dir / "export.log"
    logging.basicConfig(
        filename=log_file, filemode="w", level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    log.info(f"start slug={slug} qpp={args.qpp} max={args.max_pages} headed={args.headed}")

    keep_dir = out_dir / "pages" if args.keep_pages else pathlib.Path(tempfile.mkdtemp(prefix="et_"))
    keep_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            str(PROFILE), headless=not args.headed,
            viewport={"width": 1200, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(custom_url, wait_until="domcontentloaded")

        if args.headed:
            print("If not logged in, log in now in the browser, then press Enter here...")
            await asyncio.get_event_loop().run_in_executor(None, input)

        await page.goto(custom_url, wait_until="domcontentloaded")
        if await page.evaluate(SET_QPP_JS, args.qpp):
            await page.get_by_role("button", name=re.compile("Set Session Settings", re.I)).click()
            await page.wait_for_load_state("domcontentloaded")
            log.info(f"session qpp set to {args.qpp}")
        else:
            log.warning("qpp slider not found; continuing with site default")

        await page.goto(start_url, wait_until="domcontentloaded")

        pdfs = []
        bar = tqdm(total=args.max_pages, unit="page", desc=slug, file=sys.stdout)
        for i in range(1, args.max_pages + 1):
            try:
                await page.wait_for_selector(".exam-question-card, .question-body",
                                             timeout=30000, state="attached")
            except Exception as e:
                log.error(f"page {i} no content: {e} url={page.url}")
                break

            await page.evaluate(REVEAL_JS, not args.hide_answers)
            await page.wait_for_timeout(800)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(400)

            qnum = re.search(r"/view/(\d+)", page.url)
            name = f"page_{(qnum.group(1) if qnum else str(i)).zfill(4)}"
            pdf_path = keep_dir / f"{name}.pdf"

            try:
                await page.emulate_media(media="screen")
                await page.pdf(
                    path=str(pdf_path), format="A4", print_background=True, scale=0.85,
                    margin={"top": "5mm", "bottom": "5mm", "left": "3mm", "right": "3mm"},
                )
                if args.keep_png:
                    await page.screenshot(path=str(keep_dir / f"{name}.png"), full_page=True)
            except Exception as e:
                log.error(f"page {i} pdf failed: {e}")
                break

            size = pdf_path.stat().st_size
            log.info(f"page {i} url={page.url} bytes={size}")
            if size < 5000:
                log.warning(f"page {i} empty pdf, stopping")
                break
            pdfs.append(pdf_path)
            bar.update(1)
            bar.set_postfix_str(f"q#{qnum.group(1) if qnum else i}")

            nxt = page.locator(NEXT_SEL).first
            if await nxt.count() == 0:
                log.info("no Next button, finished")
                break
            await nxt.click()
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(2000)

        bar.close()
        await ctx.close()

    if not pdfs:
        print("No PDFs produced. See log:", log_file)
        return

    merged = out_dir / f"{slug}.pdf"
    w = PdfWriter()
    kept = dropped = 0
    for f in tqdm(pdfs, desc="merging", unit="file", file=sys.stdout):
        for pg in PdfReader(str(f)).pages:
            if len(pg.extract_text().strip()) < 40:
                dropped += 1; continue
            w.add_page(pg); kept += 1
    w.write(str(merged)); w.close()
    log.info(f"merged kept={kept} dropped={dropped} -> {merged}")
    print(f"\nDone. {kept} pages ({dropped} empty dropped) -> {merged}")
    print(f"Log: {log_file}")

    if not args.keep_pages:
        for f in pdfs:
            f.unlink(missing_ok=True)
        try:
            keep_dir.rmdir()
        except OSError:
            pass


def parse_args():
    ap = argparse.ArgumentParser(
        prog="export.py",
        description="Export an ExamTopics exam to a single merged PDF.",
        epilog="""Examples:
  python export.py                              # default exam, 50 q/page, headless
  python export.py --headed                     # first run: log in interactively
  python export.py --url https://www.examtopics.com/exams/amazon/aws-certified-solutions-architect-associate-saa-c03
  python export.py --qpp 25 --max-pages 5 --keep-pages --keep-png
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--url", help="Exam base URL (e.g. https://www.examtopics.com/exams/amazon/<exam-slug>). Prompted if omitted.")
    ap.add_argument("--qpp", type=int, default=50, help="Questions per page, 15..50 (default: 50).")
    ap.add_argument("--max-pages", type=int, default=9999, help="Cap number of pages exported.")
    ap.add_argument("--headed", action="store_true", help="Show browser (needed for first-time login).")
    ap.add_argument("--out-dir", help="Output directory (default: ~/Downloads/<exam-slug>).")
    ap.add_argument("--keep-pages", action="store_true", help="Keep per-page PDF files.")
    ap.add_argument("--keep-png", action="store_true", help="Also save a PNG screenshot per page.")
    ap.add_argument("--hide-answers", action="store_true",
                    help="Do not reveal solutions (export with answers hidden).")
    a = ap.parse_args()
    assert 15 <= a.qpp <= 50, "qpp must be 15..50"
    while not a.url:
        a.url = input("Exam base URL: ").strip()
    return a


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
