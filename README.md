# job-pipeline

A job-hunt pipeline that runs on your own laptop, one command per stage.

**Today — `tailor`:** for every job in your Notion tracker that doesn't have a resume yet, it:

1. Reads the job description from the job link (or asks you to paste it).
2. Has Claude pick the best items from your experience file and fill in your own resume layout.
3. Builds the PDF and checks that it fits on one page.
4. Scores the resume against the job description.
5. Saves the resume on its own branch in your GitHub repo, then puts the PDF link, the score and a match report in Notion.

**Later — `search`:** find jobs and add them to your Notion tracker.

## How it's organized

There are two repos:

- **This one (shared, public):** the code. Everyone installs it, so a fix reaches everyone at once.
- **Your resume repo (private, yours):** your experience, your resume layout, your prompt and every tailored resume. No one else sees it.

Your resume repo holds:

| File | What it is |
|---|---|
| `experience.md` | Everything you've done. **The only source the AI may use.** |
| `main.tex` | Your resume layout, in LaTeX. |
| `reference_resume.tex` / `.pdf` | A full one-page example. The AI never writes more than this. |
| `prompts/system.txt` | The rules the AI follows, with your layout's limits filled in. |
| `requirements.txt` | Installs this code. |
| `.env` | Your keys. Stays on your laptop, never committed. |

## What you need

- A Mac (the steps below are for macOS)
- A GitHub account, a Notion job tracker, and a Claude API key
- Your **master resume** (everything you've ever done, any format) and a **model resume** (one page, in the layout you want)

## Set up with Claude Code (easiest)

Open Claude Code and give it [`SETUP_PROMPT.md`](SETUP_PROMPT.md). It installs the tools, makes your resume repo, turns your two resumes into the files above, sets up Notion and your keys, and runs a first test. It stops for anything that needs your password or a browser.

## Set up by hand

**1. Tools:**

```bash
brew install python gh              # Homebrew first, if needed: https://brew.sh
brew install --cask mactex-no-gui   # LaTeX, a large download
gh auth login                       # choose HTTPS, then log in with the browser
```

**2. Your resume repo.** On GitHub, create an empty **private** repo (no README). Then:

```bash
mkdir -p ~/Repos && cd ~/Repos
git clone https://github.com/YOUR-USERNAME/YOUR-REPO.git
cd YOUR-REPO
python3 -m venv venv
./venv/bin/pip install git+https://github.com/happyndikumana/job-pipeline.git
./venv/bin/playwright install chromium
./venv/bin/job-pipeline init        # creates the starter files
```

**3. Fill in the starter files:** `experience.md`, your layout as `main.tex` plus a full one-page example as `reference_resume.tex`, and every `<FILL IN ...>` in `prompts/system.txt`. Commit and push them, but never `.env`.

**4. Notion.** Your tracker needs these columns, with these exact names:

| Column | Type | Notes |
|---|---|---|
| Company | Title | |
| Role Title | Text | |
| Level | Select | Optional to fill in |
| Location | Text | Optional to fill in |
| Job Link | URL | |
| count | Number | Give each job its own number. It keeps branch names unique. |
| Application Stage | Select | Must include an option called `Job Expired` |
| Resume Version | Text | Leave empty. The script fills it in. |
| Resume Score | Text | The script fills it in. |
| Resume Match Report | Text | The script fills it in. |

Other columns are fine; the script ignores them. Then:

1. At https://www.notion.so/profile/integrations, create an integration and copy its secret. Only a workspace owner can do this.
2. Open your tracker, click **•••** → **Connections**, and add that integration.
3. Copy the database ID: the 32-character code in the tracker's URL, just before `?v=`.

**5. Keys:** run `cp .env.example .env`, then fill in `NOTION_TOKEN`, `NOTION_DATABASE_ID` and `ANTHROPIC_API_KEY`.

## Using it

```bash
cd ~/Repos/YOUR-REPO
git checkout main && git pull
./venv/bin/job-pipeline tailor
```

| Option | What it does |
|---|---|
| `--limit 3` | Only do 3 jobs |
| `--company adobe` | Only jobs whose company contains "adobe" |
| `--role product` | Only jobs whose title contains "product" |
| `--manual` | Paste every job description yourself |
| `--skip-manual` | Skip jobs whose page can't be read, instead of asking you to paste |
| `--account work` | Use a different Claude API key for this run |

**First run:** it picks up every job whose Resume Version is empty. Start with `--limit 1`, and type `n/a` in Resume Version for old jobs you don't want resumes for.

Some job pages can't be read (login walls, closed postings, bot blockers). The script then asks you to paste the description: paste it and press Enter twice.

## Updating

```bash
./venv/bin/pip install --force-reinstall --no-deps -r requirements.txt
```

## Claude accounts and models

`.env` can hold one key per account, such as `ANTHROPIC_API_KEY_WORK`. `CLAUDE_ACCOUNT` picks the default, and `--account work` switches for one run. `CLAUDE_MODEL` changes the model (default `claude-sonnet-4-6`).

## Keeping resumes accurate

- The AI may only use what's in `experience.md`. If something isn't there, it won't appear on a resume.
- Lines marked **Notes (not resume text)** are rules and facts for the AI, such as a word not to use. They never appear on the resume.
- Always read a resume before you send it.
