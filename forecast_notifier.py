"""Send a Reno NWS soaring forecast when a new publication appears."""

from __future__ import annotations

import argparse
import html
import json
import logging
import os
import re
import smtplib
import time
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

PRODUCT_URL = "https://forecast.weather.gov/product.php?site=REV&issuedby=REV&product=SRG"
DEFAULT_RECIPIENT = "krish.28.naidu@gmail.com"
USER_AGENT = "reno-forecast-notifier/1.0 contact=krish.28.naidu@gmail.com"
PUBLICATION_PATTERN = re.compile(r"(UXUS97\s+KREV\s+\d{6})")
FORECAST_DATE_PATTERN = re.compile(r"\b(?:MON|TUE|WED|THU|FRI|SAT|SUN)\s+([A-Z]{3})\s+(\d{1,2})\s+(\d{4})\b")
RENO_TIME_ZONE = ZoneInfo("America/Los_Angeles")


def get_config() -> dict[str, Any]:
    return {
        "recipient": os.getenv("FORECAST_RECIPIENT", DEFAULT_RECIPIENT),
        "poll_seconds": int(os.getenv("POLL_SECONDS", "300")),
        "state_file": Path(os.getenv("STATE_FILE", "forecast_state.json")),
        "send_hour": int(os.getenv("SEND_HOUR", "7")),
    }


