import base64, json, os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from openai import OpenAI
import requests

JST = ZoneInfo("Asia/Tokyo")
ROOT = Path(__file__).resolve().parent
HISTORY_PATH = ROOT / "history.json"
PAYLOAD_PATH = ROOT / "daily_payload.json"
MEDIA_ROOT = ROOT / "generated_media"

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
TEXT_MODEL = os.getenv("OPENAI_TEXT_MODEL", "gpt-5.6-luna")
IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2.5-flare")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "").strip()


def load_history():
    if not HISTORY_PATH.exists():
        return {"items": []}
    return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))


def extract_json(text):
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("No JSON found")
    return json.loads(text[start:end + 1])


def research(today, recent):
    prompt = f'''
あなたは日本国内旅行メディアVENUTRIPの編集者です。
今日の日付は {today}（日本時間）。

公開Webを必ず検索し、全国から今日投稿する5件を選んでください。
内訳:
1 upcoming_event_1: イベント
2 destination_1: 旅行先
3 upcoming_event_2: イベント
4 local_food_1: 地域で食べたいもの
5 destination_2: 旅行先

ルール:
- 全国どこでも可。地域は偏らせない。
- イベントは今日以降60日以内を原則とし、開催日・会場・公式URLを一次情報で確認。
- 旅行先は今の季節に行く理由がある場所を優先。
- 食べ物は地域性のある具体的な名物。
- 直近投稿と重複しない。
- X本文は自然な日本語、200文字以内、ハッシュタグ最大2個。
- イベント本文には開催日/期間を入れる。
- pexels_queriesはPexelsで実写を探すための英語検索語を1件にする。固有名詞、都道府県・市区町村、Japanを含め、主題を具体化する。
- image_promptはPexelsで適切な実写が見つからない場合だけ使うAI画像指示にする。
- 画像は1投稿につき1枚。投稿内容がひと目で伝わる代表的な全景・料理・名所を選ぶこと。
- 文字・ロゴなし。

直近主題:
{json.dumps(recent[-60:], ensure_ascii=False)}

説明なしでJSONだけ返す:
{{
 "items":[
  {{"slot":"upcoming_event_1","category":"event","title":"","area":"","date_info":"","post_text":"","source_url":"","source_title":"","pexels_queries":["","",""],"image_prompt":""}},
  {{"slot":"destination_1","category":"destination","title":"","area":"","date_info":"","post_text":"","source_url":"","source_title":"","pexels_queries":["","",""],"image_prompt":""}},
  {{"slot":"upcoming_event_2","category":"event","title":"","area":"","date_info":"","post_text":"","source_url":"","source_title":"","pexels_queries":["","",""],"image_prompt":""}},
  {{"slot":"local_food_1","category":"food","title":"","area":"","date_info":"","post_text":"","source_url":"","source_title":"","pexels_queries":["","",""],"image_prompt":""}},
  {{"slot":"destination_2","category":"destination","title":"","area":"","date_info":"","post_text":"","source_url":"","source_title":"","pexels_queries":["","",""],"image_prompt":""}}
 ]
}}
'''
    r = client.responses.create(
        model=TEXT_MODEL,
        reasoning={"effort": "low"},
        tools=[{"type": "web_search"}],
        tool_choice="required",
        input=prompt,
    )
    return extract_json(r.output_text)


def shot_instruction(category, shot_no):
    if category == "food":
        shots = {
            1: "The main dish beautifully presented on a table, realistic food photography.",
            2: "A local dining atmosphere or restaurant scene connected to the food.",
            3: "A close-up detail shot showing texture, ingredients, or serving style."
        }
    elif category == "event":
        shots = {
            1: "A wide establishing shot showing the venue or townscape and overall event atmosphere.",
            2: "A mid-range shot showing visitors, festival mood, or event activity.",
            3: "A detail shot of decorations, stalls, crafts, food, or symbolic local elements."
        }
    else:
        shots = {
            1: "A wide scenic travel shot that clearly shows the destination.",
            2: "A lifestyle-style travel shot capturing the local atmosphere and charm.",
            3: "A detail shot of streets, food, architecture, nature, or a signature local feature."
        }
    return shots[shot_no]


