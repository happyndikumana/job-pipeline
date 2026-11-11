#!/usr/bin/env python3
"""
job-pipeline tailor — Batch-generate tailored resumes from Notion job postings.

For each job posting in Notion where Resume Version is empty:
1. Scrape the job description from the Job Link
2. Use Claude API to tailor the LaTeX resume
3. Create a git branch with the tailored resume + PDF
4. Score the resume against the job description
5. Update Notion with PDF link, score, and match report

Run it inside your resume folder: the git repo holding experience.md,
main.tex, reference_resume.tex, prompts/system.txt and .env.
job-pipeline init creates the starter files in a new folder.

Usage:
    # Process all jobs without resumes
    job-pipeline tailor

    # Process only 3 jobs
    job-pipeline tailor --limit 3

    # Process only Amazon jobs
    job-pipeline tailor --company amazon

    # Process a specific role at a specific company
    job-pipeline tailor --company amazon --role ring

    # Combine filters
    job-pipeline tailor --company amazon --role ring --limit 1

    # Use a different Claude account's API key for this run
    job-pipeline tailor --account work

Arguments:
    --limit N        Max number of jobs to process (default: all)
    --company TEXT    Only process jobs where the company name contains TEXT
                     (case-insensitive). E.g. --company amazon matches "Amazon".
    --role TEXT       Only process jobs where the role title contains TEXT
                     (case-insensitive). E.g. --role ring matches
                     "Embedded Software Development Engineer, Ring".
    --skip-manual    Skip jobs that can't be scraped instead of prompting for
                     manual paste. Useful for unattended batch runs.
    --manual         Skip scraping entirely and prompt to paste the job
                     description for every job.
    --account NAME   Which Claude API key to use: reads ANTHROPIC_API_KEY_<NAME>
                     from .env (e.g. --account work -> ANTHROPIC_API_KEY_WORK).
                     Defaults to CLAUDE_ACCOUNT in .env, then ANTHROPIC_API_KEY.

Requirements:
    - .env file with NOTION_TOKEN, NOTION_DATABASE_ID and a Claude API key
      (see .env.example). Optional: CLAUDE_MODEL (default claude-sonnet-4-6)
    - pdflatex installed (for LaTeX compilation)
    - playwright install chromium (for JS-rendered job pages)
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import anthropic
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
# Your resume folder is wherever you run the command from.
REPO_DIR = Path.cwd()
load_dotenv(REPO_DIR / ".env")

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_ACCOUNT = os.getenv("CLAUDE_ACCOUNT", "")

EXPERIENCE_FILE = REPO_DIR / "experience.md"
BASE_TEX_FILE = REPO_DIR / "main.tex"
REFERENCE_TEX_FILE = REPO_DIR / "reference_resume.tex"
SYSTEM_PROMPT_FILE = REPO_DIR / "prompts" / "system.txt"
# A prompts/user.txt in your folder wins; otherwise the shared default is used.
USER_PROMPT_FILE = REPO_DIR / "prompts" / "user.txt"
if not USER_PROMPT_FILE.exists():
    USER_PROMPT_FILE = Path(__file__).parent / "templates" / "user.txt"

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")


def api_key_var(account: str) -> str:
    """Name of the .env variable holding the Claude API key for an account."""
    return f"ANTHROPIC_API_KEY_{account.upper()}" if account else "ANTHROPIC_API_KEY"


def use_claude_account(account: str):
    """Switch to the Claude API key for the given account (empty = ANTHROPIC_API_KEY)."""
    global ANTHROPIC_API_KEY
    ANTHROPIC_API_KEY = os.getenv(api_key_var(account))


def check_config(account: str = ""):
    """Validate that the resume folder and all required environment variables are set."""
    required = [EXPERIENCE_FILE, BASE_TEX_FILE, REFERENCE_TEX_FILE, SYSTEM_PROMPT_FILE]
    missing_files = [str(p.relative_to(REPO_DIR)) for p in required if not p.exists()]
    if missing_files:
        print(f"Error: {REPO_DIR} is missing: {', '.join(missing_files)}")
        print("Run job-pipeline tailor inside your resume folder (job-pipeline init creates the starter files).")
        sys.exit(1)
    if "<FILL IN" in SYSTEM_PROMPT_FILE.read_text():
        print("Error: prompts/system.txt still has <FILL IN ...> placeholders. Finish it first.")
        sys.exit(1)

    missing = []
    if not NOTION_TOKEN:
        missing.append("NOTION_TOKEN")
    if not NOTION_DATABASE_ID:
        missing.append("NOTION_DATABASE_ID")
    if not ANTHROPIC_API_KEY:
        missing.append(api_key_var(account))
    if missing:
        print(f"Error: Missing environment variables: {', '.join(missing)}")
        print("Copy .env.example to .env and fill in your values. job-pipeline notion creates the tracker and fills in NOTION_DATABASE_ID.")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Notion (direct HTTP — avoids SDK version issues)
# ---------------------------------------------------------------------------
NOTION_BASE = "https://api.notion.com/v1"
NOTION_HEADERS = None  # initialized in check_config


def init_notion_headers():
    global NOTION_HEADERS
    NOTION_HEADERS = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }


def query_jobs_without_resume() -> list[dict]:
    """Query Notion DB for job postings where Resume Version is empty."""
    resp = requests.post(
        f"{NOTION_BASE}/databases/{NOTION_DATABASE_ID}/query",
        headers=NOTION_HEADERS,
        json={
            "filter": {
                "and": [
                    {
                        "property": "Resume Version",
                        "rich_text": {"is_empty": True},
                    },
                    {
                        "property": "Application Stage",
                        "select": {"does_not_equal": "Job Expired"},
                    },
                ]
            }
        },
    )
    resp.raise_for_status()
    data = resp.json()

    jobs = []
    for page in data["results"]:
        props = page["properties"]
        job = {
            "page_id": page["id"],
            "company": _get_title(props.get("Company", {})),
            "role_title": _get_rich_text(props.get("Role Title", {})),
            "level": _get_select(props.get("Level", {})),
            "location": _get_rich_text(props.get("Location", {})),
            "job_link": _get_url(props.get("Job Link", {})),
            "count": _get_number(props.get("count", {})),
        }
        jobs.append(job)
    return jobs


def _rich_text_chunks(text: str, limit: int = 2000) -> list[dict]:
    """Split text into Notion rich_text blocks (max 2000 chars each).

    Notion's rich_text property accepts an *array* of text objects that are
    concatenated together in the same field.  Each individual object can hold
    at most 2000 characters, so longer strings must be split across multiple
    array elements.
    """
    chunks = []
    for i in range(0, len(text), limit):
        chunks.append({"text": {"content": text[i : i + limit]}})
    return chunks


def mark_job_expired(page_id: str):
    """Set Application Stage to 'Job Expired' on a Notion page."""
    resp = requests.patch(
        f"{NOTION_BASE}/pages/{page_id}",
        headers=NOTION_HEADERS,
        json={
            "properties": {
                "Application Stage": {
                    "select": {"name": "Job Expired"},
                }
            }
        },
    )
    resp.raise_for_status()


def update_notion_results(page_id: str, pdf_url: str, score: int, match_report: str):
    """Update Resume Version, Resume Score, and Resume Match Report on a Notion page."""
    properties = {
        "Resume Version": {
            "rich_text": [
                {
                    "text": {
                        "content": "View Resume",
                        "link": {"url": pdf_url},
                    }
                }
            ]
        },
        "Resume Score": {
            "rich_text": [{"text": {"content": f"{score}%"}}]
        },
        "Resume Match Report": {
            "rich_text": _rich_text_chunks(match_report)
        },
    }
    resp = requests.patch(
        f"{NOTION_BASE}/pages/{page_id}",
        headers=NOTION_HEADERS,
        json={"properties": properties},
    )
    resp.raise_for_status()


# Notion property helpers
def _get_title(prop: dict) -> str:
    items = prop.get("title", [])
    return items[0]["plain_text"] if items else ""


def _get_rich_text(prop: dict) -> str:
    items = prop.get("rich_text", [])
    return items[0]["plain_text"] if items else ""


def _get_select(prop: dict) -> str:
    sel = prop.get("select")
    return sel["name"] if sel else ""


def _get_url(prop: dict) -> str:
    return prop.get("url", "") or ""


def _get_number(prop: dict) -> int:
    val = prop.get("number")
    if val is None:  # an auto-numbered ID column
        val = (prop.get("unique_id") or {}).get("number")
    return int(val) if val is not None else 0


# ---------------------------------------------------------------------------
# Job Description Scraping
# ---------------------------------------------------------------------------
def _extract_text_from_html(html: str) -> str:
    """Extract job description text from HTML content."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove script/style elements
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()

    # Try common job description containers first
    selectors = [
        ".job-description",
        ".jobDescriptionContent",
        "#job-description",
        '[data-testid="job-description"]',
        ".description__text",
        ".posting-requirements",
        "article",
        ".content-wrapper",
        "main",
    ]
    for selector in selectors:
        container = soup.select_one(selector)
        if container and len(container.get_text(strip=True)) > 200:
            return container.get_text(separator="\n", strip=True)

    # Fallback: extract all visible text from body
    body = soup.find("body")
    if body:
        text = body.get_text(separator="\n", strip=True)
        lines = [line for line in text.splitlines() if line.strip()]
        return "\n".join(lines[:300])

    return ""


