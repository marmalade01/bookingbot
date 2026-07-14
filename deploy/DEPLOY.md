# Oracle Cloud 배포 절차

## 사전 준비

- Oracle Cloud 가입 (홈 리전: Seoul), VM 생성 (Ubuntu 24.04, VM.Standard.E2.1.Micro)
- SSH private key 파일, VM의 Public IP

## 1. 파일 업로드 (PC의 PowerShell에서)

```powershell
scp -i <키파일> C:\QaProject\naver-booking-watch\watch.py C:\QaProject\naver-booking-watch\config.json ubuntu@<IP>:~/naver-booking-watch/
scp -i <키파일> C:\QaProject\naver-booking-watch\deploy\naver-watch.service ubuntu@<IP>:~/
```

## 2. 서버 설정 (SSH 접속 후)

```bash
sudo timedatectl set-timezone Asia/Seoul

# 동작 확인 (1회 검사, 텔레그램 메시지 수신 확인)
cd ~/naver-booking-watch && python3 watch.py --once

# 서비스 등록
sudo mv ~/naver-watch.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now naver-watch
```

## 3. 상태 확인

```bash
systemctl status naver-watch          # 실행 상태
tail -f ~/naver-booking-watch/watch.log   # 감시 로그 실시간 보기
journalctl -u naver-watch -f          # 서비스 로그
```

## 4. 설정 변경 시

```bash
nano ~/naver-booking-watch/config.json   # 수정 후
sudo systemctl restart naver-watch
```

## 참고

- 서비스는 부팅 시 자동 시작, 스크립트가 죽어도 30초 후 자동 재시작된다.
- 감시를 멈추려면: `sudo systemctl stop naver-watch` (다시 켜려면 start)
- PC의 감시 프로그램과 동시에 돌리면 알림이 중복으로 오므로 한쪽만 켤 것.
