# 코인 상시 봇 — OKX 한 거래소(현물 + 선물) + Render + 텔레그램

봇이 24시간 돌면서 ① 매일 09:05(KST)에 신호를 보고 모의/실제 주문 ② 20초마다 손절·본전 이동 감시 ③ 텔레그램으로 알림·명령. 노트북은 꺼도 됩니다.
**현물(BTC-USDT·ETH-USDT)과 선물(BTC-USDT 무기한)을 모두 OKX 한 곳, 같은 API 키로** 돌립니다(업비트는 선물이 없어서 선택 옵션으로만 남겼습니다: SPOT_EXCHANGE=upbit).
기본은 전부 «모의»(MODE_SPOT=paper, MODE_FUT=paper) — 진짜 주문은 아래 «실거래로 넘어가기»를 사용자가 직접 할 때만 나갑니다. 내(Claude)는 키·토큰·계정·결제를 보지도 만지지도 않습니다.

⚠ 연구 결과: 이 전략(추세+방어)은 «존버보다 낫다»가 통계로 확인되지 않았고 방어(낙폭 감소)용 후보입니다. 선물은 레버리지만큼 손실이 커집니다. 잃어도 되는 금액으로, 모의 → 데모 → 최소 금액 순서로만.

## 0) 가장 쉬운 방법 — 주소 하나 + 환경변수
1. Render → New → Background Worker(또는 Web Service) → «Public Git Repository» 에 이 저장소 주소를 붙여 넣습니다. Build 명령은 pip install -r requirements.txt, Start 명령은 python bot.py. (Blueprint 로 render.yaml 을 읽게 해도 됩니다.)
2. Render Environment 에 값만 등록합니다.
   - TELEGRAM_BOT_TOKEN : 봇 토큰
   - TELEGRAM_CHAT_ID : 봇 ID 가 아니라 «내 채팅 ID» (새 봇에게 말을 걸고 https://api.telegram.org/bot(토큰)/getUpdates 의 chat.id)
   - OKX_API_KEY, OKX_API_SECRET, OKX_API_PASSPHRASE : OKX 키(현물·선물 공용). 처음엔 비워 둬도 모의는 돌아갑니다.
   처음엔 MODE_SPOT=paper, MODE_FUT=paper 그대로 두면 키가 있어도 주문하지 않습니다.
3. 예전 «탈개미» 서비스가 같은 OKX 키로 돌고 있다면 먼저 Render 에서 Suspend/삭제하세요(두 프로그램이 같은 키로 동시에 주문하면 중복 주문). 텔레그램 봇도 새로 만든 봇을 쓰세요(같은 토큰을 두 프로그램이 쓰면 메시지를 서로 가로챕니다).
4. 무료 Web Service 는 일정 시간 요청이 없으면 잠들고 디스크가 없어 재시작 때 장부가 초기화됩니다 → 모의 시험엔 괜찮지만 실거래엔 «디스크가 붙은 유료 인스턴스»(Background Worker + Disk, DATA_DIR=/data)가 필수입니다. 봇이 «상태 파일이 없어 새로 시작» 알림으로 알려 줍니다.

## 1) 텔레그램 봇 만들기
1. 텔레그램에서 @BotFather → /newbot → 이름 정하면 토큰이 나옵니다(TELEGRAM_BOT_TOKEN).
2. 만든 봇에게 아무 말이나 보낸 뒤, 브라우저에서 https://api.telegram.org/bot(토큰)/getUpdates 를 열면 "chat":{"id": 숫자} 가 보입니다(TELEGRAM_CHAT_ID). 이 채팅의 명령만 받습니다.

## 2) 폰에서 쓰는 명령
/상태 포지션·손익·손절가 · /신호 오늘 신호 · /중지 신규 진입만 중단(보유분 손절 감시는 계속) · /재개 · /청산 → 60초 안에 /청산확인 = 봇이 가진 포지션 전량 시장가 청산 + 정지.

## 3) 손절·익절 규칙 (연구 기반 기본값, 환경변수로 변경)
- 손절: 현물 8%(3~15), 선물 6%(청산거리의 60% 이하로 자동 제한). 모든 진입에 손절이 붙습니다(현물=봇이 20초마다 감시, 선물=거래소에 동봉 주문).
- 익절 목표: 기본 없음. 연구에서 고정 익절(+10~20%)은 추세 수익을 연 0~1%로 깎았습니다. 필요하면 TP_PCT_SPOT.
- 본전 이동: +8%(선물 +6%) 닿으면 손절을 진입가로 올립니다(낙폭 -45% → -34%, 수익 비슷).
- 출구: 신호가 꺼지면 청산. 손절·익절된 뒤엔 신호가 한 번 꺼졌다 켜질 때까지 재진입하지 않습니다. 손실 한도(현물 25%·선물 15%) 넘으면 전량 청산 후 정지.
- 현물 손절은 봇이 감시하므로 봇이 켜져 있어야 보호됩니다(Render 가 꺼지면 감시도 멈춤 — 텔레그램 «봇 시작» 알림이 다시 오는지 확인).
- 전략: 현물은 BTC 일봉 종가가 EMA100 위일 때 BTC·ETH 반반 보유, 선물은 종가가 EMA100 그리고 EMA50 위일 때만 롱(숏 없음, 레버리지 최대 2배, 격리 마진).

## 4) 예산 설정 (환경변수)
- BUDGET_SPOT_USDT : 현물에 굴릴 최대 금액(USDT, 기본 100, 최소 20)
- BUDGET_USDT : 선물 증거금(USDT, 기본 100), LEVERAGE : 1~2
- 현물+선물 예산 합계가 OKX 계정 잔고보다 작아야 합니다(봇은 계정 전체가 아니라 예산만 씁니다).

## 5) 실거래로 넘어가기 (사용자가 직접, 순서대로)
1. 모의로 몇 주 돌려 알림·손절·본전 이동이 설계대로 오는지 봅니다(/상태).
2. OKX 데모 거래(가짜 돈): OKX 에서 데모 전용 API 키를 만들어 OKX_API_* 에 넣고 MODE_SPOT=demo, MODE_FUT=demo 로 주문·손절·본전 이동이 되는지 확인합니다.
3. 실계정: 실계정 API 키(권한은 «읽기 + 거래»만, 출금 절대 금지, 가능하면 허용 IP 에 Render 출력 IP 등록)를 넣고 MODE_SPOT=live + AUTOTRADE_LIVE=YES(현물), MODE_FUT=live + AUTOTRADE_LIVE_FUTURES=YES(선물). 첫 실행은 아주 작은 예산(현물 20 USDT 안팎, 선물 최소 계약)으로.
4. 한국에서 OKX 이용 가능 여부·규제·세금은 사용자가 직접 확인하세요(법률·세무 자문 아님).
5. 문제가 생기면 텔레그램 /청산 → /청산확인, 그리고 OKX 앱에서 직접 확인.

## 6) 알아 둘 것
- 실계좌·데모 주문 경로는 실제 키로 끝까지 시험하지 못한 코드입니다(요청 형태만 확인). 그래서 «모의 → 데모 → 최소 금액» 순서가 필수입니다.
- 비용: Render 백그라운드 워커(디스크 포함 유료 인스턴스) 월 요금이 듭니다(Render 요금 페이지 확인). 디스크는 GB당 월 약 0.25달러.
- 업비트로 현물을 하고 싶으면 SPOT_EXCHANGE=upbit, BUDGET_KRW, UPBIT_ACCESS_KEY, UPBIT_SECRET_KEY 를 쓰면 됩니다(업비트 주문 API 는 허용 IP 등록 필수, 선물은 여전히 OKX).
- 파일 구성: bot.py(메인) · spot.py(현물 거래소 어댑터: OKX/업비트) · rules.py(손절·익절·본전) · okx.py · upbit.py · tg.py · render.yaml · requirements.txt.
