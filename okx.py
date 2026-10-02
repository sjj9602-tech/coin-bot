# -*- coding: utf-8 -*-
"""OKX 무기한 스왑(BTC-USDT-SWAP) 클라이언트 — 공개 시세 + (선택) 개인 API. 열쇠는 환경변수 OKX_API_KEY/OKX_API_SECRET/OKX_API_PASSPHRASE 로만.
데모 거래(가짜 돈)는 OKX 데모 화면에서 만든 데모 전용 키 + 헤더 x-simulated-trading: 1. 출금 권한은 절대 켜지 말 것."""
import base64
import hashlib
import hmac
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = "https://www.okx.com"
INST = "BTC-USDT-SWAP"
SPOT = "BTC-USDT"


def 공개(경로, 값=None):
    url = BASE + 경로 + ("?" + urllib.parse.urlencode(값) if 값 else "")
    req = urllib.request.Request(url, headers={"User-Agent": "coinbot/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        j = json.loads(r.read().decode())
    if j.get("code") != "0":
        raise RuntimeError("OKX 오류 %s %s" % (j.get("code"), j.get("msg")))
    return j["data"]


def 현재가():
    return float(공개("/api/v5/market/ticker", {"instId": INST})[0]["last"])


def 종목가격(inst):
    """임의 종목(예: BTC-USDT 현물)의 현재가."""
    return float(공개("/api/v5/market/ticker", {"instId": inst})[0]["last"])


def 현물정보(inst):
    """현물 종목의 (최소 주문 수량, 수량 단위)."""
    d = 공개("/api/v5/public/instruments", {"instType": "SPOT", "instId": inst})[0]
    return float(d["minSz"]), float(d["lotSz"])


def 일봉종가(inst, 개수=300):
    rows = sorted(공개("/api/v5/market/candles", {"instId": inst, "bar": "1Dutc", "limit": str(개수)}), key=lambda r: int(r[0]))
    오늘 = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return [float(r[4]) for r in rows if datetime.fromtimestamp(int(r[0]) / 1000, tz=timezone.utc) < 오늘 and r[8] == "1"]


def 마감일봉종가(개수=300):
    rows = sorted(공개("/api/v5/market/candles", {"instId": SPOT, "bar": "1Dutc", "limit": str(개수)}), key=lambda r: int(r[0]))
    오늘 = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return [float(r[4]) for r in rows if datetime.fromtimestamp(int(r[0]) / 1000, tz=timezone.utc) < 오늘 and r[8] == "1"]


def 상품정보():
    d = 공개("/api/v5/public/instruments", {"instType": "SWAP", "instId": INST})[0]
    return float(d["ctVal"]), float(d["lotSz"]), float(d["minSz"])


class 계정:
    def __init__(self, 데모=False):
        self.k = os.environ.get("OKX_API_KEY", "")
        self.s = os.environ.get("OKX_API_SECRET", "")
        self.p = os.environ.get("OKX_API_PASSPHRASE", "")
        self.데모 = 데모
        if not (self.k and self.s and self.p):
            raise RuntimeError("OKX 열쇠 환경변수가 없다")

    def 요청(self, 방법, 경로, 값=None, 본문=None):
        q = ("?" + urllib.parse.urlencode(값)) if 값 else ""
        body = json.dumps(본문, separators=(",", ":")) if 본문 is not None else ""
        now = datetime.now(timezone.utc)
        ts = now.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (now.microsecond // 1000)
        서명 = base64.b64encode(hmac.new(self.s.encode(), (ts + 방법 + 경로 + q + body).encode(), hashlib.sha256).digest()).decode()
        h = {"OK-ACCESS-KEY": self.k, "OK-ACCESS-SIGN": 서명, "OK-ACCESS-TIMESTAMP": ts, "OK-ACCESS-PASSPHRASE": self.p,
             "Content-Type": "application/json", "User-Agent": "coinbot/1.0"}
        if self.데모:
            h["x-simulated-trading"] = "1"
        req = urllib.request.Request(BASE + 경로 + q, data=body.encode() if body else None, headers=h, method=방법)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                j = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            raise RuntimeError("OKX HTTP %d %s" % (e.code, e.read().decode()[:200]))
        if j.get("code") != "0":
            raise RuntimeError("OKX 오류 %s %s %s" % (j.get("code"), j.get("msg"), json.dumps(j.get("data"), ensure_ascii=False)[:200]))
        return j["data"]

    # ── 현물(cash) ──
    def _주문결과(self, d):
        if not d or d[0].get("sCode") not in (None, "0", 0):
            raise RuntimeError("OKX 주문 거절 %s %s" % (d[0].get("sCode") if d else "?", d[0].get("sMsg") if d else "?"))
        return d[0]["ordId"]

    def 현물시장가매수(self, inst, 금액):
        """견적통화(USDT) 금액만큼 시장가 매수."""
        return self._주문결과(self.요청("POST", "/api/v5/trade/order", 본문={"instId": inst, "tdMode": "cash", "side": "buy", "ordType": "market", "sz": "%.4f" % 금액, "tgtCcy": "quote_ccy"}))

    def 현물시장가매도(self, inst, 수량):
        """기초통화 수량만큼 시장가 매도."""
        s = ("%.8f" % 수량).rstrip("0").rstrip(".")
        return self._주문결과(self.요청("POST", "/api/v5/trade/order", 본문={"instId": inst, "tdMode": "cash", "side": "sell", "ordType": "market", "sz": s, "tgtCcy": "base_ccy"}))

    def 체결확인(self, inst, ord_id, 시도=12):
        """(체결수량, 평균가, 수수료(음수), 수수료통화). 끝날 때까지 최대 약 12초 기다린다."""
        import time
        for _ in range(시도):
            o = self.요청("GET", "/api/v5/trade/order", {"instId": inst, "ordId": ord_id})[0]
            if o.get("state") in ("filled", "canceled", "mmp_canceled"):
                return float(o.get("accFillSz") or 0), float(o.get("avgPx") or 0), float(o.get("fee") or 0), o.get("feeCcy", "")
            time.sleep(1)
        raise RuntimeError("OKX 주문 %s 체결 확인 시간 초과 — OKX 앱에서 직접 확인" % ord_id)

    def 가용(self, ccy):
        d = self.요청("GET", "/api/v5/account/balance", {"ccy": ccy})
        try:
            return float(d[0]["details"][0]["availBal"])
        except Exception:
            return 0.0

    def 총자산(self):
        d = self.요청("GET", "/api/v5/account/balance", {"ccy": "USDT"})
        return float(d[0].get("totalEq") or 0) if d else 0.0

    def 포지션(self):
        return [p for p in self.요청("GET", "/api/v5/account/positions", {"instId": INST}) if float(p.get("pos") or 0) != 0]

    def 포지션모드(self):
        return self.요청("GET", "/api/v5/account/config")[0].get("posMode", "net_mode")

    def 레버리지(self, 배, posSide=None):
        본 = {"instId": INST, "lever": str(배), "mgnMode": "isolated"}
        if posSide:
            본["posSide"] = posSide
        return self.요청("POST", "/api/v5/account/set-leverage", 본문=본)

    def 시장가롱(self, 계약수, 손절가, posSide=None):
        """손절 주문을 동봉해서만 진입한다(손절 없는 진입 불가)."""
        본 = {"instId": INST, "tdMode": "isolated", "side": "buy", "ordType": "market", "sz": str(계약수),
              "attachAlgoOrds": [{"slTriggerPx": str(손절가), "slOrdPx": "-1", "slTriggerPxType": "last"}]}
        if posSide:
            본["posSide"] = posSide
        return self.요청("POST", "/api/v5/trade/order", 본문=본)

    def 대기손절(self):
        return self.요청("GET", "/api/v5/trade/orders-algo-pending", {"ordType": "conditional", "instType": "SWAP", "instId": INST})

    def 손절올리기(self, 새손절가):
        n = 0
        for a in self.대기손절():
            self.요청("POST", "/api/v5/trade/amend-algos", 본문={"instId": INST, "algoId": a["algoId"], "newSlTriggerPx": str(새손절가), "newSlOrdPx": "-1"})
            n += 1
        return n

    def 전량청산(self, posSide=None):
        본 = {"instId": INST, "mgnMode": "isolated"}
        if posSide:
            본["posSide"] = posSide
        r = self.요청("POST", "/api/v5/trade/close-position", 본문=본)
        try:
            대기 = self.대기손절()
            if 대기:
                self.요청("POST", "/api/v5/trade/cancel-algos", 본문=[{"instId": INST, "algoId": a["algoId"]} for a in 대기])
        except Exception as e:
            print("손절 주문 정리 경고:", e)
        return r
