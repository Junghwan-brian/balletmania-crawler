#!/usr/bin/env python3
"""발레매니아 '대타 구인' 게시판 크롤러 (GitHub Actions 용).

- 게시판 첫 페이지(최신 목록)를 크롤링한다.
- 게시글의 번호/제목/작성자/추천/조회/등록일을 state.json 에 저장한다(최대 50개).
- '번호'를 기준으로 새 글을 판단해, 새 글의 제목을 텔레그램 봇으로 보낸다.
- 첫 실행(state.json 없음)에는 기존 글을 알림 없이 기준값으로만 저장한다.

상태 저장 전략 (GitHub Actions):
- 새 글이 있을 때(또는 첫 실행 시)에만 state.json 을 갱신/기록한다.
- 새 글이 없으면 state.json 을 건드리지 않으므로 git diff 가 없고 커밋도 생기지 않는다.
  => 워크플로는 "state.json 이 변경됐을 때만" 커밋/푸시한다.

사용법:
    python crawler.py            # 한 번만 크롤링 (GitHub Actions 기본)
    python crawler.py --loop     # 5분마다 반복 (로컬 테스트용)
"""

import os
import re
import sys
import json
import time
import logging
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("balletmania")


# ---------------------------------------------------------------------------
# 상태 파일 (JSON)
# ---------------------------------------------------------------------------
def load_state():
    """state.json 을 읽어 {'last_max': int|None, 'recent': [post,...]} 반환."""
    if not os.path.exists(config.STATE_PATH):
        return {"last_max": None, "recent": []}
    with open(config.STATE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("last_max", None)
    data.setdefault("recent", [])
    return data


def save_state(posts):
    """번호 내림차순 최신 MAX_ROWS 개만 state.json 에 기록."""
    recent = sorted(posts, key=lambda p: p["num"], reverse=True)[: config.MAX_ROWS]
    state = {
        "last_max": max(p["num"] for p in recent),
        "recent": recent,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(config.STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def merge_recent(old_recent, posts):
    """기존 recent 와 새로 크롤링한 posts 를 번호 기준으로 병합(최신값 우선)."""
    by_num = {p["num"]: p for p in old_recent}
    for p in posts:
        by_num[p["num"]] = p  # 새 크롤링 값으로 덮어씀
    return list(by_num.values())


# ---------------------------------------------------------------------------
# 크롤링 / 파싱
# ---------------------------------------------------------------------------
def fetch_html():
    resp = requests.get(
        config.BOARD_URL,
        headers={"User-Agent": config.USER_AGENT},
        timeout=20,
    )
    resp.raise_for_status()
    resp.encoding = "euc-kr"  # 사이트 인코딩
    return resp.text


def _to_int(text, default=0):
    m = re.search(r"-?\d+", text or "")
    return int(m.group()) if m else default


def parse_posts(html):
    """게시글 목록을 파싱해 dict 리스트로 반환.

    제목 링크 href 에 'id=working&no=숫자' 패턴이 있고, 그 링크가 든 <tr> 셀 구조는
        ['', 번호, 제목, 작성자, 추천, 조회, 등록일, '']
    이다. 공지글은 번호가 '공지'(숫자 아님)라 자동으로 걸러진다.
    """
    soup = BeautifulSoup(html, "lxml")
    posts = []
    seen_nums = set()

    for a in soup.find_all("a", href=True):
        if not re.search(r"id=working&no=\d+", a["href"]):
            continue
        tr = a.find_parent("tr")
        if tr is None:
            continue

        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(cells) < 7:
            continue

        num_text = cells[1]
        if not num_text.isdigit():  # 공지글 등 번호 없는 행 스킵
            continue
        num = int(num_text)
        if num in seen_nums:
            continue
        seen_nums.add(num)

        post_no = re.search(r"no=(\d+)", a["href"]).group(1)
        posts.append(
            {
                "num": num,
                "title": cells[2],
                "author": cells[3],
                "recommend": _to_int(cells[4]),
                "views": _to_int(cells[5]),
                "reg_date": cells[6],
                "post_no": post_no,
                "url": urljoin(config.BASE_URL, a["href"]),
            }
        )

    return posts


# ---------------------------------------------------------------------------
# 텔레그램
# ---------------------------------------------------------------------------
def send_telegram(text):
    """설정된 모든 chat_id 에게 전송. 하나라도 성공하면 True."""
    if not config.TELEGRAM_ACCESS_TOKEN:
        log.error("TELEGRAM_ACCESS_TOKEN 이 비어 있습니다. 환경변수/Secret 설정을 확인하세요.")
        return False
    if not config.TELEGRAM_CHAT_IDS:
        log.error("TELEGRAM_CHAT_IDS 가 비어 있습니다. 환경변수/Secret 설정을 확인하세요.")
        return False
    url = f"https://api.telegram.org/bot{config.TELEGRAM_ACCESS_TOKEN}/sendMessage"
    any_ok = False
    for chat_id in config.TELEGRAM_CHAT_IDS:
        resp = requests.post(
            url,
            data={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": "false",
            },
            timeout=20,
        )
        if resp.ok:
            any_ok = True
        else:
            log.error("텔레그램 전송 실패 chat_id=%s (%s): %s",
                      chat_id, resp.status_code, resp.text)
    return any_ok


def notify_new_post(post):
    text = (
        "🩰 <b>발레매니아 대타 구인 새 글</b>\n\n"
        f"<b>{post['title']}</b>\n"
        f"작성자: {post['author']}\n"
        f"등록일: {post['reg_date']} | 조회 {post['views']} | 추천 {post['recommend']}\n"
        f"번호: {post['num']}\n"
        f'\n<a href="{post["url"]}">글 보러가기</a>'
    )
    return send_telegram(text)


# ---------------------------------------------------------------------------
# 한 사이클
# ---------------------------------------------------------------------------
def crawl_once():
    html = fetch_html()
    posts = parse_posts(html)
    if not posts:
        log.warning("게시글을 하나도 파싱하지 못했습니다. (사이트 구조 변경 가능성)")
        return

    state = load_state()
    max_known = state["last_max"]

    if max_known is None:
        # 첫 실행: 기존 글을 알림 없이 기준값으로만 저장
        save_state(posts)
        log.info("첫 실행 - 기존 글 %d개를 알림 없이 저장했습니다. (기준 번호=%d)",
                 len(posts), max(p["num"] for p in posts))
        return

    # 번호가 기존 최대값보다 큰 글 = 새 글
    new_posts = sorted((p for p in posts if p["num"] > max_known), key=lambda p: p["num"])

    if not new_posts:
        # 새 글 없음 -> state.json 을 건드리지 않음 (커밋 발생 안 함)
        log.info("새 글 없음 (최신 번호=%s, 목록 %d건)", max_known, len(posts))
        return

    log.info("새 글 %d개 발견 -> 텔레그램 전송", len(new_posts))
    for p in new_posts:
        ok = notify_new_post(p)
        log.info("  [%s] %s (전송 %s)", p["num"], p["title"], "성공" if ok else "실패")

    # 새 글이 있을 때만 상태 갱신 (기존 recent 와 병합 후 최신 50개 유지)
    merged = merge_recent(state["recent"], posts)
    save_state(merged)


# ---------------------------------------------------------------------------
# 엔트리포인트
# ---------------------------------------------------------------------------
def main():
    loop = "--loop" in sys.argv
    if loop:
        log.info("루프 모드 시작 - %d초마다 크롤링합니다.", config.INTERVAL_SECONDS)
        while True:
            try:
                crawl_once()
            except Exception as e:
                log.exception("크롤링 중 오류: %s", e)
            time.sleep(config.INTERVAL_SECONDS)
    else:
        crawl_once()


if __name__ == "__main__":
    main()
