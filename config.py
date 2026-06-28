"""발레매니아 대타구하기 크롤러 설정.

GitHub Actions 환경에서는 텔레그램 토큰/chat_id 를 GitHub Secrets(환경변수)로
주입받는다. 로컬 실행 시에도 동일한 환경변수를 export 해서 쓰면 된다.

  export TELEGRAM_ACCESS_TOKEN="..."
  export TELEGRAM_CHAT_IDS="7315682787,8809086944"
"""

import os

# 텔레그램 봇 정보 (Secrets/환경변수에서 읽음)
# 토큰은 민감정보라 코드에 박지 않는다. 반드시 환경변수로 주입.
TELEGRAM_ACCESS_TOKEN = os.environ.get("TELEGRAM_ACCESS_TOKEN", "")

# 알림 받을 chat_id 목록 (쉼표구분). Secrets/환경변수로 주입.
TELEGRAM_CHAT_IDS = [
    c.strip()
    for c in os.environ.get("TELEGRAM_CHAT_IDS", "").split(",")
    if c.strip()
]

# 크롤링 대상
BOARD_URL = "https://www.balletmania.com/board/index.html?id=working"
BASE_URL = "https://www.balletmania.com/board/"  # 상세글 링크 조합용

# 상태 저장 파일 (GitHub Actions 에서 레포에 커밋되어 다음 실행으로 이어짐)
STATE_PATH = "state.json"
MAX_ROWS = 50  # state.json 에 보관할 최대 글 개수

# 크롤링 주기 (로컬 --loop 모드에서만 사용). GitHub Actions 는 워크플로 cron 으로 제어.
INTERVAL_SECONDS = 300

# 요청 헤더 (간단한 브라우저 위장)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
