# 코인 상시 봇 — Render + 텔레그램 배포 안내 (사용자가 직접 하는 부분)

이 폴더 = 저장소 하나. 봇이 24시간 돌면서 ① 매일 09:05(KST)에 신호를 보고 모의/실제 주문 ② 20초마다 **손절·본전 이동 감시** ③ 텔레그램으로 알림·명령. 노트북은 꺼도 됩니다.
**기본은 전부 «모의»**(`MODE_SPOT=paper`, `MODE_FUT=paper`). 진짜 주문은 아래 «실거래로 넘어가기»를 사용자가 직접 할 때만 나갑니다. 내(Claude)는 키·토큰·계정·결제를 보지도 만지지도 않습니다.

⚠ 연구 결과: 이 전략(추세+방어)은 «존버보다 낫다»가 통계로 확인되지 않았고 방어(낙폭 감소)용 후보입니다. 선물은 레버리지만큼 손실이 커집니다. 잃어도 되는 금액으로, 모의 → 데모/최소 금액 순서로만.

## 0) 가장 쉬운 방법 — 예전에 하신 방식 그대로 (주소 하나 + 환경변수)
1. GitHub 에서 빈 저장소를 하나 만듭니다(이름 `coin-bot`, **Public 이면 Render 에 주소만 넣으면 됩니다**. 코드에 키가 없어 공개돼도 안전합니다. Private 이면 Render 에 GitHub 연동 필요). 이 폴더의 파일 9개를 올립니다 — 웹에서 «Add file → Upload files» 로 끌어다 놓거나, 저장소 주소를 Claude 에게 알려 주면 이 PC 에서 올려 줍니다.
2. Render → New → **Background Worker**(또는 Web Service) → «Public Git Repository» 에 그 **저장소 주소**를 붙여 넣습니다. Build: `pip install -r requirements.txt`, Start: `python bot.py`. (Blueprint 로 `render.yaml` 을 읽게 해도 됩니다.)
3. Render **Environment** 에 값만 등록(예전에 하신 것과 같음): `TELEGRAM_BOT_TOKEN`(봇 토큰) · `TELEGRAM_CHAT_ID`(⚠ **봇 ID 가 아니라 «내 채팅 ID»**: 새 봇에게 말을 걸고 `https://api.telegram.org/bot<토큰>/getUpdates` 의 `chat.id`) · `UPBIT_ACCESS_KEY` · `UPBIT_SECRET_KEY` · (선물) `OKX_API_KEY` · `OKX_API_SECRET` · `OKX_API_PASSPHRASE`. 처음엔 `MODE_SPOT=paper`, `MODE_FUT=paper` 그대로 두면 키가 있어도 주문하지 않습니다.
4. ⚠ **예전 «탈개미» 서비스가 같은 업비트 키로 돌고 있다면 먼저 Render 에서 Suspend/삭제**하세요(두 프로그램이 같은 키로 동시에 주문하면 중복 주문). 텔레그램 봇도 **새로 만든 봇**을 쓰세요(같은 토큰을 두 프로그램이 쓰면 메시지를 서로 가로챕니다). 예전에 업비트 «허용 IP» 에 Render IP 를 이미 등록하셨다면 같은 지역(Singapore 등)으로 배포하면 그 IP 를 그대로 쓸 수 있습니다.
5. 무료 Web Service 는 일정 시간 요청이 없으면 잠들고 디스크가 없어 재시작 때 장부가 초기화됩니다 → **모의 시험엔 괜찮지만 실거래엔 «디스크가 붙은 유료 인스턴스»(Background Worker + Disk)가 필수**입니다(봇이 «상태 파일이 없어 새로 시작» 알림으로 알려 줍니다).
## 1) 텔레그램 봇 만들기 (이미 해 보셨으니 새 봇으로)
1. 텔레그램에서 **@BotFather** → `/newbot` → 이름 정하면 **토큰**이 나옵니다(=`TELEGRAM_BOT_TOKEN`). 기존 봇 토큰을 재사용하면 두 프로그램이 서로 메시지를 가로채니 **새 봇**을 만드세요.
2. 만든 봇에게 아무 말이나 보낸 뒤, 브라우저에서 `https://api.telegram.org/bot<토큰>/getUpdates` 를 열면 `"chat":{"id": 숫자}` 가 보입니다(=`TELEGRAM_CHAT_ID`). 이 채팅의 명령만 받습니다.

## 2) 코드를 GitHub 비공개 저장소에 올리기
이 폴더(`Documents\AI투자연구\배포\render`) 안의 파일만 새 **Private** 저장소의 루트에 올립니다.
```
cd <이 폴더 경로>
git init
git add .
git commit -m "coin bot"
git branch -M main
git remote add origin https://github.com/<내아이디>/coin-bot.git
git push -u origin main
```
(`.gitignore` 가 data·열쇠 파일을 제외합니다. 키는 저장소에 절대 넣지 않습니다.)

