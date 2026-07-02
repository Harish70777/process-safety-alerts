import os
import smtplib
from email.mime.text import MIMEText

# Pull credentials from the vault
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_APP_PASSWORD")
RECIPIENT = "harish@rskless.com"

print("Initiating Nuclear Test...")

try:
    # Build a plain text email (No links, no attachments to avoid spam filters)
    msg = MIMEText("This is a direct test from the GitHub engine. If you are reading this, the pipes are perfectly connected and the firewall let it through!")
    msg['Subject'] = "🚨 ENGINE TEST: Pipeline Check"
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECIPIENT

    # Fire the email
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(SENDER_EMAIL, SENDER_PASSWORD)
    server.send_message(msg)
    server.quit()
    print("SUCCESS: The email has officially left the GitHub server!")

except Exception as e:
    print(f"CRITICAL FAILURE: {e}")
