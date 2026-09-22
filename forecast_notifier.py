"""Send a Reno NWS soaring forecast when a new publication appears."""

from __future__ import annotations

import argparse
import base64
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


def find_pair(forecast: str, pattern: str) -> tuple[str, str]:
    """Return (today, yesterday) from a row that has both columns."""
    match = re.search(pattern, forecast, flags=re.I | re.M)
    if not match:
        return "Not available", "Not available"
    return match.group(1).strip(), match.group(2).strip()


def forecast_date(forecast: str) -> str | None:
    match = FORECAST_DATE_PATTERN.search(forecast)
    if not match:
        return None
    month, day, year = match.groups()
    return datetime.strptime(f"{month} {day} {year}", "%b %d %Y").date().isoformat()


def format_forecast_html(publication_id: str, forecast: str) -> str:
    max_temp = find_pair(forecast, r"FORECASTED MAX\s+TEMP AT RENO \(DEG F\)\.*\s+(-?\d+)\s+(-?\d+)")
    trigger_temp = find_pair(forecast, r"FORECASTED TRIGGER TEMPERATURE \(DEG F\)\.+\s+(-?\d+)\s+(-?\d+)")
    max_altitude = find_pair(forecast, r"FORECASTED MAXIMUM\s+ALTITUDE \(FT MSL\)\.+\s+(-?\d+)\s+(-?\d+)")
    soaring_index = find_pair(forecast, r"FORECASTED SOARING INDEX \(FPM\)\.+\s+(-?\d+)\s+(-?\d+)")
    k_index_18z = find_pair(forecast, r"FORECASTED K-INDEX\.+VALID 18Z\.+\s+(-?\d+)\s+(-?\d+)")
    lifted_index_18z = find_pair(forecast, r"FORECASTED LIFTED INDEX\.+VALID 18Z\.+\s+(-?\d+)\s+(-?\d+)")
    body = html.escape(forecast)
    cards = "".join(
        f'<div class="card" style="display:inline-block;width:31%;box-sizing:border-box;'
        f'padding:10px;border:1px solid #d9e2ec;background:#f7fafc;margin:0 1% 8px 0;vertical-align:top;">'
        f'<div style="font-size:12px;color:#52606d;">{label}</div>'
        f'<div style="font-size:20px;font-weight:700;color:#102a43;">{today}'
        f'<span style="font-size:12px;font-weight:400;color:#829ab1;"> yest {yesterday}</span></div></div>'
        for label, (today, yesterday) in (
            ("Max temp (F)", max_temp),
            ("Trigger temp (F)", trigger_temp),
            ("Max altitude (ft)", max_altitude),
            ("Soaring index (FPM)", soaring_index),
            ("K-index at 18Z", k_index_18z),
            ("Lifted index at 18Z", lifted_index_18z),
        )
    )
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<style>'
        ".forecast-pre{white-space:pre;overflow-x:auto;-webkit-overflow-scrolling:touch;"
        "font:12px/1.4 Consolas,'Courier New',monospace;background:#f7fafc;padding:12px;"
        "border:1px solid #d9e2ec;}"
        "@media only screen and (max-width:600px){"
        ".card{display:block !important;width:100% !important;margin:0 0 8px 0 !important;}"
        ".forecast-pre{font-size:11px;}"
        "}"
        '</style></head><body style="margin:0;padding:0;">'
        '<div style="font-family:Arial,sans-serif;color:#243b53;max-width:760px;padding:12px;">'
        '<h2 style="color:#102a43;margin-bottom:4px;">Reno Soaring Forecast</h2>'
        f'<p style="color:#52606d;margin-top:0;">Publication: {html.escape(publication_id)}</p>'
        '<h3 style="color:#102a43;border-bottom:2px solid #2f80ed;padding-bottom:6px;">Today at a glance</h3>'
        f'<div style="font-size:0;">{cards}</div>'
        '<h3 style="color:#102a43;border-bottom:2px solid #2f80ed;padding-bottom:6px;margin-top:24px;">Full forecast</h3>'
        f'<pre class="forecast-pre">{body}</pre>'
        '</div></body></html>'
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