## 3) Render 에서 배포
1. Render → **New → Blueprint**(또는 Background Worker) → 위 저장소 선택 → `render.yaml` 이 읽힙니다(워커 1개·디스크 1GB·지역 Singapore).
2. `sync: false` 항목을 Render 화면에서 직접 입력: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (처음엔 이것만). 업비트·OKX 키는 모의 단계에선 비워 둡니다.
3. 배포가 끝나면 텔레그램에 «🤖 봇 시작 …» 이 옵니다. `/상태`, `/신호` 로 확인.

## 4) 폰에서 쓰는 명령
`/상태` 포지션·손익·손절가 · `/신호` 오늘 신호 · `/중지` 신규 진입만 중단(보유분 손절 감시는 계속) · `/재개` · `/청산` → 60초 안에 `/청산확인` = 봇이 가진 포지션 전량 시장가 청산 + 정지.

## 5) 손절·익절 규칙 (연구 기반 기본값, 환경변수로 변경)
- 손절: 현물 8%(3~15), 선물 6%(청산거리의 60% 이하로 자동 제한). **모든 진입에 손절이 붙습니다**(현물=봇이 20초마다 감시, 선물=거래소에 동봉 주문).
- 익절 목표: 기본 **없음**. 연구에서 고정 익절(+10~20%)은 추세 수익을 연 0~1%로 깎았습니다. 필요하면 `TP_PCT_SPOT`.
- 본전 이동: +8%(선물 +6%) 닿으면 손절을 진입가로 올립니다(낙폭 -45% → -34%, 수익 비슷).
- 출구: 신호가 꺼지면 청산. 손절·익절된 뒤엔 신호가 한 번 꺼졌다 켜질 때까지 재진입하지 않습니다. 손실 한도(현물 25%·선물 15%) 넘으면 전량 청산 후 정지.
- 현물은 거래소가 손절 주문을 못 받아서 **봇이 켜져 있어야 보호됩니다**(Render 가 꺼지면 손절 감시도 멈춤 — 텔레그램 «봇 시작» 알림이 다시 오는지 확인).

## 6) 실거래로 넘어가기 (사용자가 직접, 순서대로)
1. **모의로 몇 주** 돌려 알림·손절·본전 이동이 설계대로 오는지 봅니다(`/상태`).
2. **현물(업비트)**: 업비트 Open API 키를 «자산조회·주문조회·주문하기»만(출금 금지)으로 만들고 **허용 IP 에 Render 의 출력 IP 를 등록**합니다(업비트 주문 API 는 허용 IP 필수). Render 의 서비스 화면 → Connect → Outbound 에서 IP 목록을 확인하세요. 업비트는 키당 등록 가능 IP 수가 제한(5~10개)이라 Render 지역 IP 가 그보다 많으면 못 맞출 수 있습니다 → 그때는 Render 의 «전용 출력 IP» 옵션이나 고정 IP 서버를 검토.
   그다음 `UPBIT_ACCESS_KEY`, `UPBIT_SECRET_KEY` 입력 → `MODE_SPOT=live`, `AUTOTRADE_LIVE=YES`, `BUDGET_KRW` 를 잃어도 되는 금액으로. **첫 실행은 5천~1만 원대.**
3. **선물(OKX)**: 먼저 OKX **데모 거래**(가짜 돈)에서 데모 전용 API 키를 만들어 `MODE_FUT=demo` 로 주문·손절 동봉·본전 이동이 되는지 확인. 그다음에야 실계정(출금 권한 금지, 허용 IP 등록) + `MODE_FUT=live`, `AUTOTRADE_LIVE_FUTURES=YES`, `LEVERAGE` 는 1~2. 한국에서 OKX 이용 가능 여부·규제·세금은 사용자가 직접 확인하세요(법률·세무 자문 아님).
4. 문제가 생기면 텔레그램 `/청산` → `/청산확인`, 그리고 거래소 앱에서 직접 확인.

## 7) 알아 둘 것
- 실거래 경로(업비트·OKX 주문)는 **실계좌로 끝까지 시험하지 못한 코드**입니다. 그래서 «모의 → 데모 → 최소 금액» 순서가 필수입니다.
- 비용: Render 백그라운드 워커(디스크 포함 유료 인스턴스) 월 요금이 듭니다(렌더 요금 페이지 확인). 디스크는 GB당 월 약 0.25달러.
- 파일 구성: `bot.py`(메인) · `rules.py`(손절·익절·본전) · `upbit.py` · `okx.py` · `tg.py` · `render.yaml` · `requirements.txt`.