def generate_image(item, outpath, shot_no):
    prompt = f'''
Create a photorealistic Japanese travel photo style image.

Subject:
- Title: {item["title"]}
- Area: {item["area"]}
- Category: {item["category"]}

Creative direction:
{item["image_prompt"]}

Required shot:
{shot_instruction(item["category"], shot_no)}

Visual style:
- realistic travel photography
- natural lighting
- premium tourism editorial look
- beautiful but believable
- no text
- no watermark
- no logo
- no readable signage
- landscape composition suitable for X post attachment

This should feel like a normal high-quality travel photo, not an illustration.
'''
    r = client.images.generate(
        model=IMAGE_MODEL,
        prompt=prompt,
        size="1536x1024",
        quality="low",
        output_format="png",
    )
    outpath.parent.mkdir(parents=True, exist_ok=True)
    outpath.write_bytes(base64.b64decode(r.data[0].b64_json))


def download_pexels_image(item, outpath, shot_no, used_photo_ids):
    if not PEXELS_API_KEY:
        return None

    queries = item.get("pexels_queries") or []
    if len(queries) < 3 or not str(queries[shot_no - 1]).strip():
        return None

    response = requests.get(
        "https://api.pexels.com/v1/search",
        headers={"Authorization": PEXELS_API_KEY},
        params={
            "query": str(queries[shot_no - 1]).strip(),
            "orientation": "landscape",
            "size": "large",
            "per_page": 10,
        },
        timeout=45,
    )
    response.raise_for_status()

    for photo in response.json().get("photos", []):
        photo_id = str(photo.get("id", ""))
        if not photo_id or photo_id in used_photo_ids:
            continue
        src = photo.get("src") or {}
        image_url = src.get("large2x") or src.get("large") or src.get("landscape")
        if not image_url:
            continue
        image_response = requests.get(image_url, timeout=60)
        image_response.raise_for_status()
        outpath.parent.mkdir(parents=True, exist_ok=True)
        outpath.write_bytes(image_response.content)
        used_photo_ids.add(photo_id)
        return {
            "type": "pexels",
            "path": str(outpath.relative_to(ROOT)).replace("\\", "/"),
            "photo_id": photo_id,
            "source_url": photo.get("url", ""),
            "photographer": photo.get("photographer", ""),
        }
    return None


def main():
    today = datetime.now(JST).date().isoformat()
    history = load_history()
    recent = [
        f'{x.get("category")} | {x.get("title")} | {x.get("area")}'
        for x in history.get("items", [])
    ]

    data = research(today, recent)
    expected = [
        "upcoming_event_1",
        "destination_1",
        "upcoming_event_2",
        "local_food_1",
        "destination_2",
    ]
    items = data.get("items", [])
    if [x.get("slot") for x in items] != expected:
        raise ValueError("Unexpected slots")

    result_items = []
    for item in items:
        if not str(item.get("source_url", "")).startswith("http"):
            raise ValueError(f'Missing source URL: {item.get("title")}')

        image_paths = []
        image_sources = []
        used_photo_ids = set()
        for shot_no in range(1, 2):
            pexels_path = MEDIA_ROOT / today / f'{item["slot"]}_{shot_no}.jpg'
            source = None
            try:
                source = download_pexels_image(item, pexels_path, shot_no, used_photo_ids)
            except requests.RequestException as exc:
                print(f'PEXELS FALLBACK {item["slot"]} shot={shot_no}: {exc}')

            if source is None:
                ai_path = MEDIA_ROOT / today / f'{item["slot"]}_{shot_no}.png'
                generate_image(item, ai_path, shot_no)
                source = {
                    "type": "ai",
                    "path": str(ai_path.relative_to(ROOT)).replace("\\", "/"),
                }

            image_paths.append(source["path"])
            image_sources.append(source)

        item = dict(item)
        item["image_paths"] = image_paths
        item["image_sources"] = image_sources
        item["image_path"] = image_paths[0]  # 互換用
        item["generated_date"] = today
        result_items.append(item)

    PAYLOAD_PATH.write_text(
        json.dumps({"date": today, "items": result_items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    hist = history.get("items", [])
    for item in result_items:
        hist.append(
            {
                "date": today,
                "category": item["category"],
                "title": item["title"],
                "area": item["area"],
                "source_url": item["source_url"],
            }
        )
    history["items"] = hist[-180:]
    HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"date": today, "items": result_items}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
