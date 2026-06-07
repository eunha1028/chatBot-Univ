import json
import os
from datetime import date, datetime, timedelta, timezone
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
KST = timezone(timedelta(hours=9))  # 한국 표준시 (Render 서버는 UTC라 명시 필요)
NEW_BADGE_DAYS = 7  # 공지 'NEW' 표시 기준 (최근 N일)
SCHOOL_PHONE = "051-334-6666"  # 학교 대표전화
SCHOOL_MAP_URL = "https://map.kakao.com/?q=부산과학기술대학교"  # 오시는길(카카오맵 검색)


def load_json(filename: str) -> dict:
    with (DATA_DIR / filename).open("r", encoding="utf-8") as f:
        return json.load(f)


def today_kst() -> date:
    """한국 시간(KST) 기준 오늘 날짜. Render 서버가 UTC여도 일관되게 동작."""
    return datetime.now(KST).date()


def fresh_label(updated) -> str:
    """수집일을 헤더용 ' (M.D. 기준)' 문구로. 값이 없거나 형식이 어긋나면 빈 문자열."""
    try:
        d = date.fromisoformat(updated)
        return f" ({d.month}.{d.day}. 기준)"
    except (ValueError, TypeError):
        return ""


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


def phone_button(label: str, number: str) -> dict:
    return {"label": label, "action": "phone", "phoneNumber": number}


def latest_board_items(items: list[dict], top_n: int = LIST_CARD_MAX_ITEMS) -> list[dict]:
    """게시판 항목을 날짜 내림차순으로 정렬해 상위 N개 반환 (오래된 핀고정 공지 제외)."""
    return sorted(items, key=lambda x: x["date"], reverse=True)[:top_n]


def menu_quick_replies():
    labels = ["학사일정", "공지사항", "장학금", "학사시설", "FAQ"]
    return [{"label": l, "action": "message", "messageText": l} for l in labels]


def menu_list_items():
    # 메뉴 5개를 카카오 listCard 최대 항목 수(5개)에 맞춰 모두 노출
    return [
        {"title": "학사일정", "description": "수업·시험 등 주요 일정"},
        {"title": "공지사항", "description": "학교 최신 공지"},
        {"title": "장학금", "description": "최신 장학금 공지"},
        {"title": "학사시설", "description": "도서관 등 시설 안내"},
        {"title": "FAQ", "description": "자주 묻는 질문"},
    ]


@app.errorhandler(Exception)
def handle_unexpected_error(e):
    # 데이터 파일 누락·손상 등 예기치 못한 오류 시 500 대신 친절한 안내로 폴백
    return jsonify(kakao_response(
        outputs=[simple_text(
            "앗, 비스가 잠시 정보를 불러오지 못했어요 :(\n"
            "잠시 후 다시 시도해 주세요."
        )],
        quick_replies=menu_quick_replies(),
    ))


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
    today = today_kst()
    today_str = today.isoformat()
    upcoming = [
        item for item in data["items"]
        if (item.get("end_date") or item["date"]) >= today_str
    ]
    upcoming.sort(key=lambda x: x["date"])
    items = []
    for item in upcoming[:5]:
        d = (date.fromisoformat(item["date"]) - today).days
        if d > 0:
            badge = f"D-{d}"        # 시작 전
        elif d == 0:
            badge = "D-DAY"         # 오늘 시작
        else:
            badge = "진행중"        # 시작일은 지났지만 기간 내(end_date 기준)
        items.append({
            "title": f"[{badge}] {item['label']}",
            "description": item["event"],
        })
    if not items:
        items = [{"title": "예정된 일정 없음", "description": "다음 학기 일정을 준비 중입니다."}]
    return jsonify(kakao_response(
        outputs=[list_card("다가오는 학사일정", items)],
        quick_replies=menu_quick_replies(),
    ))


@app.route("/skill/notice", methods=["POST"])
def notice():
    data = load_json("notices.json")
    today = today_kst()
    items = []
    for item in latest_board_items(data["items"]):
        title = item["title"]
        try:  # 최근 게시물에 NEW 배지 (날짜 형식이 어긋나면 배지 없이 표시)
            if (today - date.fromisoformat(item["date"])).days <= NEW_BADGE_DAYS:
                title = f"[NEW] {title}"
        except ValueError:
            pass
        list_item = {"title": title, "description": item["date"]}
        if item.get("url"):
            list_item["link"] = {"web": item["url"]}
        items.append(list_item)
    return jsonify(kakao_response(
        outputs=[list_card(
            "최신 공지사항" + fresh_label(data.get("updated")), items,
            buttons=[web_link_button("공지사항 전체보기", NOTICE_BOARD_URL)],
        )],
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
            "최근 장학금 공지" + fresh_label(data.get("updated")), items,
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
            "link": {"web": lib["homepage"]},  # 항목을 누르면 도서관 홈페이지로
        },
    ]
    for loc in lib["locations"]:
        items.append({"title": loc["name"], "description": loc["place"]})
    items.append({"title": "학교 대표전화", "description": SCHOOL_PHONE})
    return jsonify(kakao_response(
        outputs=[list_card(
            "학사시설·오시는길 안내", items,
            buttons=[
                web_link_button("오시는길(지도)", SCHOOL_MAP_URL),
                phone_button("학교 전화 걸기", SCHOOL_PHONE),
            ],
        )],
        quick_replies=menu_quick_replies(),
    ))


@app.route("/skill/fallback", methods=["POST"])
def fallback():
    return jsonify(kakao_response(
        outputs=[
            simple_text(
                "음, 비스가 아직 그 질문은 잘 모르겠어요 :(\n"
                "혹시 아래 중에 궁금한 게 있으실까요? 골라주시면 바로 안내해 드릴게요!"
            ),
            list_card("이런 걸 도와드릴 수 있어요", menu_list_items()),
        ],
        quick_replies=menu_quick_replies(),
    ))


@app.route("/skill/help", methods=["POST"])
def help_skill():
    return jsonify(kakao_response(
        outputs=[
            simple_text(
                "저는 부산과학기술대학교 안내봇 비스예요 :)\n"
                "학사일정·공지사항·장학금·학사시설·FAQ를 안내해 드려요.\n"
                "아래에서 궁금한 걸 골라보세요!"
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
