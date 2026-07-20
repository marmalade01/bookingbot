# -*- coding: utf-8 -*-
"""네이버 예약 빈자리 감시 → 텔레그램 알림.

동작 원리:
    1. daily 쿼리 1번으로 오늘~다음달 말까지 날짜별 집계(재고/예약수)를 가져온다.
    2. 직전 검사와 집계가 달라진 날짜만 hourly 쿼리로 상세 조회한다.
       (취소표든 월 오픈이든 unitBookingCount 변화로 잡힌다)
    3. 실제 진료 슬롯(isUnitBusinessDay) 중 자리가 생긴 슬롯만 텔레그램 발송.

사용법:
    python watch.py          # 무한 루프 (interval_seconds 간격으로 반복)
    python watch.py --once   # 1회만 검사 (작업 스케줄러 등록용)
"""
import calendar
import json
import sys
import time
import urllib.request
from datetime import date as date_cls
from datetime import datetime, timedelta
from pathlib import Path

# Windows 콘솔(cp1252 등)에서도 한글 로그가 깨지지 않도록 UTF-8 강제
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"
STATE_FILE = BASE_DIR / "state.json"
LOG_FILE = BASE_DIR / "watch.log"

GRAPHQL_URL = "https://m.booking.naver.com/graphql"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    " (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

DAILY_QUERY = (
    "query schedule($scheduleParams: ScheduleParams) {"
    " schedule(input: $scheduleParams) { bizItemSchedule { daily { date } } } }"
)
HOURLY_QUERY = (
    "query hourlySchedule($scheduleParams: ScheduleParams) {"
    " schedule(input: $scheduleParams) { bizItemSchedule { hourly {"
    " unitStartTime unitStock unitBookingCount occupiedBookingCount"
    " isUnitBusinessDay isUnitSaleDay"
    " } } } }"
)

WEEKDAY_KO = "월화수목금토일"

# 조회 연속 실패가 이 횟수에 도달하면 에러 알림 1회 발송
ERROR_NOTIFY_THRESHOLD = 5


def prevent_system_sleep():
    """감시가 도는 동안 Windows 자동 절전을 막는다 (모니터는 평소처럼 꺼짐).

    프로세스가 종료되면 자동으로 해제된다. 사용자가 직접 절전을 누르면 그대로 잔다.
    """
    if sys.platform != "win32":
        return
    import ctypes

    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001
    result = ctypes.windll.kernel32.SetThreadExecutionState(
        ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    )
    if result == 0:
        log("경고: 절전 방지 설정 실패 — 절전 모드에 들어가면 감시가 멈춥니다")


def log(message):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def post_json(url, payload, headers):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as res:
        return json.loads(res.read().decode("utf-8"))


def graphql(config, operation_name, query, start, end):
    payload = {
        "operationName": operation_name,
        "query": query,
        "variables": {
            "scheduleParams": {
                "businessTypeId": config["business_type_id"],
                "businessId": config["business_id"],
                "bizItemId": config["biz_item_id"],
                "startDateTime": start,
                "endDateTime": end,
            }
        },
    }
    headers = {"User-Agent": USER_AGENT, "Referer": booking_url(config)}
    data = post_json(f"{GRAPHQL_URL}?opName={operation_name}", payload, headers)
    if "errors" in data:
        raise RuntimeError(f"GraphQL error: {data['errors']}")
    return data["data"]["schedule"]["bizItemSchedule"]


def booking_url(config):
    """GraphQL 요청의 Referer 용 URL (앱이 보내는 형태)."""
    return (
        f"https://m.booking.naver.com/booking/{config['business_type_id']}"
        f"/bizes/{config['business_id']}/items/{config['biz_item_id']}"
    )


def place_link(config):
    """사용자에게 보낼 예약 링크.

    m.booking 딥링크는 플레이스를 거치지 않고 직접 열면 "운영하지 않는 예약
    페이지"가 뜰 때가 많다. 사용자가 실제로 예약할 때 쓰는 플레이스 홈(예약 버튼이
    노출되는 화면)으로 보낸다.
    """
    return f"https://m.place.naver.com/hospital/{config['place_id']}/home?entry=pll"