def _scrape_with_requests(url: str) -> str:
    """Fast scrape using requests + BeautifulSoup (no JS rendering)."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 404:
            return "EXPIRED"
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  Warning: Could not fetch {url}: {e}")
        return ""

    return _extract_text_from_html(resp.text)


def _scrape_with_playwright(url: str) -> str:
    """Fallback scrape using Playwright headless Chromium (renders JavaScript)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  Warning: Playwright not installed. Run: pip install playwright && playwright install chromium")
        return ""

    print("  Using Playwright for JS-rendered page...")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            # Wait for dynamic content to render
            page.wait_for_timeout(3000)
            html = page.content()
            browser.close()
        return _extract_text_from_html(html)
    except Exception as e:
        print(f"  Warning: Playwright scrape failed: {e}")
        return ""


def scrape_job_description(url: str) -> str:
    """Fetch and extract job description text from a URL.
    Tries fast requests first, falls back to Playwright for JS-rendered pages.
    Returns "EXPIRED" if the job posting is no longer available."""
    if not url:
        return ""

    # Try fast requests-based scraping first
    text = _scrape_with_requests(url)
    if text == "EXPIRED":
        return "EXPIRED"

    # If result is too short or indicates JS-only page, try Playwright
    js_indicators = ["enable javascript", "enable cookies", "browser doesn't support"]
    if len(text) < 200 or any(ind in text.lower() for ind in js_indicators):
        playwright_text = _scrape_with_playwright(url)
        if len(playwright_text) > len(text):
            text = playwright_text

    # Check for common "job no longer available" indicators
    expired_indicators = [
        "no longer available", "no longer accepting", "position has been filled",
        "job has expired", "this job is closed", "posting has been removed",
    ]
    if text and any(ind in text.lower() for ind in expired_indicators):
        return "EXPIRED"

    # Check for bot/security block pages (Cloudflare, etc.)
    blocked_indicators = [
        "sorry, you have been blocked", "cloudflare", "ray id",
        "access denied", "security check", "checking your browser",
        "please verify you are a human", "captcha",
        "not authorized to access",
    ]
    if text and any(ind in text.lower() for ind in blocked_indicators):
        print("  Warning: Scrape returned a security block page (Cloudflare/bot detection).")
        return ""

    return text