def parse_recipients(value: str) -> list[str]:
    recipients = [address.strip() for address in value.split(",") if address.strip()]
    if not recipients:
        raise ValueError("FORECAST_RECIPIENT must contain at least one email address")
    return recipients


def send_email(recipient: str, publication_id: str, forecast: str) -> None:
    recipients = parse_recipients(recipient)
    provider = os.getenv("EMAIL_PROVIDER", "smtp").lower()
    if provider == "brevo":
        send_brevo_email(recipients, publication_id, forecast)
        return
    if provider == "resend":
        send_resend_email(recipients, publication_id, forecast)
        return

    host = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.environ["SMTP_USERNAME"]
    password = os.environ["SMTP_PASSWORD"]
    sender = os.getenv("SMTP_FROM", username)

    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message["Subject"] = f"New Reno soaring forecast: {publication_id}"
    message.set_content(f"A new NWS Reno soaring forecast was published.\n\n{forecast}\n")
    message.add_alternative(format_forecast_html(publication_id, forecast), subtype="html")
    message.add_attachment(
        render_forecast_image(publication_id, forecast),
        maintype="image",
        subtype="png",
        filename=f"reno-soaring-forecast-{publication_id.split()[-1]}.png",
    )

    with smtplib.SMTP(host, port, timeout=30) as server:
        server.starttls()
        server.login(username, password)
        server.send_message(message)


def send_brevo_email(recipients: list[str], publication_id: str, forecast: str) -> None:
    payload = json.dumps(
        {
            "sender": {"email": os.environ["EMAIL_FROM"]},
            "to": [{"email": recipient} for recipient in recipients],
            "subject": f"New Reno soaring forecast: {publication_id}",
            "textContent": f"A new NWS Reno soaring forecast was published.\n\n{forecast}\n",
            "htmlContent": format_forecast_html(publication_id, forecast),
            "attachment": [
                {
                    "name": f"reno-soaring-forecast-{publication_id.split()[-1]}.png",
                    "content": base64.b64encode(render_forecast_image(publication_id, forecast)).decode("ascii"),
                }
            ],
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


def send_resend_email(recipients: list[str], publication_id: str, forecast: str) -> None:
    payload = json.dumps(
        {
            "from": os.environ["EMAIL_FROM"],
            "to": recipients,
            "subject": f"New Reno soaring forecast: {publication_id}",
            "attachments": [
                {
                    "filename": f"reno-soaring-forecast-{publication_id.split()[-1]}.png",
                    "content": base64.b64encode(render_forecast_image(publication_id, forecast)).decode("ascii"),
                }
            ],
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


WHATSAPP_MAX_CHARS = 4096


FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    "C:/Windows/Fonts/consola.ttf",
    "C:/Windows/Fonts/cour.ttf",
)


def _mono_font(size: int):
    from PIL import ImageFont

    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def render_forecast_image(publication_id: str, forecast: str) -> bytes:
    """Render the forecast as a PNG so the layout is identical on every device."""
    import io

    from PIL import Image, ImageDraw

    font = _mono_font(16)
    padding = 24
    line_height = 22
    lines = forecast.split("\n")
    text_width = int(max((font.getlength(line) for line in lines), default=0))
    width = max(text_width, int(font.getlength(publication_id))) + padding * 2
    height = line_height * (len(lines) + 3) + padding * 2

    image = Image.new("RGB", (width, height), "#ffffff")
    draw = ImageDraw.Draw(image)
    draw.text((padding, padding), f"Reno Soaring Forecast  {publication_id}", fill="#102a43", font=font)
    y = padding + line_height * 2
    for line in lines:
        draw.text((padding, y), line, fill="#243b53", font=font)
        y += line_height

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def send_whatsapp(recipient: str, publication_id: str, forecast: str) -> None:
    from twilio.rest import Client

    client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
    body = f"New NWS Reno soaring forecast ({publication_id}):\n\n{forecast}"
    chunks = [body[i : i + WHATSAPP_MAX_CHARS] for i in range(0, len(body), WHATSAPP_MAX_CHARS)]
    for chunk in chunks:
        client.messages.create(
            body=chunk,
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
