import json, os, time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

JST = ZoneInfo("Asia/Tokyo")
ROOT = Path(__file__).resolve().parent
API = "https://api.buffer.com"
KEY = os.environ["BUFFER_API_KEY"]
CHANNEL = os.getenv("BUFFER_CHANNEL_NAME", "VENUTRIP_JP")
REPO = os.environ["GITHUB_REPOSITORY"]
SHA = os.environ["GITHUB_SHA"]

TIMES = {
    "upcoming_event_1": "08:00",
    "destination_1": "10:00",
    "upcoming_event_2": "12:00",
    "local_food_1": "17:00",
    "destination_2": "19:00",
}


def gql(q):
    r = requests.post(
        API,
        headers={
            "Authorization": f"Bearer {KEY}",
            "Content-Type": "application/json"
        },
        json={"query": q},
        timeout=45
    )
    r.raise_for_status()
    data = r.json()
    if data.get("errors"):
        raise RuntimeError(data["errors"])
    return data.get("data", {})


def org_id():
    d = gql('query { account { organizations { id } } }')
    return d["account"]["organizations"][0]["id"]


def channel_id(org):
    d = gql(f'''query {{
        channels(input: {{ organizationId: "{org}" }}) {{
            id
            name
            displayName
            service
        }}
    }}''')
    wanted = CHANNEL.lower().lstrip("@")
    for c in d.get("channels", []):
        names = {
            str(c.get("name", "")).lower().lstrip("@"),
            str(c.get("displayName", "")).lower().lstrip("@"),
        }
        if wanted in names:
            return c["id"]
    raise RuntimeError(f"Channel not found: {CHANNEL}")


def build_assets_block(image_urls):
    blocks = []
    for url in image_urls:
        url_json = json.dumps(url, ensure_ascii=False)
        blocks.append(f'{{ image: {{ url: {url_json} }} }}')
    return ", ".join(blocks)


def create_post(cid, text, due, image_urls):
    txt = json.dumps(text, ensure_ascii=False)
    assets_block = build_assets_block(image_urls)
    q = f'''mutation {{
      createPost(input: {{
        text: {txt},
        channelId: "{cid}",
        schedulingType: automatic,
        mode: customScheduled,
        dueAt: "{due}",
        assets: [{assets_block}]
      }}) {{
        ... on PostActionSuccess {{
          post {{ id dueAt }}
        }}
        ... on MutationError {{
          message
        }}
      }}
    }}'''
    out = gql(q).get("createPost", {})
    if out.get("message"):
        raise RuntimeError(out["message"])
    return out.get("post")


def wait_public(url):
    for _ in range(12):
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 200 and r.content:
                return
        except Exception:
            pass
        time.sleep(5)
    raise RuntimeError(f"Image is not publicly reachable: {url}")


def main():
    payload = json.loads((ROOT / "daily_payload.json").read_text(encoding="utf-8"))
    today = datetime.now(JST).date().isoformat()
    if payload["date"] != today:
        raise RuntimeError("Payload date mismatch")

    cid = channel_id(org_id())
    now = datetime.now(JST)

    for item in payload["items"]:
        hhmm = TIMES[item["slot"]]
        h, m = map(int, hhmm.split(":"))
        due_local = datetime(now.year, now.month, now.day, h, m, tzinfo=JST)

        if due_local <= now:
            print("SKIP", item["slot"], hhmm)
            continue

        due = due_local.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

        image_paths = item.get("image_paths") or [item["image_path"]]
        image_urls = [
            f"https://raw.githubusercontent.com/{REPO}/{SHA}/{path}"
            for path in image_paths
        ]

        for image_url in image_urls:
            wait_public(image_url)

        text = item["post_text"].strip() + "\n\n※画像はAI生成イメージ"
        post = create_post(cid, text, due, image_urls)
        print("CREATED", item["slot"], hhmm, post)


if __name__ == "__main__":
    main()
