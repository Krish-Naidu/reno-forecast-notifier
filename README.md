# Reno Forecast Notifier

Polls the National Weather Service Reno soaring guidance product and sends the full forecast by email when a new publication is detected. The default recipient is `krish.28.naidu@gmail.com`.

## Setup

1. Create a virtual environment and install the optional WhatsApp dependency:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and configure one email provider. Brevo is convenient if you do not own a custom domain: verify your sender address in Brevo, create an API key, set `EMAIL_PROVIDER=brevo`, `BREVO_API_KEY`, and `EMAIL_FROM`. Never put the API key in source control. Resend and Gmail SMTP remain supported.

3. Export the values from `.env` in your shell, or use a secrets manager. PowerShell example:

   ```powershell
   Get-Content .env | ForEach-Object {
     if ($_ -and -not $_.StartsWith('#')) { $name, $value = $_ -split '=', 2; [Environment]::SetEnvironmentVariable($name, $value) }
   }
   ```

4. Verify the NWS fetch without sending a message:

   ```powershell
   py forecast_notifier.py --once --dry-run
   ```

5. Run continuously:

   ```powershell
   py forecast_notifier.py
   ```

For unattended operation on Windows, create a Task Scheduler task that starts `py forecast_notifier.py` at login or system startup, with the project directory as the working directory. The program polls every five minutes, waits until 7:00 AM in Reno (`America/Los_Angeles`), and sends only once per local calendar day. Keep the process running so it can send automatically each morning.

## WhatsApp

WhatsApp delivery is optional and uses Twilio. Set `WHATSAPP_ENABLED=true`, add the Twilio credentials, and complete Twilio's WhatsApp sender/recipient approval or sandbox setup. WhatsApp messages are truncated to fit a single message; email remains the complete forecast.

## Data source

NWS Reno product: https://forecast.weather.gov/product.php?site=REV&issuedby=REV&product=SRG
