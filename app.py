import json
import os
from datetime import date
from pathlib import Path

from flask import Flask, jsonify

app = Flask(__name__)
DATA_DIR = Path(__file__).parent / "data"

NOTICE_BOARD_URL = (
    "https://www.bist.ac.kr/univ/board/list.php"
    "?menu=220&board_id=haksaNotice"
)
SCHOLARSHIP_BOARD_URL = (
    "https://www.bist.ac.kr/univ/board/list.php"
    "?menu=234&board_id=scholrshipNotice"
)
FAQ_BOARD_URL = (
    "https://www.bist.ac.kr/univ/board/list.php"
    "?menu=279&board_id=haksahangjung"
)
LIST_CARD_MAX_ITEMS = 5  # 카카오 listCard 한 카드당 최대 5개


def load_json(filename: str) -> dict:
    with (DATA_DIR / filename).open("r", encoding="utf-8") as f:
        return json.load(f)


def kakao_response(outputs, quick_replies=None) -> dict:
    template = {"outputs": outputs}
    if quick_replies:
        template["quickReplies"] = quick_replies
    return {"version": "2.0", "template": template}


def simple_text(text: str) -> dict:
    return {"simpleText": {"text": text}}


def list_card(header_title: str, items: list, buttons=None) -> dict:
    card = {"header": {"title": header_title}, "items": items}
    if buttons:
        card["buttons"] = buttons
    return {"listCard": card}


def web_link_button(label: str, url: str) -> dict:
    return {"label": label, "action": "webLink", "webLinkUrl": url}


def latest_board_items(items: list[dict], top_n: int = LIST_CARD_MAX_ITEMS) -> list[dict]:
    """게시판 항목을 날짜 내림차순으로 정렬해 상위 N개 반환 (오래된 핀고정 공지 제외)."""
    return sorted(items, key=lambda x: x["date"], reverse=True)[:top_n]


def menu_quick_replies():
    labels = ["학사일정", "공지사항", "학식메뉴", "장학금", "학사시설", "FAQ"]
    return [{"label": l, "action": "message", "messageText": l} for l in labels]


def menu_list_items():
    # 카카오 listCard는 최대 5개 항목만 지원 → FAQ는 quickReplies 버튼으로만 노출
    return [
        {"title": "학사일정", "description": "수업·시험 등 주요 일정"},
        {"title": "공지사항", "description": "학교 최신 공지"},
        {"title": "학식메뉴", "description": "오늘의 학식"},
        {"title": "장학금", "description": "최신 장학금 공지"},
        {"title": "학사시설", "description": "도서관 등 시설 안내"},
    ]


@app.route("/")
def index():
    return "BIST Chatbot 'Bis' is running."


@app.route("/skill/hello", methods=["POST"])
def hello():
    return jsonify(kakao_response(
        outputs=[
            simple_text("안녕하세요! 부산과학기술대학교 안내봇 비스예요 :)"),
            list_card("비스가 도와드릴 수 있어요", menu_list_items()),
        ],
        quick_replies=menu_quick_replies(),
    ))


@app.route("/skill/menu", methods=["POST"])
def menu():
    return jsonify(kakao_response(
        outputs=[list_card("비스가 도와드릴 수 있어요", menu_list_items())],
        quick_replies=menu_quick_replies(),
    ))


@app.route("/skill/schedule", methods=["POST"])
def schedule():
    data = load_json("schedule.json")
    today = date.today().isoformat()
    upcoming = [
        item for item in data["items"]
        if (item.get("end_date") or item["date"]) >= today
    ]
    upcoming.sort(key=lambda x: x["date"])
    items = [
        {"title": item["label"], "description": item["event"]}
        for item in upcoming[:5]
    ]
    if not items:
        items = [{"title": "예정된 일정 없음", "description": "다음 학기 일정을 준비 중입니다."}]
    return jsonify(kakao_response(
        outputs=[list_card("다가오는 학사일정", items)],
        quick_replies=menu_quick_replies(),
    ))


@app.route("/skill/notice", methods=["POST"])
def notice():
    data = load_json("notices.json")
    items = []
    for item in latest_board_items(data["items"]):
        list_item = {"title": item["title"], "description": item["date"]}
        if item.get("url"):
            list_item["link"] = {"web": item["url"]}
        items.append(list_item)
    return jsonify(kakao_response(
        outputs=[list_card(
            "최신 공지사항", items,
            buttons=[web_link_button("공지사항 전체보기", NOTICE_BOARD_URL)],
        )],
        quick_replies=menu_quick_replies(),
    ))


@app.route("/skill/meal", methods=["POST"])
def meal():
    data = load_json("meals.json")
    today = data["today"]
    items = [
        {"title": "중식", "description": today["lunch"]},
        {"title": "석식", "description": today["dinner"]},
    ]
    return jsonify(kakao_response(
        outputs=[list_card("오늘의 학식", items)],
        quick_replies=menu_quick_replies(),
    ))


@app.route("/skill/scholarship", methods=["POST"])
def scholarship():
    data = load_json("scholarships.json")
    items = []
    for sch in latest_board_items(data["items"]):
        item = {"title": sch["title"], "description": sch["date"]}
        if sch.get("url"):
            item["link"] = {"web": sch["url"]}
        items.append(item)
    return jsonify(kakao_response(
        outputs=[list_card(
            "최근 장학금 공지", items,
            buttons=[web_link_button("장학금 공지 전체보기", SCHOLARSHIP_BOARD_URL)],
        )],
        quick_replies=menu_quick_replies(),
    ))


@app.route("/skill/facility", methods=["POST"])
def facility():
    lib = load_json("library.json")
    hours = lib["hours"]
    items = [
        {
            "title": "도서관 운영시간",
            "description": f"{hours['weekday_thu']}\n{hours['friday']}\n{hours['weekend']}",
        },
    ]
    for loc in lib["locations"]:
        items.append({"title": loc["name"], "description": loc["place"]})
    return jsonify(kakao_response(
        outputs=[list_card(
            "학사시설 안내", items,
            buttons=[web_link_button("도서관 홈페이지", lib["homepage"])],
        )],
        quick_replies=menu_quick_replies(),
    ))


@app.route("/skill/fallback", methods=["POST"])
def fallback():
    return jsonify(kakao_response(
        outputs=[
            simple_text(
                "죄송해요, 비스가 아직 모르는 질문이에요.\n"
                "아래 메뉴 중에서 골라주시면 도와드릴게요!"
            ),
            list_card("비스가 도와드릴 수 있어요", menu_list_items()),
        ],
        quick_replies=menu_quick_replies(),
    ))


@app.route("/skill/faq", methods=["POST"])
def faq():
    data = load_json("faq.json")
    items = [
        {"title": item["q"], "description": item["a"]}
        for item in data["items"][:5]
    ]
    return jsonify(kakao_response(
        outputs=[list_card(
            "자주 묻는 질문", items,
            buttons=[web_link_button("학사문의게시판으로", FAQ_BOARD_URL)],
        )],
        quick_replies=menu_quick_replies(),
    ))


if __name__ == "__main__":
    # 로컬 개발용 실행. Render에서는 gunicorn이 app 객체를 직접 띄우므로
    # 이 블록은 실행되지 않는다(아래는 `python app.py` 로컬 실행 전용).
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
