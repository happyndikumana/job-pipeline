"""
job-pipeline notion — create your Notion job tracker, or fix the columns of an existing one.

Needs NOTION_TOKEN in .env (the secret of a Notion integration you created).

- With no NOTION_DATABASE_ID in .env: creates a "Job Tracker" database inside a
  Notion page you shared with the integration, then saves its ID to .env.
- With NOTION_DATABASE_ID set: checks that tracker, adds any missing columns,
  and reports columns that have the wrong type (those you fix in Notion).
"""

import argparse
import re
import sys
from pathlib import Path

import requests
from dotenv import dotenv_values

NOTION_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

# Application Stage options, in pipeline order. The tailor needs "Job Expired".
STAGES = [
    "Not Applied", "Not Applying", "Getting Referral", "Applied", "Online Assessment",
    "Phone Screen", "Technical Interview", "2nd Round", "Leadership Round", "Final Round",
    "Offer", "Rejected", "Withdrawn", "Job Expired",
]

# Columns the tailor reads and writes: name -> (accepted types, how to create it)
REQUIRED = {
    "Company": (("title",), {"title": {}}),
    "Role Title": (("rich_text",), {"rich_text": {}}),
    "Level": (("select",), {"select": {"options": []}}),
    "Location": (("rich_text",), {"rich_text": {}}),
    "Job Link": (("url",), {"url": {}}),
    "count": (("unique_id", "number"), {"unique_id": {"prefix": None}}),
    "Application Stage": (("select",), {"select": {"options": [{"name": s} for s in STAGES]}}),
    "Resume Version": (("rich_text",), {"rich_text": {}}),
    "Resume Score": (("rich_text",), {"rich_text": {}}),
    "Resume Match Report": (("rich_text",), {"rich_text": {}}),
}

# Handy extras added only when creating a new tracker.
EXTRAS = {
    "Date Applied": {"date": {}},
    "Notes": {"rich_text": {}},
}


class NotionError(Exception):
    pass


