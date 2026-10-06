import os, re, time, threading, logging
from http.server import BaseHTTPRequestHandler, HTTPServer
import requests

GOLDEN_KEY = os.environ["FUNPAY_GOLDEN_KEY"]
GAME_ID = os.getenv("GAME_ID", "81")
NODE_ID = os.getenv("NODE_ID", "223")
INTERVAL = int(float(os.getenv("INTERVAL_HOURS", "4.5")) * 3600)

BASE = "https://funpay.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("raiser")


def parse_wait(text):
    """Достаёт время ожидания из ответа вида 'Подождите 3 часа' / '45 минут'."""
    secs = 0
    h = re.search(r"(\d+)\s*(?:час|ч\b)", text)
    m = re.search(r"(\d+)\s*мин", text)
    if h:
        secs += int(h.group(1)) * 3600
    if m:
        secs += int(m.group(1)) * 60
    return secs or None


def raise_lots():
    s = requests.Session()
    s.headers["User-Agent"] = UA
    s.cookies.set("golden_key", GOLDEN_KEY, domain="funpay.com")

    page = s.get(f"{BASE}/lots/{NODE_ID}/trade", timeout=30)
    page.raise_for_status()

    if "js-lot-raise" not in page.text:
        raise RuntimeError("Кнопки нет: golden_key протух или FunPay отдал капчу")

    csrf = re.search(r"csrf-token&quot;:&quot;([^&]+)&quot;", page.text)
    data = {"game_id": GAME_ID, "node_id": NODE_ID}
    if csrf:
        data["csrf_token"] = csrf.group(1)

    r = s.post(
        f"{BASE}/lots/raise",
        data=data,
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{BASE}/lots/{NODE_ID}/trade",
            "Origin": BASE,
        },
        timeout=30,
    )
    log.info("HTTP %s: %s", r.status_code, r.text[:300])

    try:
        msg = r.json().get("msg", "") or ""
    except ValueError:
        msg = r.text
    return msg


def worker():
    while True:
        delay = INTERVAL
        try:
            msg = raise_lots()
            wait = parse_wait(msg) if "дождит" in msg else None
            if wait:
                delay = wait + 60
                log.info("Кулдаун, следующая попытка через %d мин", delay // 60)
            else:
                log.info("Поднято. Следующий запуск через %.1f ч", delay / 3600)
        except Exception as e:
            delay = 600
            log.error("Ошибка: %s. Повтор через 10 мин", e)
        time.sleep(delay)


class Ping(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    threading.Thread(target=worker, daemon=True).start()
    port = int(os.getenv("PORT", "10000"))
    HTTPServer(("0.0.0.0", port), Ping).serve_forever()
