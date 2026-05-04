import time
from signal_engine import stock_signal
from router import Router
import requests
import json
import os
from dotenv import load_dotenv


load_dotenv()

WEBHOOK = os.getenv("SLACK_WEBHOOK")
def send_slack(msg):

    if not WEBHOOK:

        print("❌ WEBHOOK not set")

        return

    resp = requests.post(WEBHOOK, json={"text": msg})

    print("SLACK STATUS:", resp.status_code)

    print("SLACK RESPONSE:", resp.text)
    

router = Router(slack_fn=send_slack)


def load_watchlist():
    if os.path.exists("watchlist_stock.json"):
        data = json.load(open("watchlist_stock.json"))
        return data.get("symbols", [])
    return []


def run():

    print("🚀 SYSTEM STARTED")

    while True:

        symbols = load_watchlist()

        print("WATCHLIST:", symbols)

        if not symbols:
            print("❌ EMPTY WATCHLIST → EXIT PREVENTED")
            time.sleep(5)
            continue

        for s in symbols:

            print("CHECK:", s)

            sig = stock_signal(s)

            print("SIGNAL RAW:", sig)

            router.route(s, sig)

        print("🔁 LOOP END\n")
        time.sleep(10)


if __name__ == "__main__":
    run()