def end_of_next_month(today):
    year, month = today.year, today.month + 1
    if month > 12:
        year, month = year + 1, 1
    return date_cls(year, month, calendar.monthrange(year, month)[1])


def is_watched_date(config, day):
    weekday_ko = WEEKDAY_KO[day.weekday()]
    return weekday_ko not in config.get("exclude_weekdays", [])


def fetch_day_summaries(config):
    """오늘~다음달 말까지 날짜별 집계를 요청 1번으로 가져온다.

    반환: {"YYYY-MM-DD": "stock/booked/occupied" 시그니처}
    """
    today = datetime.now().date()
    until = end_of_next_month(today)
    daily = fetch_daily_range(config, today, until)
    summaries = {}
    for key, day in daily.items():
        summaries[key] = (
            f"{day['stock']}/{day['bookingCount']}/{day['occupiedBookingCount']}"
        )
    return summaries


def fetch_daily_range(config, start_date, end_date):
    result = graphql(
        config,
        "schedule",
        DAILY_QUERY,
        f"{start_date:%Y-%m-%d}T00:00:00",
        f"{end_date:%Y-%m-%d}T23:59:59",
    )
    return (result.get("daily") or {}).get("date") or {}


def fetch_available_slots(config, day):
    """해당 날짜의 실제 진료 슬롯 중 예약 가능한 것을 {'HH:MM': 남은자리}로 반환."""
    result = graphql(
        config,
        "hourlySchedule",
        HOURLY_QUERY,
        f"{day}T00:00:00",
        f"{day}T23:59:59",
    )
    now = datetime.now()
    # 당일 예약을 안 받는 업체는 오늘 슬롯이 화면에 안 뜨므로 min_lead_days=1로 제외
    min_bookable_date = now.date() + timedelta(days=config.get("min_lead_days", 1))
    available = {}
    for slot in result.get("hourly") or []:
        if not (slot["isUnitBusinessDay"] and slot["isUnitSaleDay"]):
            continue  # 진료 시간이 아닌 슬롯
        start = datetime.strptime(slot["unitStartTime"], "%Y-%m-%d %H:%M:%S")
        if start <= now or start.date() < min_bookable_date:
            continue
        if not (config["watch_start_hour"] <= start.hour < config["watch_end_hour"]):
            continue
        remaining = (
            slot["unitStock"]
            - slot["unitBookingCount"]
            - slot["occupiedBookingCount"]
        )
        if remaining > 0:
            available[f"{start:%H:%M}"] = remaining
    return available


def send_telegram(config, text, chat_ids=None):
    """chat_ids 미지정 시 telegram_chat_id로 발송. 문자열/리스트 모두 지원."""
    if chat_ids is None:
        chat_ids = config["telegram_chat_id"]
    if not isinstance(chat_ids, list):
        chat_ids = [chat_ids]
    for chat_id in chat_ids:
        try:
            post_json(
                f"https://api.telegram.org/bot{config['telegram_token']}/sendMessage",
                {"chat_id": chat_id, "text": text},
                {},
            )
        except Exception as e:  # 한 명 실패해도 나머지에겐 발송
            log(f"텔레그램 발송 실패 (chat_id={chat_id}): {e}")


def format_new_slots(new_by_date):
    lines = []
    for day in sorted(new_by_date):
        weekday = WEEKDAY_KO[datetime.strptime(day, "%Y-%m-%d").weekday()]
        times = ", ".join(
            f"{t}({remaining}자리)" for t, remaining in sorted(new_by_date[day].items())
        )
        lines.append(f"📅 {day}({weekday}) {times}")
    return "\n".join(lines)


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return None


def save_state(state):
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def ping_healthcheck(config):
    """검사 성공마다 healthchecks.io에 생존 신호를 보낸다.

    신호가 끊기면 healthchecks.io가 대신 '다운됨' 알림을 보낸다 (죽은
    프로그램은 스스로 알릴 수 없으므로 외부 감시가 필요).
    """
    url = config.get("healthcheck_url")
    if not url:
        return
    try:
        urllib.request.urlopen(url, timeout=10)
    except Exception:
        pass  # 감시 서비스 쪽 일시 장애가 본 기능을 막으면 안 됨


