"""
job-pipeline — one command, one step per stage of the job hunt.

    job-pipeline init      set up the starter files in a new resume folder
    job-pipeline tailor    write a tailored resume for each new job in Notion
"""

import sys

COMMANDS = {
    "init": "Set up the starter files in a new resume folder",
    "tailor": "Write a tailored resume for each job in Notion that doesn't have one",
}


def usage():
    print("Usage: job-pipeline <command> [options]\n\nCommands:")
    for name, about in COMMANDS.items():
        print(f"  {name:8} {about}")
    print("\nRun 'job-pipeline <command> --help' to see a command's options.")


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        usage()
        return
    command, rest = args[0], args[1:]
    if command not in COMMANDS:
        print(f"Unknown command: {command}\n")
        usage()
        sys.exit(1)

    # Import per command: tailor loads .env and the API clients, init needs neither.
    if command == "init":
        from job_pipeline import init
        init.main(rest)
    elif command == "tailor":
        from job_pipeline import tailor
        tailor.main(rest)


if __name__ == "__main__":
    main()
