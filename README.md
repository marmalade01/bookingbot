# naver-booking-watch

네이버 예약 취소표/월 오픈이 생기면 텔레그램으로 알려주는 감시 스크립트.

## 동작 방식

1. `interval_seconds`마다 daily 쿼리 **1번**으로 오늘~`watch_range_days`일 뒤까지 날짜별 집계(재고/예약수) + 예약가능 여부(`isBusinessDay`) 조회
2. 직전 검사와 집계가 달라진 날짜만 hourly 쿼리로 상세 조회 (평소엔 요청 1회로 끝)
3. 실제 진료 슬롯(`isUnitBusinessDay=true`) 중 `unitStock - unitBookingCount - occupiedBookingCount > 0`인 슬롯만 예약 가능으로 판정
4. 두 종류의 알림을 발송:
   - 🔔 **취소표**: 마감 슬롯이 취소로 풀려 직전 상태에 없던 새 슬롯이 생긴 순간
   - 🗓️ **예약 오픈**: 잠겨 있던(`isBusinessDay=false`) 날짜가 새로 열리는 순간(월 오픈 등). 여러 날이 한꺼번에 열리므로, 알림받고 들어가 원하는 시간을 선점하기 좋음
5. 5회 연속 조회 실패 시(네이버 API 변경/차단 등) 에러 알림 1회 발송

알림 링크는 딥링크 대신 실제 예약이 열리는 네이버 플레이스 예약 화면(`m.place.naver.com/hospital/{place_id}/home`)으로 보낸다.

## 설정 (config.json)

| 키 | 설명 |
|---|---|
| `telegram_token` | 텔레그램 봇 토큰 |
| `telegram_chat_id` | 알림 받을 chat id |
| `business_id` / `biz_item_id` | 예약 URL의 `bizes/{business_id}/items/{biz_item_id}` |
| `exclude_weekdays` | 감시 제외 요일 (예: `["수", "금"]` = 정기 휴무) |
| `watch_start_hour` / `watch_end_hour` | 알림 대상 시간대 (예: 9~20시) |
| `interval_seconds` | 검사 주기 (초). 너무 짧으면 차단 위험 |

감시 범위는 **오늘부터 다음달 말일까지** 자동 계산된다.

## 실행

- **콘솔 창 보면서 실행**: `run_watch.bat` 더블클릭
- **백그라운드 실행**: `start_hidden.vbs` 더블클릭 (창 없이 실행됨)
  - 종료: 작업 관리자에서 `pythonw.exe` 종료
- **1회만 검사**: `python watch.py --once` (Windows 작업 스케줄러 등록용)

부팅 시 자동 시작하려면: `Win+R` → `shell:startup` → 열린 폴더에 `start_hidden.vbs` 바로가기 추가.

## 로그 / 상태

- `watch.log` — 검사 기록
- `state.json` — 직전 검사 상태. 삭제하면 다음 실행이 "첫 실행"으로 초기화됨 (감시 시작 메시지 재발송)
