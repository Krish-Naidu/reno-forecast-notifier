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

WhatsApp delivery is optional and uses Twilio. Set `WHATSAPP_ENABLED=true`, add the Twilio credentials, and complete Twilio's WhatsApp sender/recipient approval or sandbox setup. WhatsApp messages are truncated to fit a single message; email remains the complete forecast.

## Data source

NWS Reno product: https://forecast.weather.gov/product.php?site=REV&issuedby=REV&product=SRG
