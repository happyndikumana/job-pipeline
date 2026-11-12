# job-pipeline

A job-hunt pipeline that runs on your own laptop, one command per stage.

## Get started

### What you need

- A Mac or a Windows PC with about 5 GB free, and your computer's password. On Windows, read [Windows](#windows) first.
- [Claude Code](https://claude.com/claude-code), to run the setup for you
- A **Claude API key** from https://console.anthropic.com, with a few dollars of credit added (the key won't work without it; each tailored resume costs roughly 10–15 cents)
- A **GitHub** account
- A **Notion** account, as owner of the workspace you'll use
- Your **master resume** (everything you've ever done, any format) and a **model resume** (one page, in the look you want)

### Then let Claude Code set you up

Open Claude Code in Terminal and paste:

```text
Fetch https://raw.githubusercontent.com/happyndikumana/job-pipeline/main/SETUP_PROMPT.md and follow its steps to set me up.
```

It installs the tools, makes your resume repo, turns your two resumes into your resume files, builds your Notion tracker, and runs a first test. Expect to do these few things yourself when it asks:

- type your Mac password, and log in to GitHub in the browser
- create an empty private repo on GitHub
- create a Notion integration and copy its secret
- paste your keys into the `.env` file it opens for you
- make an empty Notion page, connect the integration to it, and paste the page's link
- check your experience file and your resume layout

After that, see [Using it](#using-it) for the everyday steps.

## What it does

**Today — `tailor`:** for every job in your Notion tracker that doesn't have a resume yet, it:

1. Reads the job description from the job link (or asks you to paste it).
2. Has Claude pick the best items from your experience file and fill in your own resume layout.
3. Builds the PDF and checks that it fits on one page.
4. Scores the resume against the job description.
5. Saves the resume on its own branch in your GitHub repo, then puts the PDF link, the score and a match report in Notion.

**Later — `search`:** find jobs and add them to your Notion tracker.

| Command | What it does |
|---|---|
| `job-pipeline init` | Creates the starter files in a new resume folder |
| `job-pipeline notion` | Creates your Notion job tracker, or adds missing columns to the one you have |
| `job-pipeline tailor` | Writes a tailored resume for each job in Notion that doesn't have one |

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

**4. Keys.** Run `cp .env.example .env`, then fill in:

- `ANTHROPIC_API_KEY`: your Claude API key
- `NOTION_TOKEN`: at https://www.notion.so/profile/integrations, create an internal integration in your workspace and copy its secret. Only a workspace owner can do this.

**5. Your Notion tracker.** Notion only lets the integration into pages you share with it, so this part takes two clicks:

1. In Notion, make an empty page, for example "Job Search".
2. On that page, click **•••** → **Connections** and add your integration. Then click **•••** → **Copy link**.

Then build the tracker inside it:

```bash
./venv/bin/job-pipeline notion --page "PASTE-THE-PAGE-LINK"
```

It creates a "Job Tracker" with every column the pipeline needs and saves its ID to `.env`.

**Already have a tracker?** Share the tracker itself with the integration (**•••** → **Connections**), put its ID in `.env` as `NOTION_DATABASE_ID` (the 32-character code in its link, just before `?v=`), and run `./venv/bin/job-pipeline notion`. It adds any missing columns and names any that have the wrong type, so you can fix those in Notion.

The columns it makes:

| Column | Type | Notes |
|---|---|---|
| Company | Title | |
| Role Title | Text | |
| Job Link | URL | |
| Level | Select | Optional to fill in |
| Location | Text | Optional to fill in |
| count | ID | Numbers each job by itself. An older tracker can use a Number column instead. |
| Application Stage | Select | 14 stages, from Not Applied to Offer. The pipeline needs `Job Expired`. |
| Resume Version | Text | Leave empty. The pipeline fills it in. |
| Resume Score | Text | The pipeline fills it in. |
| Resume Match Report | Text | The pipeline fills it in. |
| Date Applied, Notes | Date, Text | For you. The pipeline ignores them. |

## Windows

Everything works the same on Windows; only the commands differ. Use **PowerShell**, and reopen it after installing anything so new commands are found. If you're setting up with Claude Code, close and reopen **Claude Code itself** after the tools install, or it won't find LaTeX. These Windows steps are new: if one doesn't work on your PC, please open an issue on this repo.

**Before Claude Code:** Claude Code on Windows needs Git, so install Git first, then [Claude Code](https://claude.com/claude-code):

```powershell
winget install --id Git.Git -e
```

Then follow [Then let Claude Code set you up](#then-let-claude-code-set-you-up). The setup prompt handles Windows.

**Setting up by hand on Windows**

1. Tools:

   ```powershell
   winget install --id Python.Python.3.12 -e
   winget install --id GitHub.cli -e
   winget install --id MiKTeX.MiKTeX -e
   gh auth login
   ```

   Then open **MiKTeX Console** → **Settings** and choose **Always install missing packages on-the-fly**, so LaTeX fetches what your resume needs without stopping to ask.

2. Your resume repo:

   ```powershell
   mkdir -Force $HOME\Repos; cd $HOME\Repos
   git clone https://github.com/YOUR-USERNAME/YOUR-REPO.git
   cd YOUR-REPO
   py -m venv venv
   .\venv\Scripts\pip install git+https://github.com/happyndikumana/job-pipeline.git
   .\venv\Scripts\playwright install chromium
   .\venv\Scripts\job-pipeline init
   ```

3. Steps 3–5 of [Set up by hand](#set-up-by-hand) are the same, with these swaps: `copy .env.example .env`, `notepad .env`, and `.\venv\Scripts\job-pipeline notion --page "PASTE-THE-PAGE-LINK"`.

**Using it on Windows**

```powershell
cd $HOME\Repos\YOUR-REPO
git checkout main; git pull
.\venv\Scripts\job-pipeline tailor
```

The options are the same as on a Mac.

**Updating on Windows**

```powershell
.\venv\Scripts\pip install --force-reinstall --no-deps -r requirements.txt
```

## Using it

The commands below are for a Mac; on Windows, see [Windows](#windows).

1. Add jobs to your tracker: **Company**, **Role Title** and **Job Link**. Leave Resume Version empty.
2. Run:

```bash
cd ~/Repos/YOUR-REPO
git checkout main && git pull
./venv/bin/job-pipeline tailor
```

3. Each finished job gets a **View Resume** link, a score and a match report in Notion. Read the resume before you send it.

| Option | What it does |
|---|---|
| `--limit 3` | Only do 3 jobs |
| `--company adobe` | Only jobs whose company contains "adobe" |
| `--role product` | Only jobs whose title contains "product" |
| `--manual` | Paste every job description yourself |
| `--skip-manual` | Skip jobs whose page can't be read, instead of asking you to paste |
| `--account work` | Use a different Claude API key for this run |

**Commit first:** if you've edited `experience.md` or any other file, commit and push it before running. The pipeline won't start while tracked files have uncommitted changes, so your work can't leak into a resume branch or get lost.

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
