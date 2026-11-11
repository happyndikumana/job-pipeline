# Set up my job pipeline

Help me set up job-pipeline on this computer (a Mac or a Windows PC): https://github.com/happyndikumana/job-pipeline. It reads jobs from a Notion job tracker, uses the Claude API to write a one-page resume for each job from my experience file, builds the PDF with LaTeX, saves it in my own private GitHub repo, and puts the link and a match score back in Notion. Its `README.md` is the reference if anything here differs.

Go through the steps below in order. Before each step, tell me in one plain sentence what you're about to do. If a step fails, stop and show me the error instead of guessing.

## Ground rules

- Some steps need my computer's password, a browser login, a click in Notion, or a long download. For those, tell me exactly what to do (or give me the exact command to paste into my own Terminal window), wait until I say it's done, then check that it worked.
- Never ask me to paste a password, token, or API key into this chat, and never print the contents of `.env`. I'll type secrets into the `.env` file myself. Links to Notion pages are not secret; I can paste those here.
- Never invent anything about my experience. Everything in my files must come from my own resumes or from me.

## If I'm on Windows

Use PowerShell commands for anything I type myself, and make these swaps throughout:

- Install tools with winget instead of Homebrew: `winget install --id Python.Python.3.12 -e`, `winget install --id GitHub.cli -e` and `winget install --id MiKTeX.MiKTeX -e`. Git for Windows is already installed, because Claude Code needs it. After installing, have me reopen the terminal so the new commands are found.
- Make LaTeX install missing packages by itself: have me open MiKTeX Console → Settings and choose "Always install missing packages on-the-fly".
- Create the venv with `py -m venv venv`, and use `venv\Scripts\` wherever these steps say `venv/bin/` (in Git Bash, `venv/Scripts/`).
- Use `$HOME\Repos` for `~/Repos`, `copy` for `cp`, and `notepad .env` instead of `open -e .env`.
- Read a .docx with python-docx (install it into the venv) instead of `textutil`.
- Open a PDF for me with `start` instead of `open`.

## Before you start

Ask me for, and wait until I have:

- my **master resume** (everything I've done, any format) and my **model resume** (one page, in the layout I want), as file paths
- a **Claude API key**, with credit added at https://console.anthropic.com
- a **GitHub** account and a **Notion** account
- about **5 GB** of free disk space (LaTeX is large)

## Steps

1. **Check what's installed:** Homebrew (Mac only), git, Python 3, the GitHub CLI (`gh`), and LaTeX (`pdflatex`). Skip anything I already have.

2. **Install what's missing.** On Windows, follow "If I'm on Windows" above instead of this step. On a Mac: Homebrew comes from https://brew.sh. After it installs, run the "Next steps" commands it prints so `brew` is on my PATH. Then:

   ```bash
   brew install python gh
   brew install --cask mactex-no-gui
   ```

   `pdflatex` lives in `/Library/TeX/texbin`. If it isn't found right after installing, use that full path or open a new Terminal window.

3. **Sign me in to GitHub.** I run `gh auth login` myself (choose GitHub.com, HTTPS, and log in with the browser). Then you run `gh auth setup-git`.

4. **Make my resume repo.** Ask me to create an empty **private** repo on GitHub (no README) and tell you its name. Then:

   ```bash
   mkdir -p ~/Repos && cd ~/Repos
   git clone https://github.com/MY-USERNAME/MY-REPO.git
   cd MY-REPO
   python3 -m venv venv
   ./venv/bin/pip install git+https://github.com/happyndikumana/job-pipeline.git
   ./venv/bin/playwright install chromium
   ./venv/bin/job-pipeline init
   ```

5. **Build `experience.md` from my master resume.** Extract all of its text (for a .docx, `textutil -convert txt`; for a PDF, read it). Fill in the starter `experience.md`, keeping its format: every role, title, date, location and bullet, word for word. Summarize nothing and add nothing. If the resume has notes to self (instructions such as "don't call it X", or remarks on what was verified), move them word for word onto that entry's "Notes (not resume text)" line, and tell me each one you moved. Then check both ways: every line of the original is in the file, and nothing in the file is missing from the original. Report the bullet counts.

6. **Build my LaTeX layout from my model resume.** Recreate its look as `main.tex` as closely as you can: font, sizes, margins, section headings, and how each entry's header line reads. If it's a PDF, measure sizes and positions from the file rather than guessing. Rules:
   - Use simple custom commands for each kind of entry, and put all spacing inside the command definitions, so the body never needs manual spacing.
   - Use `\usepackage[T1]{fontenc}`, and add `\input{glyphtounicode}` and `\pdfgentounicode=1` so applicant tracking systems can read the PDF.
   - Compile in a temporary folder. It must be exactly 1 page with no overfull boxes. Compare it with my model resume and fix differences until they match.
   - Save the same document as `reference_resume.tex`, with a header comment saying it's the full one-page example, and keep its compiled `reference_resume.pdf`.
   - If my model resume has facts that aren't in `experience.md`, list them and ask me which to add. Never add them on your own.

7. **Finish `prompts/system.txt`.** Replace every `<FILL IN ...>` using my reference resume: the section order, the most entries and bullets per section (counted from it), how many characters fit on one printed bullet line (measure it), and which command to use for each kind of entry. Don't change the other rules.

8. **Get my Notion key.** Walk me through it and wait for me: at https://www.notion.so/profile/integrations, create a new internal integration in my workspace, name it "Job Pipeline", and keep its secret handy. Only a workspace owner can do this.

9. **Create my `.env`:** run `cp .env.example .env`, then open it for me with `open -e .env`. I'll fill in `NOTION_TOKEN` (the integration secret) and `ANTHROPIC_API_KEY`, and save. Then, for each of those names, print only "set" or "missing", and treat the example placeholder text as missing.

10. **Build my job tracker in Notion.** Notion only lets the integration into pages I share with it, so ask me to:
    1. make an empty page in Notion, for example "Job Search";
    2. on that page, click ••• → Connections and add "Job Pipeline";
    3. click ••• → Copy link, and paste the link here.

    Then run:

    ```bash
    ./venv/bin/job-pipeline notion --page "THE-LINK-I-PASTED"
    ```

    It creates a "Job Tracker" with every column the pipeline needs and saves its ID to `.env`. Show me its output.

    If I'd rather use a tracker I already have: ask me to share that tracker with "Job Pipeline" (••• → Connections) and to add its ID to `.env` as `NOTION_DATABASE_ID` (the 32-character code in its link, just before `?v=`). Then run `./venv/bin/job-pipeline notion` with no `--page`. It adds any missing columns and names any with the wrong type; walk me through fixing those in Notion and run it again until it says everything is there.

11. **Check that the Claude key works** without spending money: with the venv's Python, create `anthropic.Anthropic(api_key=<ANTHROPIC_API_KEY from .env>)` and call `client.models.list()`. Print only "Claude key works" or the error.

12. **Save my files to GitHub.** Show me `git status` first. Commit `experience.md`, `main.tex`, `reference_resume.tex`, `reference_resume.pdf`, `prompts/system.txt`, `requirements.txt`, `.gitignore` and `.env.example`, then push to `main`. Never commit `.env`.

13. **First real test:** ask me to add one job to my tracker: **Company**, **Role Title** and **Job Link**, with Resume Version left empty (the count column numbers itself). If my tracker already has old jobs I don't want resumes for, have me type "n/a" in their Resume Version. Then run:

    ```bash
    ./venv/bin/job-pipeline tailor --limit 1
    ```

    If the job page can't be read, the script asks me to paste the description: I paste it and press Enter twice. When it finishes, show me the Notion link and the match score, and open the PDF so I can read it.

14. **Wrap up** with a short summary of what's set up and how I run it from now on:

    ```bash
    cd ~/Repos/MY-REPO
    git checkout main && git pull
    ./venv/bin/job-pipeline tailor
    ```

    And how to update the shared code: `./venv/bin/pip install --force-reinstall --no-deps -r requirements.txt`
