"""
부산과학기술대학교 게시판 크롤러 (학사공지·장학금 등 동일 구조 게시판).

학교 robots.txt(`Disallow: /`)를 존중하기 위해:
- 자동 스케줄 실행은 하지 않는다 (사용자가 수동으로 실행).
- User-Agent를 명시한다.
- 호출 사이에 대기 시간을 둔다.
- 챗봇 런타임은 학교 서버를 호출하지 않고 JSON만 읽는다.

사용법:
    python crawler/board_crawler.py            # BOARDS의 모든 게시판 갱신
    python crawler/board_crawler.py haksaNotice  # 특정 board_id만 갱신
"""

import io
import json
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# Windows cp949 콘솔에서도 한글이 깨지지 않게 stdout을 UTF-8로 강제
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE_URL = "https://www.bist.ac.kr/univ/board/"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
USER_AGENT = (
    "BIST-Chatbot-Project/1.0 "
    "(Student class project for BIST university; "
    "contact: contact@example.com)"
)
MAX_ITEMS = 15  # 핀고정 공지가 위에 섞이므로 넉넉히 가져와서 app.py에서 날짜순 정렬
REQUEST_DELAY_SEC = 2

BOARDS = [
    {
        "id": "haksaNotice",
        "menu": 220,
        "output": "notices.json",
        "label": "학사공지",
    },
    {
        "id": "scholrshipNotice",
        "menu": 234,
        "output": "scholarships.json",
        "label": "장학금공지",
    },
]


def fetch_html(url: str) -> str:
    time.sleep(REQUEST_DELAY_SEC)
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=10)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


def parse_board(html: str, max_items: int = MAX_ITEMS) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("tbody tr")
    items: list[dict] = []
    for row in rows:
        title_a = row.select_one("td.title a")
        date_td = row.select_one("td.date")
        if not title_a or not date_td:
            continue
        title = title_a.get_text(strip=True)
        href = title_a.get("href", "")
        if href.startswith("./"):
            url = BASE_URL + href[2:]
        elif href.startswith("/"):
            url = "https://www.bist.ac.kr" + href
        else:
            url = BASE_URL + href
        date_str = date_td.get_text(strip=True).replace(".", "-")
        items.append({"title": title, "date": date_str, "url": url})
        if len(items) >= max_items:
            break
    return items


def save_items(items: list[dict], filename: str) -> Path:
    path = DATA_DIR / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump({"items": items}, f, ensure_ascii=False, indent=2)
    return path


def crawl_board(board: dict) -> None:
    url = f"{BASE_URL}list.php?menu={board['menu']}&board_id={board['id']}"
    print(f"[크롤러] {board['label']} 가져오는 중: {url}")
    html = fetch_html(url)
    items = parse_board(html)
    if not items:
        print(f"[경고] {board['label']}: 0건 (HTML 구조 변경 가능성)")
        return
    out_path = save_items(items, board["output"])
    print(f"[완료] {board['label']} {len(items)}건 → {out_path}")
    for i, it in enumerate(items, 1):
        print(f"  {i}. ({it['date']}) {it['title']}")


def main() -> None:
    target_id = sys.argv[1] if len(sys.argv) > 1 else None
    targets = [b for b in BOARDS if not target_id or b["id"] == target_id]
    if not targets:
        print(f"[에러] '{target_id}' 게시판을 찾을 수 없습니다.")
        print("등록된 board_id:", [b["id"] for b in BOARDS])
        sys.exit(1)
    for board in targets:
        crawl_board(board)
        print()


if __name__ == "__main__":
    main()
