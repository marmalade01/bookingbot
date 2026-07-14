# 서버에 코드 업로드 + 서비스 재시작 (더블클릭 불가 — PowerShell에서 실행)
# 사용법: PowerShell에서  .\redeploy.ps1

$KEY = "C:\Users\Seadronix\Desktop\김주영\qa 자동화 tool\클라우드 오라클 ssh key\oracle ssh key(amd)\ssh-key-2026-01-22.key"
$SERVER = "ubuntu@168.107.2.200"
$SRC = "C:\QaProject\naver-booking-watch"

Write-Host "[1/2] 파일 업로드 중..."
scp -i $KEY "$SRC\watch.py" "$SRC\config.json" "${SERVER}:~/naver-booking-watch/"
if (-not $?) { Write-Host "업로드 실패"; exit 1 }

Write-Host "[2/2] 서비스 재시작 중..."
ssh -i $KEY $SERVER "sudo systemctl restart naver-watch && systemctl is-active naver-watch"

Write-Host "완료. 'active' 라고 떴으면 정상 반영된 것."
