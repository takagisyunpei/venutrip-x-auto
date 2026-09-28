import base64, json, os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from openai import OpenAI

JST = ZoneInfo("Asia/Tokyo")
ROOT = Path(__file__).resolve().parent
HISTORY_PATH = ROOT / "history.json"
PAYLOAD_PATH = ROOT / "daily_payload.json"
MEDIA_ROOT = ROOT / "generated_media"

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
TEXT_MODEL = os.getenv("OPENAI_TEXT_MODEL", "gpt-5.6-luna")
IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2.5-flare")

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
    return json.loads(text[start:end+1])

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
- image_promptは現地写真の偽装ではなく、上品な旅行雑誌風イラスト用。文字・ロゴなし。

直近主題:
{json.dumps(recent[-60:], ensure_ascii=False)}

説明なしでJSONだけ返す:
{{
 "items":[
  {{"slot":"upcoming_event_1","category":"event","title":"","area":"","date_info":"","post_text":"","source_url":"","source_title":"","image_prompt":""}},
  {{"slot":"destination_1","category":"destination","title":"","area":"","date_info":"","post_text":"","source_url":"","source_title":"","image_prompt":""}},
  {{"slot":"upcoming_event_2","category":"event","title":"","area":"","date_info":"","post_text":"","source_url":"","source_title":"","image_prompt":""}},
  {{"slot":"local_food_1","category":"food","title":"","area":"","date_info":"","post_text":"","source_url":"","source_title":"","image_prompt":""}},
  {{"slot":"destination_2","category":"destination","title":"","area":"","date_info":"","post_text":"","source_url":"","source_title":"","image_prompt":""}}
 ]
}}
'''
    r = client.responses.create(
        model=TEXT_MODEL,
        reasoning={"effort":"low"},
        tools=[{"type":"web_search"}],
        tool_choice="required",
        input=prompt,
    )
    return extract_json(r.output_text)

def generate_image(item, outpath):
    prompt = f'''
Create a polished Japanese travel-magazine editorial illustration inspired by
{item["title"]} in {item["area"]}.
Creative direction: {item["image_prompt"]}
Landscape composition for X. Premium travel editorial aesthetic.
No text, no letters, no logos, no watermark, no readable signage.
Atmospheric illustration, not documentary proof.
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

def main():
    today = datetime.now(JST).date().isoformat()
    history = load_history()
    recent = [f'{x.get("category")} | {x.get("title")} | {x.get("area")}' for x in history.get("items", [])]
    data = research(today, recent)
    expected = ["upcoming_event_1","destination_1","upcoming_event_2","local_food_1","destination_2"]
    items = data.get("items", [])
    if [x.get("slot") for x in items] != expected:
        raise ValueError("Unexpected slots")

    result_items = []
    for item in items:
        if not str(item.get("source_url","")).startswith("http"):
            raise ValueError(f'Missing source URL: {item.get("title")}')
        outpath = MEDIA_ROOT / today / f'{item["slot"]}.png'
        generate_image(item, outpath)
        item = dict(item)
        item["image_path"] = str(outpath.relative_to(ROOT)).replace("\\","/")
        item["generated_date"] = today
        result_items.append(item)

    PAYLOAD_PATH.write_text(json.dumps({"date":today,"items":result_items}, ensure_ascii=False, indent=2), encoding="utf-8")

    hist = history.get("items", [])
    for item in result_items:
        hist.append({"date":today,"category":item["category"],"title":item["title"],"area":item["area"],"source_url":item["source_url"]})
    history["items"] = hist[-180:]
    HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"date":today,"items":result_items}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
