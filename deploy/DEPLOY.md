# Oracle Cloud 배포 & 코드 업데이트 가이드

네이버 예약 감시 봇을 Oracle Cloud 무료 VM에서 24시간 돌리기 위한 문서.

## 현재 배포 정보

| 항목 | 값 |
|---|---|
| 서버 | Oracle Cloud `instance-20260122-1022` (South Korea North) |
| Public IP | `168.107.2.200` |
| 접속 계정 | `ubuntu` |
| SSH 키 | `C:\Users\Seadronix\Desktop\김주영\qa 자동화 tool\클라우드 오라클 ssh key\oracle ssh key(amd)\ssh-key-2026-01-22.key` |
| 서버 내 코드 위치 | `/home/ubuntu/naver-booking-watch/` |
| 서비스 이름 | `naver-watch` (systemd) |

## ⚠️ 먼저: 창 2개를 구분할 것

작업할 때 열게 되는 창이 2종류이고, **명령어를 어느 창에 치는지가 제일 흔한 실수 포인트**다.

| 창 | 프롬프트 모양 | 여기서 하는 것 |
|---|---|---|
| **PC PowerShell** | `PS C:\>` | `ssh` 접속, `scp` 파일 업로드, `redeploy.ps1` |
| **서버 (SSH 접속 후)** | `ubuntu@instance-...:~$` | `python3`, `sudo systemctl`, `tail` 등 나머지 전부 |

- PowerShell에서 `&&` 는 문법 에러가 난다 → `&&` 가 들어간 명령은 전부 서버용
- 서버 창에서 `ssh ...` 를 또 치면 서버가 자기 자신에 접속하려 한다 → 이미 접속돼 있으면 ssh 불필요

---

# 1부. 처음부터 배포하기

## 1-1. 서버 접속

PC PowerShell에서:

```powershell
ssh -i "C:\Users\Seadronix\Desktop\김주영\qa 자동화 tool\클라우드 오라클 ssh key\oracle ssh key(amd)\ssh-key-2026-01-22.key" ubuntu@168.107.2.200
```

- 처음 접속하는 PC라면 `Are you sure you want to continue connecting?` → `yes` 입력
- 프롬프트가 `ubuntu@instance-...:~$` 로 바뀌면 접속 성공

**자주 나는 에러:**

| 에러 | 원인 / 해결 |
|---|---|
| `Identity file ... not accessible` | 키 파일 경로가 틀림. 경로에 공백이 있으면 반드시 큰따옴표로 감쌀 것 |
| `UNPROTECTED PRIVATE KEY FILE` | 키 파일 권한이 열려 있음. 아래 두 줄 실행 후 재시도:<br>`icacls "<키경로>" /inheritance:r`<br>`icacls "<키경로>" /grant:r "$env:USERNAME:R"` |
| `Permission denied (publickey)` | 이 VM의 키가 아님. VM 만들 때 받은 키인지 확인 |
| 접속 자체가 안 됨 (타임아웃) | VM이 Stopped 상태이거나 Public IP가 없음. Oracle 콘솔 → Compute → Instances에서 확인 |

## 1-2. 서버 기본 설정 (최초 1회)

서버 창에서:

```bash
sudo timedatectl set-timezone Asia/Seoul   # 필수! 스크립트가 서버 시계 기준으로 동작
mkdir -p ~/naver-booking-watch
date                                        # 한국 시간이 나오는지 확인
```

## 1-3. 파일 업로드

**새 PC PowerShell 창**에서 (서버 창 말고):

```powershell
scp -i "C:\Users\Seadronix\Desktop\김주영\qa 자동화 tool\클라우드 오라클 ssh key\oracle ssh key(amd)\ssh-key-2026-01-22.key" C:\QaProject\naver-booking-watch\watch.py C:\QaProject\naver-booking-watch\config.json ubuntu@168.107.2.200:~/naver-booking-watch/

scp -i "C:\Users\Seadronix\Desktop\김주영\qa 자동화 tool\클라우드 오라클 ssh key\oracle ssh key(amd)\ssh-key-2026-01-22.key" C:\QaProject\naver-booking-watch\deploy\naver-watch.service ubuntu@168.107.2.200:~/
```

각 파일마다 `100%` 표시가 나오면 성공.