# ---------------------------------------------------------------------------
# Claude API — Resume Tailoring
# ---------------------------------------------------------------------------
def tailor_resume(
    job_description: str,
    experience_pool: str,
    base_tex: str,
    reference_tex: str,
    company: str,
    role_title: str,
    level: str,
    location: str,
) -> str:
    """Use Claude to generate a tailored LaTeX resume."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    system_prompt = SYSTEM_PROMPT_FILE.read_text()

    user_prompt_template = USER_PROMPT_FILE.read_text()
    user_prompt = user_prompt_template.format(
        company=company,
        role_title=role_title,
        level=level,
        location=location,
        job_description=job_description,
        experience_pool=experience_pool,
        base_tex=base_tex,
        reference_tex=reference_tex,
    )

    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=8192,
        messages=[{"role": "user", "content": user_prompt}],
        system=system_prompt,
    )

    content = message.content[0].text

    # Strip markdown fences if present
    content = re.sub(r"^```(?:latex|tex)?\s*\n", "", content)
    content = re.sub(r"\n```\s*$", "", content)

    return content


# ---------------------------------------------------------------------------
# Claude API — Match Scoring
# ---------------------------------------------------------------------------
def score_resume(job_description: str, tailored_tex: str, company: str, role_title: str) -> str:
    """Use Claude to score how well the tailored resume matches the job description."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2048,
        system="""\
You are a resume-job matching analyst. Evaluate how well a resume matches a job description. \
Be specific, actionable, and honest.""",
        messages=[
            {
                "role": "user",
                "content": f"""\
## Job Posting: {role_title} at {company}

### Job Description:
{job_description}

### Tailored Resume (LaTeX source):
{tailored_tex}

---

Provide a match report in this exact format:

# Match Report: {role_title} at {company}

## Overall Match Score: XX%

## Matched Keywords & Skills
- keyword1 (found as: "exact text in resume")
- keyword2 (found as: "exact text in resume")
...

## Missing Keywords & Requirements
- missing_keyword1 — why it matters
- missing_keyword2 — why it matters
...

## Suggestions for Improvement
1. suggestion1
2. suggestion2
...

## Summary
Brief 2-3 sentence summary of the match quality.
""",
            }
        ],
    )

    return message.content[0].text


