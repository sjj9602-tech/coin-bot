# -*- coding: utf-8 -*-
"""업비트 클라이언트 — 공개 시세 + (선택) 개인 API(JWT HS256 직접 생성). 열쇠는 환경변수 UPBIT_ACCESS_KEY / UPBIT_SECRET_KEY 로만.
업비트 API 관리에서 열쇠를 만들 때 «자산조회·주문조회·주문하기»만 켜고 «출금하기»는 절대 켜지 말고, «허용 IP» 에 Render 의 출력 IP 를 등록한다."""
import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests

API = "https://api.upbit.com/v1"


def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=")


def _토큰(질의=None):
    a, s = os.environ.get("UPBIT_ACCESS_KEY", ""), os.environ.get("UPBIT_SECRET_KEY", "")
    if not a or not s:
        raise RuntimeError("UPBIT_ACCESS_KEY / UPBIT_SECRET_KEY 환경변수가 없다")
    본 = {"access_key": a, "nonce": str(uuid.uuid4())}
    if 질의:
        본["query_hash"] = hashlib.sha512(urlencode(질의, doseq=True).encode()).hexdigest()
        본["query_hash_alg"] = "SHA512"
    머리 = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    몸 = _b64(json.dumps(본, separators=(",", ":")).encode())
    서명 = _b64(hmac.new(s.encode(), 머리 + b"." + 몸, hashlib.sha256).digest())
    return (머리 + b"." + 몸 + b"." + 서명).decode()


def _호출(방식, 경로, 질의=None, 재시도=3):
    for i in range(재시도):
        헤더 = {"Authorization": "Bearer " + _토큰(질의), "Accept": "application/json"}
        if 방식 == "GET":
            r = requests.get(API + 경로, params=질의, headers=헤더, timeout=15)
        else:
            헤더["Content-Type"] = "application/json; charset=utf-8"
            r = requests.request(방식, API + 경로, data=json.dumps(질의) if 질의 else None, headers=헤더, timeout=15)
        if r.status_code == 429:
            time.sleep(1 + i)
            continue
        if r.status_code >= 400:
            raise RuntimeError("업비트 %s %s → %d %s" % (방식, 경로, r.status_code, r.text[:300]))
        return r.json()
    raise RuntimeError("요청 제한에 계속 걸림: " + 경로)


# ───── 공개 시세 ─────
def 현재가(시장들):
    r = requests.get(API + "/ticker", params={"markets": ",".join(시장들)}, timeout=15)
    r.raise_for_status()
    return {x["market"]: float(x["trade_price"]) for x in r.json()}


def 마감일봉종가(시장, 개수=200):
    """마감된 일봉 종가(오래된 순). 진행 중인 오늘(UTC) 봉은 뺀다."""
    r = requests.get(API + "/candles/days", params={"market": 시장, "count": 개수}, timeout=15)
    r.raise_for_status()
    오늘 = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rows = [x for x in r.json() if x["candle_date_time_utc"][:10] < 오늘]
    rows.sort(key=lambda x: x["candle_date_time_utc"])
    return [float(x["trade_price"]) for x in rows]


def ema(값들, n):
    a, o = 2.0 / (n + 1), []
    for i, v in enumerate(값들):
        o.append(v if i == 0 else a * v + (1 - a) * o[-1])
    return o


# ───── 개인 API ─────
def 원화잔고():
    for x in _호출("GET", "/accounts"):
        if x["currency"] == "KRW":
            return float(x["balance"])
    return 0.0


def 보유수량(시장):
    코인 = 시장.split("-")[1]
    for x in _호출("GET", "/accounts"):
        if x["currency"] == 코인:
            return float(x["balance"]) + float(x["locked"])
    return 0.0


def 시장가매수(시장, 원):
    return _호출("POST", "/orders", {"market": 시장, "side": "bid", "price": str(int(원)), "ord_type": "price"})


def 시장가매도(시장, 수량):
    return _호출("POST", "/orders", {"market": 시장, "side": "ask", "volume": "%.8f" % float(수량), "ord_type": "market"})


def 체결확인(uuid_, 시도=10):
    """주문이 끝날 때까지 기다려 (체결수량, 체결금액, 수수료)."""
    for _ in range(시도):
        o = _호출("GET", "/order", {"uuid": uuid_})
        if o.get("state") in ("done", "cancel"):
            수량 = float(o.get("executed_volume") or 0)
            금액 = sum(float(t["funds"]) for t in o.get("trades", [])) if o.get("trades") else 0.0
            return 수량, 금액, float(o.get("paid_fee") or 0)
        time.sleep(1)
    raise RuntimeError("주문 %s 체결 확인 시간 초과 — 업비트 앱에서 직접 확인" % uuid_)
