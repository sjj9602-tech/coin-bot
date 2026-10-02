# -*- coding: utf-8 -*-
"""코인 상시 봇 — Render 백그라운드 워커(또는 PC)에서 24시간 돈다. 폰은 텔레그램으로 알림을 받고 명령한다.

  현물(업비트): BTC 일봉 종가 > EMA100 이면 BTC·ETH 반반 보유, 아니면 현금. 진입마다 손절(+선택 익절·본전 이동)을 봇이 20초마다 감시.
  선물(OKX BTC-USDT 무기한): 종가 > EMA100 «그리고» > EMA50 일 때만 롱(숏 없음, 레버리지 ≤2배, 격리 마진, 손절 주문 동봉).
  모드(환경변수): MODE_SPOT = off|paper|live (기본 paper), MODE_FUT = off|paper|demo|live (기본 paper). 기본은 전부 «모의».
  진짜 주문 잠금: 현물 live → AUTOTRADE_LIVE=YES, 선물 live → AUTOTRADE_LIVE_FUTURES=YES (없으면 paper 로 내려간다).

텔레그램 명령(허가된 TELEGRAM_CHAT_ID 한 곳만): /상태 /신호 /중지 /재개 /청산 → /청산확인 /도움말
안전장치(코드에 강제): 모든 진입에 손절 · 예산 상한 · 손실 한도(현물 25%·선물 15%) 초과 시 전량 청산 후 정지 · 하루 1회 진입 · 손절·익절 후엔 신호가 한 번 꺼졌다 켜질 때까지 재진입 안 함 ·
  열쇠·토큰은 환경변수에만(로그에 안 찍음). ⚠ 연구상 «존버보다 낫다»가 통계로 확인된 신호는 없고(방어형만), 실거래 경로는 아직 실계좌에서 시험되지 않았다 → 모의 → 데모/최소 금액 순서.

    python bot.py          # 상시 실행
    python bot.py --once   # 한 바퀴만(점검용)
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import okx
import rules
import upbit
from tg import 텔레그램

KST = timezone(timedelta(hours=9))
MARKETS = ["KRW-BTC", "KRW-ETH"]
SLIP, FEE, MINORD = 0.0005, 0.0005, 5000
일일시각 = 9 * 60 + 5


def 환경(이름, 기본):
    return os.environ.get(이름, 기본)


def 설정읽기():
    c = dict(
        spot=환경("MODE_SPOT", "paper").lower(), fut=환경("MODE_FUT", "paper").lower(),
        budget_krw=float(환경("BUDGET_KRW", "100000")), budget_usdt=float(환경("BUDGET_USDT", "100")),
        maxloss_spot=float(환경("MAX_LOSS_SPOT", "0.25")), maxloss_fut=float(환경("MAX_LOSS_FUT", "0.15")),
        stop_spot=float(환경("STOP_PCT_SPOT", "8")), stop_fut=float(환경("STOP_PCT_FUT", "6")),
        tp_spot=float(환경("TP_PCT_SPOT", "0")), be_spot=float(환경("BE_PCT_SPOT", "8")), be_fut=float(환경("BE_PCT_FUT", "6")),
        lever=int(환경("LEVERAGE", "1")), data=환경("DATA_DIR", "./data"), loop=int(환경("LOOP_SEC", "20")))
    경고 = []
    if c["lever"] < 1 or c["lever"] > 2:
        경고.append("LEVERAGE 는 1~2 만 허용 → 2 로 제한")
        c["lever"] = max(1, min(2, c["lever"]))
    c["stop_spot"] = min(15.0, max(3.0, c["stop_spot"]))
    c["stop_fut"] = min(c["stop_fut"], 0.6 * 100.0 / c["lever"])
    c["stop_fut"] = max(2.0, c["stop_fut"])
    if c["budget_krw"] < 10000:
        경고.append("BUDGET_KRW 가 너무 작아 10,000원으로 올림")
        c["budget_krw"] = 10000.0
    if c["spot"] == "live" and 환경("AUTOTRADE_LIVE", "") != "YES":
        경고.append("현물 live 잠금(AUTOTRADE_LIVE=YES 없음) → paper 로 실행")
        c["spot"] = "paper"
    if c["fut"] == "live" and 환경("AUTOTRADE_LIVE_FUTURES", "") != "YES":
        경고.append("선물 live 잠금(AUTOTRADE_LIVE_FUTURES=YES 없음) → paper 로 실행")
        c["fut"] = "paper"
    for k in ("spot", "fut"):
        if c[k] not in ("off", "paper", "live", "demo") or (k == "spot" and c[k] == "demo"):
            경고.append("MODE_%s=%s 는 허용되지 않아 paper 로 실행" % (k.upper(), c[k]))
            c[k] = "paper"
    c["경고"] = 경고
    return c


# ───── 상태 저장 ─────
def 상태경로(c):
    os.makedirs(c["data"], exist_ok=True)
    return os.path.join(c["data"], "state.json")


def 상태읽기(c):
    p = 상태경로(c)
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            print("상태 파일을 읽지 못해 새로 시작:", p)
    return {"fresh": True, "paused": False, "confirm_until": 0, "spot": {"pos": {}, "armed": {}, "cash": c["budget_krw"], "init": c["budget_krw"], "invested": 0.0, "returned": 0.0, "last_daily": "", "last_signal": None},
            "fut": {"paper": None, "live": None, "armed": True, "last_daily": "", "last_signal": None, "margin": c["budget_usdt"], "init": c["budget_usdt"]}, "errs": {}}


def 상태저장(c, st):
    p = 상태경로(c)
    json.dump(st, open(p + ".tmp", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(p + ".tmp", p)


def 오류알림(st, tg, 키, e):
    now = time.time()
    if now - st["errs"].get(키, 0) > 1800:
        st["errs"][키] = now
        tg.보내기("⚠ 오류(%s): %s" % (키, repr(e)[:300]))
    print("오류", 키, repr(e)[:300])


def kst분():
    d = datetime.now(KST)
    return d.hour * 60 + d.minute


def 오늘():
    return datetime.now(KST).strftime("%Y-%m-%d")


# ═════════════ 현물 (업비트) ═════════════
def 현물신호():
    c = upbit.마감일봉종가("KRW-BTC", 200)
    if len(c) < 120:
        raise RuntimeError("일봉이 모자람")
    e = upbit.ema(c, 100)
    return c[-1] > e[-1], {"종가": c[-1], "EMA100": round(e[-1], 0), "이격": round((c[-1] / e[-1] - 1) * 100, 2)}


def 현물평가(c, st, 가격):
    s = st["spot"]
    가치 = sum(p["qty"] * 가격.get(m, p["entry"]) for m, p in s["pos"].items())
    if c["spot"] == "paper":
        eq = s["cash"] + 가치
        return eq, eq - s["init"]
    return 가치, 가치 + s["returned"] - s["invested"]          # live: 평가손익 = 보유가치 + 회수 - 투입


def 현물매수(c, st, tg, m, 금액, 가격):
    s = st["spot"]
    if c["spot"] == "paper":
        금액 = min(금액, s["cash"] / (1 + FEE))
        if 금액 < MINORD:
            tg.보내기("[현물 모의] %s 현금 부족으로 매수 건너뜀" % m)
            return
        px = 가격 * (1 + SLIP)
        s["cash"] -= 금액 * (1 + FEE)
        qty = 금액 / px
    else:
        if s["invested"] - s["returned"] + 금액 > c["budget_krw"] * 1.001 or 금액 < MINORD:
            tg.보내기("[현물] 예산 상한/최소 주문 때문에 %s 매수 건너뜀" % m)
            return
        if upbit.원화잔고() < 금액 * (1 + FEE * 1.2):
            tg.보내기("[현물] 원화 잔고 부족으로 %s 매수 건너뜀" % m)
            return
        o = upbit.시장가매수(m, 금액)
        qty, funds, fee = upbit.체결확인(o["uuid"])
        if qty <= 0:
            raise RuntimeError("매수 체결 수량 0: " + m)
        px = funds / qty
        s["invested"] += funds + fee
    stop = rules.손절가(px, c["stop_spot"])
    s["pos"][m] = {"qty": qty, "entry": px, "stop": stop, "be_done": False, "opened": 오늘()}
    tg.보내기("🟢 [현물 %s] %s 매수 %s원 @ %s\n손절 %s · %s" % ("모의" if c["spot"] == "paper" else "실거래", m[4:], format(int(금액), ","), format(int(px), ","),
                                                           format(int(stop), ","), rules.설명(c["stop_spot"], c["tp_spot"], c["be_spot"])))


def 현물매도(c, st, tg, m, 이유, 가격):
    s = st["spot"]
    p = s["pos"].get(m)
    if not p:
        return
    if c["spot"] == "paper":
        px = 가격 * (1 - SLIP)
        받음 = p["qty"] * px * (1 - FEE)
        s["cash"] += 받음
        s["returned"] += 받음
        팔림 = p["qty"]
    else:
        실제 = min(p["qty"], upbit.보유수량(m))
        if 실제 * 가격 < MINORD:
            tg.보내기("[현물] %s 평가액 5,000원 미만이라 팔 수 없음(장부에서 제거)" % m)
            s["pos"].pop(m, None)
            return
        o = upbit.시장가매도(m, 실제)
        팔림, funds, fee = upbit.체결확인(o["uuid"])
        px = funds / 팔림 if 팔림 else 가격
        s["returned"] += funds - fee
    손익 = px / p["entry"] - 1
    p["qty"] -= 팔림
    if p["qty"] * 가격 < MINORD or c["spot"] == "paper":
        s["pos"].pop(m, None)
    if 이유 in ("손절", "익절"):
        s["armed"][m] = False                       # 신호가 한 번 꺼졌다 켜질 때까지 재진입 안 함
    tg.보내기("%s [현물 %s] %s %s @ %s (%+.2f%%)" % ("🔴" if 손익 < 0 else "🔵", "모의" if c["spot"] == "paper" else "실거래", m[4:], 이유, format(int(px), ","), 손익 * 100))


def 현물전량(c, st, tg, 이유):
    if not st["spot"]["pos"]:
        return
    가격 = upbit.현재가(list(st["spot"]["pos"]))
    for m in list(st["spot"]["pos"]):
        현물매도(c, st, tg, m, 이유, 가격[m])


def 현물감시(c, st, tg):
    s = st["spot"]
    if c["spot"] == "off" or not s["pos"]:
        return False
    가격 = upbit.현재가(list(s["pos"]))
    변함 = False
    for m in list(s["pos"]):
        p = s["pos"][m]
        act = rules.점검(p, 가격[m], c["tp_spot"], c["be_spot"])
        if act is None:
            continue
        변함 = True
        if act[0] == "본전이동":
            tg.보내기("🛡 [현물] %s +%.0f%% 도달 → 손절을 본전(%s)으로 올림" % (m[4:], c["be_spot"], format(int(act[1]), ",")))
        else:
            현물매도(c, st, tg, m, act[0], 가격[m])
    _, 손익 = 현물평가(c, st, 가격)
    if -손익 > c["budget_krw"] * c["maxloss_spot"]:
        tg.보내기("⛔ [현물] 손실 한도 초과(%s원 > 예산의 %d%%) → 전량 청산 후 정지" % (format(int(-손익), ","), c["maxloss_spot"] * 100))
        현물전량(c, st, tg, "손실 한도")
        st["paused"] = True
        변함 = True
    return 변함


def 현물일일(c, st, tg):
    s = st["spot"]
    if c["spot"] == "off" or s["last_daily"] == 오늘() or kst분() < 일일시각:
        return False
    on, 설명 = 현물신호()
    s["last_signal"] = {"on": on, **설명, "일": 오늘()}
    줄 = ["📊 [현물 %s] 신호 %s · BTC %s · EMA100 %s (이격 %+.2f%%)" % ("모의" if c["spot"] == "paper" else "실거래", "켜짐(보유)" if on else "꺼짐(현금)", format(int(설명["종가"]), ","), format(int(설명["EMA100"]), ","), 설명["이격"])]
    if not on:
        for m in MARKETS:
            s["armed"][m] = True                      # 신호가 꺼졌으니 다음에 켜지면 다시 진입 가능
        for m in list(s["pos"]):
            가격 = upbit.현재가([m])[m]
            현물매도(c, st, tg, m, "신호 꺼짐", 가격)
    elif not st["paused"]:
        가격 = upbit.현재가(MARKETS)
        for m in MARKETS:
            if m in s["pos"] or not s["armed"].get(m, True):
                continue
            현물매수(c, st, tg, m, c["budget_krw"] / len(MARKETS), 가격[m])
    else:
        줄.append("(중지 상태라 신규 진입 안 함)")
    s["last_daily"] = 오늘()
    tg.보내기("\n".join(줄))
    return True


# ═════════════ 선물 (OKX) ═════════════
def 선물신호():
    c = okx.마감일봉종가()
    if len(c) < 120:
        raise RuntimeError("OKX 일봉이 모자람")
    e100, e50 = upbit.ema(c, 100)[-1], upbit.ema(c, 50)[-1]
    return (c[-1] > e100 and c[-1] > e50), {"종가": c[-1], "EMA100": round(e100, 1), "EMA50": round(e50, 1)}


def 계약수(예산, 배, 가격, ct, lot, minsz):
    n = int(예산 * 배 / (가격 * ct) / lot) * lot
    return round(n, 8) if n >= minsz else 0.0


def 선물일일(c, st, tg):
    f = st["fut"]
    if c["fut"] == "off" or f["last_daily"] == 오늘() or kst분() < 일일시각:
        return False
    on, 설명 = 선물신호()
    f["last_signal"] = {"on": on, **설명, "일": 오늘()}
    모드 = c["fut"]
    줄 = ["📊 [선물 %s] 신호 %s · BTC %.0f USDT · EMA100 %.0f · EMA50 %.0f" % (모드, "롱" if on else "현금", 설명["종가"], 설명["EMA100"], 설명["EMA50"])]
    ct, lot, minsz = okx.상품정보()
    가격 = okx.현재가()
    sl, pct = None, c["stop_fut"]
    if not on:
        f["armed"] = True
    if 모드 == "paper":
        p = f["paper"]
        if not on and p:
            선물모의청산(c, st, tg, 가격, "신호 꺼짐")
        elif on and not p and f["armed"] and not st["paused"]:
            n = 계약수(f["margin"], c["lever"], 가격, ct, lot, minsz)
            if n > 0:
                px = 가격 * (1 + SLIP)
                f["margin"] -= n * ct * px * FEE
                f["paper"] = {"n": n, "entry": px, "stop": rules.손절가(px, pct), "be_done": False, "ct": ct}
                tg.보내기("🟢 [선물 모의] 롱 %.2f계약 @ %.1f · %d배 · 손절 %.1f (-%.1f%%) · %s" % (n, px, c["lever"], f["paper"]["stop"], pct, rules.설명(pct, 0, c["be_fut"])))
    else:
        ex = okx.계정(데모=(모드 == "demo"))
        ps = "long" if ex.포지션모드() == "long_short_mode" else None
        보유 = ex.포지션()
        if not on and 보유:
            ex.전량청산(ps)
            f["live"] = None
            tg.보내기("🔵 [선물 %s] 신호 꺼짐 → 전량 청산" % 모드)
        elif on and not 보유 and f["armed"] and not st["paused"]:
            n = 계약수(c["budget_usdt"], c["lever"], 가격, ct, lot, minsz)
            if n <= 0:
                줄.append("(예산이 최소 계약수에 못 미침)")
            else:
                sl = round(rules.손절가(가격, pct), 1)
                ex.레버리지(c["lever"], ps)
                r = ex.시장가롱(n, sl, ps)
                보유 = ex.포지션()
                px = float(보유[0]["avgPx"]) if 보유 else 가격
                f["live"] = {"n": n, "entry": px, "stop": sl, "be_done": False}
                tg.보내기("🟢 [선물 %s] 롱 %s계약 @ %.1f · %d배 격리 · 손절 %.1f(-%.1f%%, 거래소 동봉) · %s" % (모드, n, px, c["lever"], sl, pct, rules.설명(pct, 0, c["be_fut"])))
    f["last_daily"] = 오늘()
    tg.보내기("\n".join(줄))
    return True


def 선물모의청산(c, st, tg, 가격, 이유):
    f = st["fut"]
    p = f["paper"]
    if not p:
        return
    px = 가격 * (1 - SLIP) if 이유 != "손절" else min(가격, p["stop"])
    손익 = p["n"] * p["ct"] * (px - p["entry"])
    f["margin"] += 손익 - p["n"] * p["ct"] * px * FEE
    f["paper"] = None
    if 이유 in ("손절", "손실 한도"):
        f["armed"] = False
    tg.보내기("%s [선물 모의] %s 청산 @ %.1f (%+.2f USDT, %+.2f%% 가격)" % ("🔴" if 손익 < 0 else "🔵", 이유, px, 손익, (px / p["entry"] - 1) * 100))


def 선물감시(c, st, tg, 상태={"last": 0}):
    f = st["fut"]
    if c["fut"] == "off":
        return False
    모드 = c["fut"]
    변함 = False
    if 모드 == "paper":
        p = f["paper"]
        if not p:
            return False
        가격 = okx.현재가()
        if 가격 <= p["stop"]:
            선물모의청산(c, st, tg, 가격, "손절")
            return True
        새 = rules.본전만(p, 가격, c["be_fut"])
        if 새:
            tg.보내기("🛡 [선물 모의] +%.0f%% 도달 → 손절을 본전(%.1f)으로 올림" % (c["be_fut"], 새))
            변함 = True
        미실현 = p["n"] * p["ct"] * (가격 - p["entry"])
        if -미실현 > c["budget_usdt"] * c["maxloss_fut"]:
            tg.보내기("⛔ [선물 모의] 손실 한도 초과 → 청산 후 정지")
            선물모의청산(c, st, tg, 가격, "손실 한도")
            st["paused"] = True
            변함 = True
        return 변함
    # 데모·실거래: 거래소가 손절을 들고 있다. 60초마다 포지션 확인·본전 이동·손실 한도.
    if time.time() - 상태["last"] < 60:
        return False
    상태["last"] = time.time()
    ex = okx.계정(데모=(모드 == "demo"))
    보유 = ex.포지션()
    lv = f["live"]
    if lv and not 보유:
        tg.보내기("🔴 [선물 %s] 포지션이 사라짐(거래소 손절 체결 또는 수동 청산) — 진입 %.1f 손절 %.1f. 신호가 꺼졌다 켜질 때까지 재진입 안 함" % (모드, lv["entry"], lv["stop"]))
        f["live"] = None
        f["armed"] = False
        return True
    if lv and 보유:
        가격 = okx.현재가()
        새 = rules.본전만(lv, 가격, c["be_fut"])
        if 새:
            n = ex.손절올리기(round(새, 1))
            tg.보내기("🛡 [선물 %s] +%.0f%% 도달 → 손절을 본전(%.1f)으로 올림(%d건)" % (모드, c["be_fut"], 새, n))
            변함 = True
        미실현 = sum(float(x.get("upl") or 0) for x in 보유)
        if -미실현 > c["budget_usdt"] * c["maxloss_fut"]:
            tg.보내기("⛔ [선물 %s] 손실 한도 초과(%.2f USDT) → 전량 청산 후 정지" % (모드, -미실현))
            ps = "long" if ex.포지션모드() == "long_short_mode" else None
            ex.전량청산(ps)
            f["live"] = None
            st["paused"] = True
            변함 = True
    return 변함


def 선물전량(c, st, tg, 이유):
    f = st["fut"]
    if c["fut"] == "off":
        return
    if c["fut"] == "paper":
        if f["paper"]:
            선물모의청산(c, st, tg, okx.현재가(), 이유)
        return
    ex = okx.계정(데모=(c["fut"] == "demo"))
    if ex.포지션():
        ps = "long" if ex.포지션모드() == "long_short_mode" else None
        ex.전량청산(ps)
        tg.보내기("🔵 [선물 %s] %s → 전량 청산" % (c["fut"], 이유))
    f["live"] = None


# ═════════════ 텔레그램 명령 ═════════════
def 상태글(c, st):
    줄 = ["봇 상태 · %s%s" % (오늘(), " · ⏸ 중지 중(신규 진입 안 함, 손절 감시는 계속)" if st["paused"] else "")]
    s = st["spot"]
    if c["spot"] != "off":
        try:
            가격 = upbit.현재가(MARKETS)
            eq, 손익 = 현물평가(c, st, 가격)
        except Exception:
            가격, eq, 손익 = {}, 0, 0
        줄.append("[현물 %s] 예산 %s원 · 평가손익 %s원" % ("모의" if c["spot"] == "paper" else "실거래", format(int(c["budget_krw"]), ","), format(int(손익), ",")))
        for m, p in s["pos"].items():
            px = 가격.get(m, p["entry"])
            줄.append("  %s %.6f개 · 진입 %s · 현재 %s (%+.2f%%) · 손절 %s%s" % (m[4:], p["qty"], format(int(p["entry"]), ","), format(int(px), ","), (px / p["entry"] - 1) * 100, format(int(p["stop"]), ","), " (본전 이동됨)" if p["be_done"] else ""))
        if not s["pos"]:
            줄.append("  보유 없음")
        if s["last_signal"]:
            줄.append("  마지막 신호(%s): %s" % (s["last_signal"]["일"], "보유" if s["last_signal"]["on"] else "현금"))
    f = st["fut"]
    if c["fut"] != "off":
        pos = f["paper"] if c["fut"] == "paper" else f["live"]
        줄.append("[선물 %s] 레버 %d배 · 증거금 예산 %s USDT" % (c["fut"], c["lever"], c["budget_usdt"]))
        if pos:
            줄.append("  롱 %s계약 · 진입 %.1f · 손절 %.1f%s" % (pos.get("n"), pos["entry"], pos["stop"], " (본전 이동됨)" if pos["be_done"] else ""))
        else:
            줄.append("  포지션 없음")
        if f["last_signal"]:
            줄.append("  마지막 신호(%s): %s" % (f["last_signal"]["일"], "롱" if f["last_signal"]["on"] else "현금"))
    줄.append("규칙: 현물 " + rules.설명(c["stop_spot"], c["tp_spot"], c["be_spot"]))
    return "\n".join(줄)


def 명령처리(c, st, tg, 글):
    cmd = 글.split()[0].split("@")[0].lower()
    if cmd in ("/상태", "/status", "/start"):
        tg.보내기(상태글(c, st))
    elif cmd in ("/신호", "/signal"):
        try:
            a = 현물신호()
            b = 선물신호()
            tg.보내기("현물 신호: %s (BTC %s, EMA100 %s)\n선물 신호: %s (BTC %.0f USDT)" % ("보유" if a[0] else "현금", format(int(a[1]["종가"]), ","), format(int(a[1]["EMA100"]), ","), "롱" if b[0] else "현금", b[1]["종가"]))
        except Exception as e:
            tg.보내기("신호 조회 실패: " + repr(e)[:200])
    elif cmd in ("/중지", "/stop", "/pause"):
        st["paused"] = True
        tg.보내기("⏸ 신규 진입을 중지했습니다. 보유분의 손절·본전 이동 감시와 신호 꺼짐 청산은 계속됩니다. 재개: /재개")
    elif cmd in ("/재개", "/resume"):
        st["paused"] = False
        tg.보내기("▶ 재개했습니다(다음 신호 때부터 진입).")
    elif cmd in ("/청산", "/panic"):
        st["confirm_until"] = time.time() + 60
        tg.보내기("⚠ 봇이 가진 현물·선물 포지션을 전부 시장가로 청산하고 정지합니다. 60초 안에 /청산확인 을 보내세요.")
    elif cmd in ("/청산확인", "/confirm"):
        if time.time() > st["confirm_until"]:
            tg.보내기("확인 시간이 지났습니다. 다시 /청산 부터.")
            return
        st["confirm_until"] = 0
        tg.보내기("청산을 시작합니다…")
        for 일, 이름 in ((lambda: 현물전량(c, st, tg, "긴급 청산"), "현물"), (lambda: 선물전량(c, st, tg, "긴급 청산"), "선물")):
            try:
                일()
            except Exception as e:
                tg.보내기("⚠ %s 청산 중 오류: %s (거래소 앱에서 직접 확인하세요)" % (이름, repr(e)[:200]))
        st["paused"] = True
        tg.보내기("정지 상태입니다. 재개: /재개")
    else:
        tg.보내기("명령: /상태 /신호 /중지 /재개 /청산 → /청산확인")


# ═════════════ 메인 ═════════════
def 한바퀴(c, st, tg):
    for 글 in tg.명령들():
        try:
            명령처리(c, st, tg, 글)
        except Exception as e:
            오류알림(st, tg, "명령", e)
    for 이름, 일 in (("현물감시", 현물감시), ("선물감시", 선물감시), ("현물일일", 현물일일), ("선물일일", 선물일일)):
        try:
            일(c, st, tg)
        except Exception as e:
            오류알림(st, tg, 이름, e)


def 건강확인서버():
    """환경변수 PORT 가 있으면(Render Web Service) 간단한 HTTP 응답을 열어 둔다. 백그라운드 워커로 돌리면 필요 없다."""
    port = 환경("PORT", "")
    if not port:
        return
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *a):
            pass
    threading.Thread(target=HTTPServer(("0.0.0.0", int(port)), H).serve_forever, daemon=True).start()


def main():
    건강확인서버()
    c = 설정읽기()
    st = 상태읽기(c)
    tg = 텔레그램()
    once = "--once" in sys.argv
    tg.보내기("🤖 봇 시작 · 현물 %s · 선물 %s · 레버 %d배 · 예산 %s원/%s USDT%s\n%s" % (
        c["spot"], c["fut"], c["lever"], format(int(c["budget_krw"]), ","), c["budget_usdt"], " · 텔레그램 꺼짐(토큰/채팅 ID 없음)" if not tg.켜짐 else "",
        "\n".join("⚠ " + w for w in c["경고"]) or "명령: /상태 /신호 /중지 /재개 /청산"))
    if st.pop("fresh", False):
        tg.보내기("ℹ 상태 파일이 없어 새로 시작합니다. (Render 에 디스크가 없으면 재시작·재배포 때마다 이렇게 초기화되어 보유 장부·손절 감시가 사라집니다 → 실거래 전에 디스크 필수)")
    while True:
        한바퀴(c, st, tg)
        상태저장(c, st)
        if once:
            break
        time.sleep(c["loop"])


if __name__ == "__main__":
    main()