# ---------------------------------------------------------------------------
# Git Operations
# ---------------------------------------------------------------------------
def slugify(text: str) -> str:
    """Convert text to a URL/branch-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text[:50].strip("-")


def git_run(*args: str) -> str:
    """Run a git command in the repo directory."""
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout.strip()


def create_branch(company: str, role_title: str, count: int) -> str:
    """Create and checkout a new branch for this job's resume.
    Uses the Notion count number to ensure unique branch names."""
    branch = f"resume/{slugify(company)}-{slugify(role_title)}-{count}"

    # Ensure we start from main
    git_run("checkout", "main")

    # Delete if it already exists (re-run scenario)
    existing = git_run("branch", "--list", branch)
    if existing:
        git_run("branch", "-D", branch)

    git_run("checkout", "-b", branch)
    return branch


def get_github_pdf_url(branch: str) -> str:
    """Construct a GitHub URL to view the PDF on a branch."""
    remote_url = git_run("remote", "get-url", "origin")
    # Convert git@github.com:user/repo.git or https://github.com/user/repo.git to base URL
    remote_url = remote_url.replace(".git", "")
    if remote_url.startswith("git@github.com:"):
        remote_url = remote_url.replace("git@github.com:", "https://github.com/")
    return f"{remote_url}/blob/{branch}/main.pdf"


def commit_and_return(branch: str, company: str, role_title: str, match_score: str):
    """Commit the tailored resume, push to remote, and switch back to main."""
    git_run("add", "main.tex", "main.pdf", "match_report.txt")
    git_run(
        "commit",
        "-m",
        f"Tailored resume for {role_title} at {company}\n\n{match_score}",
    )
    git_run("push", "-u", "origin", branch)
    git_run("checkout", "main")


# ---------------------------------------------------------------------------
# LaTeX Compilation
# ---------------------------------------------------------------------------
def compile_latex() -> tuple[bool, int]:
    """Compile main.tex to PDF using pdflatex. Returns (success, page_count)."""
    result = subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "main.tex"],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"  Warning: pdflatex failed. Output:\n{result.stdout[-500:]}")
        return False, 0
    # Run twice for references
    result2 = subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "main.tex"],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
    )
    # Parse page count from pdflatex log
    page_count = 1
    match = re.search(r"Output written on main\.pdf \((\d+) page", result2.stdout)
    if match:
        page_count = int(match.group(1))
    return True, page_count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def process_job(job: dict, experience_pool: str, base_tex: str, reference_tex: str, skip_manual: bool = False, manual: bool = False) -> str:
    """Process a single job posting: tailor, branch, compile, score, commit, update Notion.
    Returns a status string: 'Completed (XX%)' or 'Skipped — <reason>'."""
    company = job["company"]
    role_title = job["role_title"]
    job_link = job["job_link"]
    print(f"\n{'='*60}")
    print(f"Processing: {role_title} at {company}")
    print(f"{'='*60}")

    # 1. Get job description (scrape, manual paste, or both)
    if manual:
        job_desc = ""
    else:
        print("  Scraping job description...")
        job_desc = scrape_job_description(job_link)
        if job_desc == "EXPIRED":
            print(f"  Job posting is no longer available. Marking as expired in Notion.")
            mark_job_expired(job["page_id"])
            return "Skipped — job expired"

    if not job_desc or len(job_desc) < 200:
        if not manual:
            print(f"  Could not scrape job description from: {job_link}")
            if skip_manual:
                print("  Skipping (--skip-manual).")
                return "Skipped — scrape failed"
        print("  Paste the job description below (press Enter twice when done):")
        lines = []
        empty_count = 0
        while True:
            try:
                line = input()
            except EOFError:
                break
            if line == "":
                empty_count += 1
                if empty_count >= 2:
                    break
            else:
                empty_count = 0
            lines.append(line)
        job_desc = "\n".join(lines).strip()
        if not job_desc:
            print("  Skipping — no job description provided.")
            return "Skipped — no description"
        print(f"  Received job description ({len(job_desc)} chars).")

    # 2. Tailor resume
    print("  Tailoring resume with Claude...")
    tailored_tex = tailor_resume(
        job_description=job_desc,
        experience_pool=experience_pool,
        base_tex=base_tex,
        reference_tex=reference_tex,
        company=company,
        role_title=role_title,
        level=job["level"],
        location=job["location"],
    )

    # 3. Create branch and write files
    print("  Creating git branch...")
    branch = create_branch(company, role_title, job["count"])

    tex_path = REPO_DIR / "main.tex"
    tex_path.write_text(tailored_tex)

    # 4. Compile LaTeX
    print("  Compiling LaTeX...")
    compiled, page_count = compile_latex()
    if not compiled:
        print("  Warning: PDF compilation failed — committing .tex anyway.")
    if page_count > 1:
        print(f"  WARNING: Resume is {page_count} pages (expected 1)")

    # 5. Score the resume
    print("  Scoring resume match...")
    match_report = score_resume(job_desc, tailored_tex, company, role_title)

    report_path = REPO_DIR / "match_report.txt"
    report_path.write_text(match_report)

    # Extract score line and numeric score
    score_line = ""
    score_number = 0
    for line in match_report.splitlines():
        if "Overall Match Score" in line:
            score_line = line.strip()
            # Extract number from e.g. "## Overall Match Score: 78%"
            match = re.search(r"(\d+)%", line)
            if match:
                score_number = int(match.group(1))
            break

    print(f"  {score_line}")
    print(f"\n{match_report}\n")

    # 6. Commit, push, and return to main
    print("  Committing and pushing...")
    commit_and_return(branch, company, role_title, score_line)

    # 7. Update Notion with clickable PDF link and score
    pdf_url = get_github_pdf_url(branch)
    print(f"  Updating Notion — score: {score_number}%, PDF: {pdf_url}")
    update_notion_results(job["page_id"], pdf_url, score_number, match_report)

    print(f"  Done! Branch: {branch}")
    status = f"Completed ({score_number}%)"
    if page_count > 1:
        status += f" — WARNING: {page_count} pages"
    return status


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(prog="job-pipeline tailor", description="Write a tailored resume for each job in Notion that doesn't have one.")
    parser.add_argument("--limit", type=int, default=0, help="Max number of jobs to process (0 = all)")
    parser.add_argument("--company", type=str, default="", help="Only process jobs from this company (case-insensitive substring match)")
    parser.add_argument("--role", type=str, default="", help="Only process jobs matching this role (case-insensitive substring match)")
    parser.add_argument("--skip-manual", action="store_true", help="Skip jobs that can't be scraped instead of prompting for manual paste")
    parser.add_argument("--manual", action="store_true", help="Skip scraping entirely and prompt to paste the job description for every job")
    parser.add_argument("--account", type=str, default=CLAUDE_ACCOUNT, help="Which Claude API key to use: reads ANTHROPIC_API_KEY_<ACCOUNT> from .env (default: CLAUDE_ACCOUNT in .env)")
    args = parser.parse_args(argv)

    use_claude_account(args.account)
    check_config(args.account)
    print(f"Claude account: {args.account or 'default'}")

    # Load static files
    experience_pool = EXPERIENCE_FILE.read_text()
    base_tex = BASE_TEX_FILE.read_text()
    reference_tex = REFERENCE_TEX_FILE.read_text()

    # Connect to Notion and fetch jobs
    init_notion_headers()
    print("Querying Notion for jobs without resumes...")
    jobs = query_jobs_without_resume()

    if not jobs:
        print("No jobs found that need resumes. All caught up!")
        return

    if args.company:
        jobs = [j for j in jobs if args.company.lower() in j["company"].lower()]
    if args.role:
        jobs = [j for j in jobs if args.role.lower() in j["role_title"].lower()]
    if args.limit:
        jobs = jobs[: args.limit]

    print(f"Found {len(jobs)} job(s) to process.")

    results = []  # list of (company, role, status)

    for job in jobs:
        company = job.get("company", "?")
        role = job.get("role_title", "?")
        try:
            status = process_job(job, experience_pool, base_tex, reference_tex, skip_manual=args.skip_manual, manual=args.manual)
            results.append((company, role, status))
        except KeyboardInterrupt:
            print("\n\n  Interrupted by user. Cleaning up...")
            results.append((company, role, "Interrupted"))
            try:
                git_run("checkout", "main")
            except RuntimeError:
                pass
            break
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
            print(f"\n  API authentication error: {e}")
            print(f"  Check {api_key_var(args.account)} in .env. Stopping batch.")
            results.append((company, role, "Failed — API auth error"))
            try:
                git_run("checkout", "main")
            except RuntimeError:
                pass
            break
        except anthropic.RateLimitError as e:
            print(f"\n  API rate limit or out of credits: {e}")
            print("  Check your Anthropic account balance. Stopping batch.")
            results.append((company, role, "Failed — out of credits"))
            try:
                git_run("checkout", "main")
            except RuntimeError:
                pass
            break
        except requests.RequestException as e:
            print(f"\n  Notion API error: {e}")
            results.append((company, role, "Failed — Notion API error"))
            try:
                git_run("checkout", "main")
            except RuntimeError:
                pass
            continue
        except RuntimeError as e:
            print(f"\n  Git error: {e}")
            results.append((company, role, "Failed — git error"))
            try:
                git_run("checkout", "main")
            except RuntimeError:
                pass
            continue
        except Exception as e:
            print(f"\n  Unexpected error: {e}")
            results.append((company, role, f"Failed — {type(e).__name__}"))
            try:
                git_run("checkout", "main")
            except RuntimeError:
                pass
            continue

    # Mark remaining jobs that weren't reached
    processed_count = len(results)
    for job in jobs[processed_count:]:
        results.append((job.get("company", "?"), job.get("role_title", "?"), "Not processed"))

    # Print summary table
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    if results:
        col_w1 = max(len(r[0]) for r in results)
        col_w2 = max(len(r[1]) for r in results)
        header = f"  {'Company':<{col_w1}}  {'Role':<{col_w2}}  Status"
        print(header)
        print(f"  {'-'*col_w1}  {'-'*col_w2}  {'-'*25}")
        for company, role, status in results:
            print(f"  {company:<{col_w1}}  {role:<{col_w2}}  {status}")

    completed = sum(1 for _, _, s in results if s.startswith("Completed"))
    skipped = sum(1 for _, _, s in results if s.startswith("Skipped"))
    failed = sum(1 for _, _, s in results if s.startswith("Failed"))
    not_processed = sum(1 for _, _, s in results if s == "Not processed")
    print(f"\n  Completed: {completed} | Skipped: {skipped} | Failed: {failed}", end="")
    if not_processed:
        print(f" | Not processed: {not_processed}")
    else:
        print()
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
