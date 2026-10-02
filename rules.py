# -*- coding: utf-8 -*-
"""청산 규칙 — 진입 뒤 손절·익절·본전 이동을 어디에 둘지 (연구 결과 `자동매매\결과\청산규칙_*.md` 기반 기본값).

연구(51코인·5년·추세 진입 기준)에서 나온 것:
  · 손절 8~12% 고정은 무손절과 수익이 비슷하고 낙폭이 -45% → -39~-41% 로 소폭 줄었다.
  · 고정 익절 목표(+10~20%)는 큰 추세를 일찍 놓쳐 연수익이 0~1% 로 무너졌다 → 기본은 «익절 목표 없음».
  · ATR 트레일링 2~4배는 코인 변동성에 너무 자주 털려 -7~+7%/년 → 쓰지 않는다.
  · 손절 -8% 에서 +8% 닿으면 손절을 본전으로 올리기: 수익 비슷(+13%)·낙폭 -34% → 기본 켬.
  · 신호가 꺼지면 청산(추세 이탈)이 기본 출구.
따라서 기본값: 손절 8%(현물)/6%(선물 2배), 익절 없음, +8%(선물은 +6%)에서 본전 이동. 모두 환경변수로 바꿀 수 있다.
"""
BE_BUFFER = 1.002          # 본전 이동 시 수수료를 덮을 만큼 살짝 위


def 손절가(진입가, 손절pct):
    return 진입가 * (1 - 손절pct / 100.0)


def 점검(pos, 가격, 익절pct=0.0, 본전pct=0.0):
    """pos = {entry, stop, be_done}. 가격은 현재가. 반환: None | ("손절", 가격) | ("익절", 가격) | ("본전이동", 새손절가).
    '본전이동'은 pos 를 직접 갱신한다(be_done=True, stop 상승)."""
    if 가격 <= pos["stop"]:
        return ("손절", 가격)
    if 익절pct and 가격 >= pos["entry"] * (1 + 익절pct / 100.0):
        return ("익절", 가격)
    if 본전pct and not pos.get("be_done") and 가격 >= pos["entry"] * (1 + 본전pct / 100.0):
        새 = max(pos["stop"], pos["entry"] * BE_BUFFER)
        pos["be_done"] = True
        pos["stop"] = 새
        return ("본전이동", 새)
    return None


def 본전만(pos, 가격, 본전pct):
    """손절은 거래소가 처리하는 선물용: 본전 이동 조건만 본다. 조건이 되면 새 손절가를 돌려주고 pos 를 갱신."""
    if 본전pct and not pos.get("be_done") and 가격 >= pos["entry"] * (1 + 본전pct / 100.0):
        새 = max(pos["stop"], pos["entry"] * BE_BUFFER)
        pos["be_done"] = True
        pos["stop"] = 새
        return 새
    return None


def 설명(손절pct, 익절pct, 본전pct):
    s = "손절 -%.1f%%" % 손절pct
    s += " · 익절 +%.0f%%" % 익절pct if 익절pct else " · 익절 목표 없음(추세 청산)"
    s += " · +%.0f%% 에서 본전 이동" % 본전pct if 본전pct else " · 본전 이동 끔"
    return s
