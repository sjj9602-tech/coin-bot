# -*- coding: utf-8 -*-
"""현물 거래소 어댑터 — OKX(기본, 선물과 같은 거래소·같은 키)와 업비트(선택). 봇은 이 인터페이스만 쓴다.

공통 인터페이스: 이름, 통화, 시장들, 수수료, 최소주문, 기호(m), 표시(x), 신호(), 가격(시장들), 매수(m, 금액)->(수량, 평균가, 쓴돈),
               매도(m, 수량)->(팔린수량, 평균가, 받은돈), 보유수량(m), 잔고충분(금액).
"""
import math

import okx
import upbit


def ema(값들, n):
    a, o = 2.0 / (n + 1), []
    for i, v in enumerate(값들):
        o.append(v if i == 0 else a * v + (1 - a) * o[-1])
    return o


def _신호(종가들):
    if len(종가들) < 120:
        raise RuntimeError("일봉이 모자람")
    e = ema(종가들, 100)
    return 종가들[-1] > e[-1], {"종가": 종가들[-1], "EMA100": round(e[-1], 2 if 종가들[-1] < 1000 else 0), "이격": round((종가들[-1] / e[-1] - 1) * 100, 2)}


class OKX현물:
    이름, 통화, 수수료, 최소주문 = "OKX", "USDT", 0.001, 5.0
    시장들 = ["BTC-USDT", "ETH-USDT"]

    def __init__(self, 데모=False):
        self.데모 = 데모
        self._계정 = None
        self._정보 = {}

    def 계정(self):
        if self._계정 is None:
            self._계정 = okx.계정(데모=self.데모)
        return self._계정

    def 기호(self, m):
        return m.split("-")[0]

    def 표시(self, x):
        return "%.2f USDT" % x

    def 신호(self):
        return _신호(okx.일봉종가("BTC-USDT"))

    def 가격(self, 시장들):
        return {m: okx.종목가격(m) for m in 시장들}

    def _단위(self, m):
        if m not in self._정보:
            self._정보[m] = okx.현물정보(m)
        return self._정보[m]

    def 매수(self, m, 금액):
        ex = self.계정()
        oid = ex.현물시장가매수(m, 금액)
        수량, 평균가, 수수료, 수수료통화 = ex.체결확인(m, oid)
        if 수량 <= 0:
            raise RuntimeError("OKX 매수 체결 수량 0: " + m)
        순수량 = 수량 + (수수료 if 수수료통화 == m.split("-")[0] else 0.0)       # 현물 매수 수수료는 받은 코인에서 빠진다(음수)
        쓴돈 = 수량 * 평균가 - (수수료 if 수수료통화 == "USDT" else 0.0)
        return 순수량, 평균가, 쓴돈

    def 매도(self, m, 수량):
        ex = self.계정()
        최소, 단위 = self._단위(m)
        수량 = math.floor(수량 / 단위 + 1e-9) * 단위
        if 수량 < 최소:
            raise RuntimeError("OKX 최소 주문 수량(%s) 미만: %s" % (최소, 수량))
        oid = ex.현물시장가매도(m, 수량)
        팔림, 평균가, 수수료, 수수료통화 = ex.체결확인(m, oid)
        받은돈 = 팔림 * 평균가 + (수수료 if 수수료통화 == "USDT" else 0.0)
        return 팔림, 평균가, 받은돈

    def 보유수량(self, m):
        return self.계정().가용(m.split("-")[0])

    def 잔고충분(self, 금액):
        return self.계정().가용("USDT") >= 금액 * 1.002


class 업비트현물:
    이름, 통화, 수수료, 최소주문 = "업비트", "원", 0.0005, 5000.0
    시장들 = ["KRW-BTC", "KRW-ETH"]

    def 기호(self, m):
        return m[4:]

    def 표시(self, x):
        return format(int(x), ",") + "원"

    def 신호(self):
        return _신호(upbit.마감일봉종가("KRW-BTC", 200))

    def 가격(self, 시장들):
        return upbit.현재가(시장들)

    def 매수(self, m, 금액):
        o = upbit.시장가매수(m, 금액)
        수량, 체결금액, 수수료 = upbit.체결확인(o["uuid"])
        if 수량 <= 0:
            raise RuntimeError("업비트 매수 체결 수량 0: " + m)
        return 수량, 체결금액 / 수량, 체결금액 + 수수료

    def 매도(self, m, 수량):
        o = upbit.시장가매도(m, 수량)
        팔림, 체결금액, 수수료 = upbit.체결확인(o["uuid"])
        return 팔림, (체결금액 / 팔림 if 팔림 else 0.0), 체결금액 - 수수료

    def 보유수량(self, m):
        return upbit.보유수량(m)

    def 잔고충분(self, 금액):
        return upbit.원화잔고() >= 금액 * 1.0006


def 만들기(거래소, 모드):
    if 거래소 == "upbit":
        return 업비트현물()
    return OKX현물(데모=(모드 == "demo"))