def maybe_send_heartbeat(config, state):
    """heartbeat_hour시 이후 첫 검사 때 하루 1회 생존 신고를 보낸다.

    이 메시지가 매일 오지 않으면 서버/스크립트에 문제가 생긴 것.
    """
    hour = config.get("heartbeat_hour")
    if hour is None:
        return
    now = datetime.now()
    today_key = f"{now.date():%Y-%m-%d}"
    if now.hour >= hour and state.get("last_heartbeat_date") != today_key:
        state["last_heartbeat_date"] = today_key
        total = sum(len(slots) for slots in state["available"].values())
        send_telegram(
            config,
            f"💓 [{config['place_name']}] 감시 정상 작동 중 "
            f"(예약 가능 슬롯 {total}개)",
            chat_ids=config.get("heartbeat_chat_id"),  # 미지정 시 기본 수신자
        )


def check_once(config):
    state = load_state()
    first_run = state is None
    if first_run:
        state = {"day_summaries": {}, "available": {}}

    summaries = fetch_day_summaries(config)
    today_key = f"{datetime.now().date():%Y-%m-%d}"

    # 감시 대상: 휴무 요일 제외, 집계가 직전과 달라진 날짜만 상세 조회
    changed_days = [
        day
        for day, signature in summaries.items()
        if is_watched_date(config, datetime.strptime(day, "%Y-%m-%d").date())
        and state["day_summaries"].get(day) != signature
    ]

    new_by_date = {}
    for day in sorted(changed_days):
        available = fetch_available_slots(config, day)
        previous = state["available"].get(day, {})
        new_times = {
            t: remaining for t, remaining in available.items() if t not in previous
        }
        if new_times and not first_run:
            new_by_date[day] = new_times
        state["available"][day] = available
        time.sleep(0.5)  # 요청 간격을 두어 차단 방지

    # 지난 날짜 상태 정리
    state["day_summaries"] = summaries
    state["available"] = {
        day: slots for day, slots in state["available"].items() if day >= today_key
    }
    maybe_send_heartbeat(config, state)
    save_state(state)

    if first_run:
        total = sum(len(s) for s in state["available"].values())
        log(f"첫 실행: 날짜 {len(changed_days)}개 조회, 현재 예약 가능 슬롯 {total}개")
        send_telegram(
            config,
            f"✅ [{config['place_name']}] 감시 시작\n"
            f"현재 예약 가능 슬롯 {total}개. 취소표/월 오픈이 생기면 알려드릴게요.",
        )
    elif new_by_date:
        count = sum(len(v) for v in new_by_date.values())
        log(f"새 슬롯 {count}개 발견: {new_by_date}")
        send_telegram(
            config,
            f"🔔 [{config['place_name']}] 예약 자리 발견!\n\n"
            f"{format_new_slots(new_by_date)}\n\n{place_link(config)}",
        )
    else:
        log(f"변화 없음 (상세 조회한 날짜 {len(changed_days)}개)")


def main():
    config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    if "봇_토큰" in config["telegram_token"]:
        sys.exit("config.json에 telegram_token과 telegram_chat_id를 먼저 입력하세요.")

    once = "--once" in sys.argv
    if not once:
        prevent_system_sleep()
    consecutive_failures = 0

    while True:
        try:
            check_once(config)
            consecutive_failures = 0
            ping_healthcheck(config)
        except Exception as e:  # 네트워크/스키마 변경 등 어떤 실패든 기록
            consecutive_failures += 1
            log(f"검사 실패({consecutive_failures}회 연속): {e}")
            if consecutive_failures == ERROR_NOTIFY_THRESHOLD:
                try:
                    send_telegram(
                        config,
                        f"⚠️ [{config['place_name']}] 감시 스크립트가 "
                        f"{ERROR_NOTIFY_THRESHOLD}회 연속 실패했습니다: {e}",
                    )
                except Exception:
                    pass
        if once:
            break
        time.sleep(config["interval_seconds"])


if __name__ == "__main__":
    main()