> `config.json`은 토큰이 들어 있어 GitHub에는 없다. PC의 원본을 올리거나,
> 서버에서 `config.example.json`을 복사해 직접 채운다.

## 1-4. 동작 테스트

서버 창에서:

```bash
cd ~/naver-booking-watch && python3 watch.py --once
```

- 성공: `첫 실행: 날짜 N개 조회, 현재 예약 가능 슬롯 N개` 출력 + 폰 텔레그램으로 "✅ 감시 시작" 수신
- 실패하면 여기서 멈추고 에러부터 해결할 것 (아직 서비스 등록 전이라 디버깅이 쉬움)

## 1-5. 상시 실행 등록 (systemd)

서버 창에서:

```bash
sudo mv ~/naver-watch.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now naver-watch
systemctl status naver-watch     # "Active: active (running)" 확인, q로 나가기
```

이제 SSH를 끊어도, PC를 꺼도 서버에서 계속 돈다.
부팅 시 자동 시작 + 스크립트가 죽으면 30초 후 자동 재시작.

**⚠️ PC(회사 컴퓨터)에서 돌리던 감시가 있다면 꺼줄 것** — 둘 다 켜면 알림이 중복으로 온다.

---

# 2부. 코드 업데이트 반영하기

파일만 바꿔서는 반영 안 된다. **업로드 + 서비스 재시작**이 한 세트.
(파이썬은 시작할 때 코드/설정을 메모리에 올려두고 돌기 때문)

## 방법 A: 원클릭 스크립트 (권장)

PC PowerShell에서:

```powershell
cd C:\QaProject\naver-booking-watch\deploy
.\redeploy.ps1
```

`watch.py` + `config.json` 업로드 → 서비스 재시작까지 자동. 마지막에 `active` 가 출력되면 반영 완료.

> 처음 실행할 때 "이 시스템에서 스크립트를 실행할 수 없습니다" 에러가 나면:
> `powershell -ExecutionPolicy Bypass -File .\redeploy.ps1` 로 실행

## 방법 B: 수동

```powershell
# ① PC PowerShell: 수정한 파일 업로드
scp -i "<키경로>" C:\QaProject\naver-booking-watch\watch.py ubuntu@168.107.2.200:~/naver-booking-watch/
```

```bash
# ② 서버: 재시작
sudo systemctl restart naver-watch
systemctl is-active naver-watch    # "active" 나오면 OK
```

## 업데이트 시 알아둘 것

- **config.json만 바꿔도 재시작 필요** (설정도 시작 시 1회만 읽음)
- **state.json은 유지됨** — 재배포해도 "이미 알림 보낸 슬롯" 기억은 안 사라진다
- 감시 상태를 초기화하고 싶으면 (처음부터 다시 스캔 + "감시 시작" 메시지 재발송):
  ```bash
  rm ~/naver-booking-watch/state.json && sudo systemctl restart naver-watch
  ```

---

# 3부. 운영 명령어 모음 (서버 창)

```bash
# 감시 로그 실시간 보기 (2분마다 "변화 없음..." 이 찍히면 정상)
tail -f ~/naver-booking-watch/watch.log        # Ctrl+C로 종료

# 최근 로그 20줄
tail -20 ~/naver-booking-watch/watch.log

# 서비스 상태 / 중지 / 시작 / 재시작
systemctl status naver-watch
sudo systemctl stop naver-watch
sudo systemctl start naver-watch
sudo systemctl restart naver-watch

# 서비스 레벨 로그 (파이썬이 뜨자마자 죽는 경우 원인 확인)
journalctl -u naver-watch -n 50
```

## 이상 신호와 대처

| 증상 | 대처 |
|---|---|
| 텔레그램으로 "⚠️ 5회 연속 실패" 수신 | 네이버 API 변경 또는 차단. `journalctl -u naver-watch -n 50` 로 에러 확인 |
| 알림이 한동안 아예 없음 | 정상일 수 있음(변화가 없으면 조용함). `tail watch.log` 로 2분마다 검사가 도는지 확인 |
| 서버 접속이 안 됨 | Oracle 콘솔에서 인스턴스가 Running인지 확인. Oracle 무료 VM은 드물게 회수 통지가 옴(이메일 확인) |
