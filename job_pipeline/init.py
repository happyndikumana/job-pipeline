"""
job-pipeline init — create the starter files in a new resume folder.

Run it inside the (empty) git repo that will hold your resume. It never
overwrites a file that already exists.
"""

import argparse
import shutil
from pathlib import Path

TEMPLATES = Path(__file__).parent / "templates"

# template file -> where it goes in your resume folder
STARTER_FILES = {
    "experience.md": "experience.md",
    "system.txt": "prompts/system.txt",
    "env.example": ".env.example",
    "gitignore": ".gitignore",
    "requirements.txt": "requirements.txt",
}


def main(argv=None):
    argparse.ArgumentParser(
        prog="job-pipeline init",
        description="Create the starter files in the current folder. Never overwrites existing files.",
    ).parse_args(argv)

    root = Path.cwd()
    print(f"Setting up {root}")
    for template, dest in STARTER_FILES.items():
        target = root / dest
        if target.exists():
            print(f"  kept     {dest} (already exists)")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(TEMPLATES / template, target)
        print(f"  created  {dest}")
    print(
        "\nNext:\n"
        "  1. Fill in experience.md with everything you've done.\n"
        "  2. Add your resume as main.tex and a full one-page example as reference_resume.tex.\n"
        "  3. Replace every <FILL IN ...> in prompts/system.txt.\n"
        "  4. Copy .env.example to .env and add your keys."
    )


if __name__ == "__main__":
    main()