def fetch_forecast() -> tuple[str, str]:
    request = Request(PRODUCT_URL, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        page = response.read().decode("utf-8", errors="replace")

    pre_match = re.search(r"<pre[^>]*>([\s\S]*?)</pre>", page, flags=re.I)
    if pre_match:
        text = html.unescape(pre_match.group(1)).replace("\r\n", "\n").strip()
    else:
        text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", page, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()

    match = PUBLICATION_PATTERN.search(text)
    if not match:
        raise RuntimeError("Could not find the expected SRGREV publication header")

    publication_id = match.group(1).replace("  ", " ")
    marker = text.find(publication_id)
    forecast = text[marker:].strip()
    return publication_id, forecast


def find_value(forecast: str, pattern: str) -> str:
    match = re.search(pattern, forecast, flags=re.I | re.M)
    return match.group(1).strip() if match else "Not available"


def forecast_date(forecast: str) -> str | None:
    match = FORECAST_DATE_PATTERN.search(forecast)
    if not match:
        return None
    month, day, year = match.groups()
    return datetime.strptime(f"{month} {day} {year}", "%b %d %Y").date().isoformat()


def format_forecast_html(publication_id: str, forecast: str) -> str:
    max_temp = find_value(forecast, r"FORECASTED MAX\s+TEMP AT RENO \(DEG F\)\.*\s+(\d+)\s+")
    trigger_temp = find_value(forecast, r"FORECASTED TRIGGER TEMPERATURE \(DEG F\)\.+\s+(\d+)")
    max_altitude = find_value(forecast, r"FORECASTED MAXIMUM\s+ALTITUDE \(FT MSL\)\.+\s+(\d+)")
    soaring_index = find_value(forecast, r"FORECASTED SOARING INDEX \(FPM\)\.+\s+(\d+)")
    k_index_18z = find_value(forecast, r"FORECASTED K-INDEX\.+VALID 18Z\.+\s+(-?\d+)")
    lifted_index_18z = find_value(forecast, r"FORECASTED LIFTED INDEX\.+VALID 18Z\.+\s+(-?\d+)")
    body = html.escape(forecast)
    cards = "".join(
        f'<td style="padding:10px;border:1px solid #d9e2ec;background:#f7fafc;">'
        f'<div style="font-size:12px;color:#52606d;">{label}</div>'
        f'<div style="font-size:22px;font-weight:700;color:#102a43;">{value}</div></td>'
        for label, value in (
            ("Max temp (F)", max_temp),
            ("Trigger temp (F)", trigger_temp),
            ("Max altitude (ft)", max_altitude),
            ("Soaring index (FPM)", soaring_index),
            ("K-index at 18Z", k_index_18z),
            ("Lifted index at 18Z", lifted_index_18z),
        )
    )
    return (
        '<div style="font-family:Arial,sans-serif;color:#243b53;max-width:760px;">'
        '<h2 style="color:#102a43;margin-bottom:4px;">Reno Soaring Forecast</h2>'
        f'<p style="color:#52606d;margin-top:0;">Publication: {html.escape(publication_id)}</p>'
        '<h3 style="color:#102a43;border-bottom:2px solid #2f80ed;padding-bottom:6px;">Today at a glance</h3>'
        f'<table role="presentation" style="border-collapse:collapse;width:100%;"><tr>{cards}</tr></table>'
        '<h3 style="color:#102a43;border-bottom:2px solid #2f80ed;padding-bottom:6px;margin-top:24px;">Full forecast</h3>'
        f'<pre style="white-space:pre-wrap;font:13px/1.45 Consolas,monospace;background:#f7fafc;padding:16px;border:1px solid #d9e2ec;">{body}</pre>'
        '</div>'
    )


def load_state(path: Path) -> dict[str, str] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def save_state(path: Path, publication_id: str, sent_date: str) -> None:
    path.write_text(
        json.dumps({"publication_id": publication_id, "sent_date": sent_date}, indent=2) + "\n",
        encoding="utf-8",
    )


def send_email(recipient: str, publication_id: str, forecast: str) -> None:
    provider = os.getenv("EMAIL_PROVIDER", "smtp").lower()
    if provider == "brevo":
        send_brevo_email(recipient, publication_id, forecast)
        return
    if provider == "resend":
        send_resend_email(recipient, publication_id, forecast)
        return

    host = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.environ["SMTP_USERNAME"]
    password = os.environ["SMTP_PASSWORD"]
    sender = os.getenv("SMTP_FROM", username)

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = f"New Reno soaring forecast: {publication_id}"
    message.set_content(f"A new NWS Reno soaring forecast was published.\n\n{forecast}\n")
    message.add_alternative(format_forecast_html(publication_id, forecast), subtype="html")

    with smtplib.SMTP(host, port, timeout=30) as server:
        server.starttls()
        server.login(username, password)
        server.send_message(message)


def send_brevo_email(recipient: str, publication_id: str, forecast: str) -> None:
    payload = json.dumps(
        {
            "sender": {"email": os.environ["EMAIL_FROM"]},
            "to": [{"email": recipient}],
            "subject": f"New Reno soaring forecast: {publication_id}",
            "textContent": f"A new NWS Reno soaring forecast was published.\n\n{forecast}\n",
            "htmlContent": format_forecast_html(publication_id, forecast),
        }
    ).encode("utf-8")
    request = Request(
        "https://api.brevo.com/v3/smtp/email",
        data=payload,
        headers={
            "api-key": os.environ["BREVO_API_KEY"],
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        if response.status >= 300:
            raise RuntimeError(f"Brevo returned HTTP {response.status}")


def send_resend_email(recipient: str, publication_id: str, forecast: str) -> None:
    payload = json.dumps(
        {
            "from": os.environ["EMAIL_FROM"],
            "to": [recipient],
            "subject": f"New Reno soaring forecast: {publication_id}",
            "text": f"A new NWS Reno soaring forecast was published.\n\n{forecast}\n",
        }
    ).encode("utf-8")
    request = Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {os.environ['RESEND_API_KEY']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        if response.status >= 300:
            raise RuntimeError(f"Resend returned HTTP {response.status}")


def send_whatsapp(recipient: str, publication_id: str, forecast: str) -> None:
    from twilio.rest import Client

    client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
    body = f"New NWS Reno soaring forecast ({publication_id}):\n\n{forecast}"
    client.messages.create(
        body=body[:1600],
        from_=os.environ["TWILIO_WHATSAPP_FROM"],
        to=os.environ.get("TWILIO_WHATSAPP_TO", recipient),
    )


def notify(config: dict[str, Any], dry_run: bool = False) -> bool:
    publication_id, forecast = fetch_forecast()
    now = datetime.now(RENO_TIME_ZONE)
    today = now.date().isoformat()
    state = load_state(config["state_file"]) or {}
    if now.hour < config["send_hour"]:
        logging.info("Waiting until %02d:00 Reno time", config["send_hour"])
        return False
    if forecast_date(forecast) != today:
        logging.info("NWS has not published today's forecast yet; latest report date is %s", forecast_date(forecast))
        return False
    if state.get("sent_date") == today:
        logging.info("Already sent today's forecast; latest publication is %s", publication_id)
        return False

    if dry_run:
        logging.info("Dry run: would notify for %s", publication_id)
        print(forecast)
        return True

    if os.getenv("EMAIL_ENABLED", "true").lower() == "true":
        send_email(config["recipient"], publication_id, forecast)
    if os.getenv("WHATSAPP_ENABLED", "false").lower() == "true":
        send_whatsapp(config["recipient"], publication_id, forecast)

    save_state(config["state_file"], publication_id, today)
    logging.info("Sent new forecast notification for %s", publication_id)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="check once and exit")
    parser.add_argument("--dry-run", action="store_true", help="fetch and print without sending or saving state")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = get_config()

    while True:
        try:
            notify(config, dry_run=args.dry_run)
        except Exception:
            logging.exception("Forecast check failed")
            if args.once:
                raise SystemExit(1)
        if args.once:
            return
        time.sleep(config["poll_seconds"])


if __name__ == "__main__":
    main()
