# Reno Forecast Notifier

Polls the National Weather Service Reno soaring guidance product and sends the full forecast by email when a new publication is detected. The default recipient is `krish.28.naidu@gmail.com`.

## GitHub-only setup

The scheduled workflow runs on GitHub-hosted servers. Your computer does not need to be on, and no terminal needs to remain open.

1. In the repository, open **Settings -> Secrets and variables -> Actions**.
2. Add these repository secrets:

   ```text
   BREVO_API_KEY       your current Brevo API key
   EMAIL_FROM          krishchunk@gmail.com
   FORECAST_RECIPIENT  krish.28.naidu@gmail.com, someone@example.com
   ```

   Separate multiple recipients with commas. Each recipient receives the same email.

3. Open **Actions -> Reno forecast notifier**, then choose **Run workflow** to test it.

The workflow runs once daily at 14:05 UTC (7:05 AM Reno time / 3:05 PM London time in summer). The Python code waits until 7:00 AM Reno time (`America/Los_Angeles`), confirms that NWS has published today's report, and sends at most one message per local calendar day.

> **Why once a day instead of every 15 minutes?** The original every-15-minutes schedule was heavily delayed by GitHub Actions (runs fired 3–4 hours apart), so the email that should have gone out at 7 AM Reno arrived around 10 AM Reno (6 PM London). A single daily run is far less likely to be delayed. GitHub may still start a scheduled job a few minutes late, and the Python `SEND_HOUR` gate remains as a safety net. The local `.env` file is not used by GitHub Actions and must never be committed.

This private repository is suitable for the workflow. GitHub Actions usage is subject to the account's included private-repository minutes, and scheduled workflows may be disabled after long periods with no repository activity.

## WhatsApp

WhatsApp delivery is optional and uses Twilio. It sends the **full forecast as a PNG image** (the same image attached to the email) so the monospace columns stay aligned on a phone. Twilio fetches WhatsApp media server-side, so the image is uploaded to a public host (uguu.se, falling back to catbox.moe) and the resulting URL is passed to Twilio. If the upload fails, it falls back to sending the forecast as text, split into messages if it exceeds WhatsApp's 4096-character limit.

> **Sandbox sessions expire after 24 hours.** WhatsApp only allows free-form messages (and media) inside a 24-hour customer service window that opens when *you* message the sender first. Outside that window, business-initiated messages require an approved template, which the sandbox does not support for this use case. So before each send, you must have messaged the sandbox recently — the simplest fix is to send any message (e.g. `join <your sandbox code>`) to the sandbox number from your phone each day, or shortly before the scheduled run. If the window is closed, Twilio returns error 21654 and the run logs a message telling you to reopen it. The email still sends either way.

To enable it:

1. Add these repository **secrets** (Settings -> Secrets and variables -> Actions -> Secrets):

   ```text
   TWILIO_ACCOUNT_SID     your Twilio Account SID
   TWILIO_AUTH_TOKEN      your Twilio Auth Token
   TWILIO_WHATSAPP_FROM   the Twilio WhatsApp sender, e.g. whatsapp:+14155255555
   TWILIO_WHATSAPP_TO     your number, e.g. whatsapp:+447700900000
   ```

2. Add a repository **variable** (Secrets and variables -> Actions -> Variables):

   ```text
   WHATSAPP_ENABLED = true
   ```

   WhatsApp stays off (and the workflow still runs) until this variable is set.

3. Complete Twilio's WhatsApp sender/recipient approval or sandbox setup.

## Data source

NWS Reno product: https://forecast.weather.gov/product.php?site=REV&issuedby=REV&product=SRG