def notion(method: str, path: str, token: str, body: dict = None) -> dict:
    resp = requests.request(
        method, f"{NOTION_BASE}{path}", json=body, timeout=30,
        headers={"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION},
    )
    data = resp.json()
    if resp.status_code >= 400:
        raise NotionError(f"{data.get('code', resp.status_code)}: {data.get('message', resp.text)}")
    return data


def title_of(obj: dict) -> str:
    if obj["object"] == "database":
        parts = obj.get("title", [])
    else:
        prop = next((p for p in obj.get("properties", {}).values() if p.get("type") == "title"), {})
        parts = prop.get("title", [])
    return "".join(t.get("plain_text", "") for t in parts) or "(untitled)"


def save_env_value(env_path: Path, key: str, value: str):
    """Set KEY=value in .env, replacing an existing line or adding one."""
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    out, done = [], False
    for line in lines:
        if line.split("=", 1)[0].strip() == key:
            out.append(f"{key}={value}")
            done = True
        else:
            out.append(line)
    if not done:
        out.append(f"{key}={value}")
    env_path.write_text("\n".join(out) + "\n")


def shared_pages(token: str) -> list:
    """Every page the integration can see that isn't a row of a database."""
    pages, cursor = [], None
    while True:
        body = {"filter": {"property": "object", "value": "page"}, "page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        found = notion("POST", "/search", token, body)
        pages += [p for p in found["results"] if p["parent"]["type"] != "database_id" and not p.get("archived")]
        if not found.get("has_more"):
            return pages
        cursor = found["next_cursor"]


def page_id_in(text: str) -> str:
    """The 32-character page ID in a Notion link or ID, or '' if there isn't one."""
    match = re.search(r"([0-9a-f]{32})(?:[?#]|$)", text.replace("-", "").split("?")[0] + "?")
    return match.group(1) if match else ""


def create_tracker(token: str, page_name: str, env_path: Path):
    link_id = page_id_in(page_name) if page_name else ""
    if link_id:
        # A page link opens the page directly (search can lag behind new shares).
        try:
            pages = [notion("GET", f"/pages/{link_id}", token)]
        except NotionError:
            pages = []
    else:
        pages = shared_pages(token)
        if page_name:
            pages = [p for p in pages if title_of(p).lower() == page_name.lower()]

    if not pages:
        me = notion("GET", "/users/me", token)
        name = me.get("name") or "your integration"
        print(f'Your integration "{name}" can\'t see any Notion page to put the tracker in.' if not page_name
              else f'"{name}" can\'t open that page: {page_name}')
        print(f'Open (or make) a page in Notion, click ••• → Connections, add "{name}", then run this again.')
        sys.exit(1)
    if len(pages) > 1:
        print("Your integration can see several pages. Pick one with --page:")
        for p in pages:
            print(f'  job-pipeline notion --page "{title_of(p)}"')
        sys.exit(1)

    page = pages[0]
    properties = {name: spec for name, (_, spec) in REQUIRED.items()}
    properties.update(EXTRAS)
    body = {
        "parent": {"type": "page_id", "page_id": page["id"]},
        "title": [{"type": "text", "text": {"content": "Job Tracker"}}],
        "properties": properties,
    }
    try:
        db = notion("POST", "/databases", token, body)
    except NotionError:
        # Fall back to a plain Number column if auto-numbered IDs can't be created.
        properties["count"] = {"number": {}}
        db = notion("POST", "/databases", token, body)

    save_env_value(env_path, "NOTION_DATABASE_ID", db["id"].replace("-", ""))
    count_type = db["properties"]["count"]["type"]
    print(f'Created "Job Tracker" in the page "{title_of(page)}" and saved its ID to .env.')
    print(f"  {db.get('url', '')}")
    if count_type == "unique_id":
        print("The count column numbers each job automatically.")
    else:
        print("Give each job its own number in the count column.")


def fix_tracker(token: str, database_id: str):
    try:
        db = notion("GET", f"/databases/{database_id}", token)
    except NotionError as e:
        print(f"Can't open the tracker in NOTION_DATABASE_ID ({e}).")
        print("In Notion, open the tracker, click ••• → Connections, and add your integration. Then run this again.")
        sys.exit(1)

    props = db["properties"]
    to_add, wrong = {}, []
    for name, (types, spec) in REQUIRED.items():
        if name not in props:
            to_add[name] = spec
        elif props[name]["type"] not in types:
            wrong.append(f'"{name}" is {props[name]["type"]}, should be {" or ".join(types)}')

    stage = props.get("Application Stage", {})
    if stage.get("type") == "select":
        options = stage["select"]["options"]
        if "Job Expired" not in [o["name"] for o in options]:
            to_add["Application Stage"] = {"select": {"options": [{"id": o["id"], "name": o["name"], "color": o["color"]} for o in options] + [{"name": "Job Expired"}]}}

    print(f'Tracker: "{title_of(db)}"')
    if to_add:
        notion("PATCH", f"/databases/{database_id}", token, {"properties": to_add})
        for name in to_add:
            print(f"  added    {name}" if name not in props else f'  updated  {name} (added the "Job Expired" option)')
    for line in wrong:
        print(f"  WRONG    {line}. Change it in Notion.")
    if not to_add and not wrong:
        print("  All the columns the pipeline needs are there.")
    if wrong:
        sys.exit(1)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="job-pipeline notion",
        description="Create your Notion job tracker, or add any missing columns to the one in NOTION_DATABASE_ID.",
    )
    parser.add_argument("--page", default="", help="The Notion page to create the tracker in: its link (most reliable) or its exact name")
    args = parser.parse_args(argv)

    env_path = Path.cwd() / ".env"
    env = dotenv_values(env_path) if env_path.exists() else {}
    token = (env.get("NOTION_TOKEN") or "").strip()
    if not token or token.startswith("secret_your"):
        print("Add NOTION_TOKEN to .env first: the secret of the integration you made at")
        print("https://www.notion.so/profile/integrations")
        sys.exit(1)

    database_id = (env.get("NOTION_DATABASE_ID") or "").strip()
    try:
        if database_id and database_id != "your_notion_database_id":
            fix_tracker(token, database_id)
        else:
            create_tracker(token, args.page, env_path)
    except NotionError as e:
        print(f"Notion error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
