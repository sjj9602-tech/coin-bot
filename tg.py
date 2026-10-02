# -*- coding: utf-8 -*-
"""텔레그램 봇 — 알림 보내기 + 명령 받기. 허가된 채팅(TELEGRAM_CHAT_ID) 한 곳의 명령만 받는다. 토큰은 환경변수로만."""
import json
import os
import urllib.parse
import urllib.request


class 텔레그램:
    def __init__(self):
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat = str(os.environ.get("TELEGRAM_CHAT_ID", "")).strip()
        self.offset = None
        self.켜짐 = bool(self.token and self.chat)
        self.경고한것 = set()
        if self.켜짐:
            try:                                  # 시작 전에 쌓인 옛 명령(예: 어제의 /청산확인)은 버린다
                r = self._호출("getUpdates", {"offset": -1, "timeout": 0})
                if r:
                    self.offset = r[-1]["update_id"] + 1
            except Exception as e:
                print("텔레그램 초기화 경고:", repr(e)[:100])

    def _호출(self, 방법, 값):
        url = "https://api.telegram.org/bot%s/%s" % (self.token, 방법)
        req = urllib.request.Request(url, data=urllib.parse.urlencode(값).encode(), method="POST")
        with urllib.request.urlopen(req, timeout=15) as r:
            j = json.loads(r.read().decode())
        if not j.get("ok"):
            raise RuntimeError("텔레그램 오류 " + str(j)[:150])
        return j["result"]

    def 보내기(self, 글):
        print("[알림]", 글.replace("\n", " | ")[:300])
        if not self.켜짐:
            return
        try:
            self._호출("sendMessage", {"chat_id": self.chat, "text": 글[:3800]})
        except Exception as e:
            print("텔레그램 전송 실패:", repr(e)[:100])

    def 명령들(self):
        """허가된 채팅에서 온 새 명령(문자열 목록)."""
        if not self.켜짐:
            return []
        값 = {"timeout": 0}
        if self.offset is not None:
            값["offset"] = self.offset
        try:
            업 = self._호출("getUpdates", 값)
        except Exception as e:
            print("텔레그램 수신 실패:", repr(e)[:100])
            return []
        out = []
        for u in 업:
            self.offset = u["update_id"] + 1
            m = u.get("message") or {}
            채팅 = str((m.get("chat") or {}).get("id", ""))
            글 = (m.get("text") or "").strip()
            if not 글:
                continue
            if 채팅 != self.chat:
                if 채팅 not in self.경고한것:        # 모르는 사람의 명령은 무시(한 번만 기록)
                    self.경고한것.add(채팅)
                    print("허가되지 않은 채팅 무시:", 채팅)
                continue
            out.append(글)
        return out
