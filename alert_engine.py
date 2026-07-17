import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import difflib
import feedparser
from datetime import datetime, timezone, timedelta
from google import genai

# Configurations
RSS_URLS = [os.environ.get("SAFETY_RSS_URL_1"), os.environ.get("SAFETY_RSS_URL_2"), os.environ.get("SAFETY_RSS_URL_3")]
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

# Email Configurations
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_APP_PASSWORD")
RECIPIENTS = os.environ.get("RECIPIENT_EMAILS", "").split(",")

URL_HISTORY_FILE = "processed_urls.txt"
TITLE_HISTORY_FILE = "processed_titles.txt"

def load_history(filename):
    if not os.path.exists(filename): return []
    with open(filename, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def save_history(filename, item, max_lines=100):
    history = load_history(filename)
    history.append(item)
    with open(filename, "w", encoding="utf-8") as f:
        for line in history[-max_lines:]:
            f.write(line + "\n")

def is_duplicate_news(new_title, past_titles, threshold=0.65):
    for past_title in past_titles:
        if difflib.SequenceMatcher(None, new_title.lower(), past_title.lower()).ratio() > threshold:
            return True
    return False

def is_critical_safety_event(title, summary):
    if not GEMINI_KEY: return True 
    client = genai.Client(api_key=GEMINI_KEY)
    
    # NEW SUPER-STRICT AI PROMPT
    prompt = f"""Analyze this news headline and summary for a Process Safety Management (PSM) alert system:
Title: {title}
Summary: {summary}

A True Process Safety Event is an ACCIDENTAL explosion, catastrophic fire, or major toxic chemical release at an industrial facility (refinery, chemical plant, pipeline) due to equipment failure or operational error.

You MUST EXCLUDE:
- Acts of war, military strikes, drone attacks, or terrorism.
- Sabotage, vandalism, or intentional pipeline tapping.
- Stock photos or historical image sales.
- General political, tourism, or public complaints about risks.

Choose EXACTLY ONE label from the list below:
- true process safety incident
- intentional attack or war
- stock photo or historical
- regulatory or legal action
- other

Respond with ONLY the exact label name."""

    try:
        response = client.models.generate_content(model='gemini-3.1-flash-lite', contents=prompt)
        label = response.text.strip().lower()
        
        # Now it ONLY lets true accidents through!
        if label in ["true process safety incident","other"]:
            return True
            
        print(f"AI Filter Blocked: {title} ({label})")
        return False
    except Exception as e:
        print(f"API Error: {e}")
        return True

def generate_ics_attachment(title, summary, link, start_time, end_time):
    """Creates a raw ICS calendar file in memory to attach to the email."""
    dt_start = start_time.strftime('%Y%m%dT%H%M%SZ')
    dt_end = end_time.strftime('%Y%m%dT%H%M%SZ')
    
    ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Process Safety Alert Engine//EN
BEGIN:VEVENT
SUMMARY:🚨 PSM Alert: {title[:40]}...
DESCRIPTION:Incident: {title}\\n\\nSummary: {summary}\\n\\nLink: {link}
DTSTART:{dt_start}
DTEND:{dt_end}
END:VEVENT
END:VCALENDAR"""
    return ics_content

def send_instant_email(title, summary, link):
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        print("Missing Email Credentials in GitHub Secrets. Aborting email.")
        return

    # Set appointment for right now
    start_time = datetime.now(timezone.utc)
    end_time = start_time + timedelta(minutes=15)

    # Build the Email
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = ", ".join(RECIPIENTS)
    msg['Subject'] = f"🚨 Safety Alert: {title[:50]}"

    # Email Body
    body_text = f"High-Consequence Process Safety Event Detected\n\nTitle: {title}\n\nSummary: {summary}\n\nRead more: {link}\n\n(A calendar invite is attached to block this review on your schedule)."
    msg.attach(MIMEText(body_text, 'plain'))

    # Build and Attach the Calendar File
    ics_data = generate_ics_attachment(title, summary, link, start_time, end_time)
    part = MIMEApplication(ics_data.encode('utf-8'), Name="psm_alert.ics")
    part['Content-Disposition'] = 'attachment; filename="psm_alert.ics"'
    msg.attach(part)

    # Fire the Email via Gmail's Servers
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"Successfully emailed alert to team: {title}")
    except Exception as e:
        print(f"Failed to send email: {e}")

def main():
    # The Disguise: Tells the news server we are a normal Chrome browser
    feedparser.USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    processed_urls = set(load_history(URL_HISTORY_FILE))
    processed_titles = load_history(TITLE_HISTORY_FILE)
    
    for url in filter(None, RSS_URLS):
        print(f"Fetching RSS Feed: {url}")
        feed = feedparser.parse(url)
        
        # Diagnostic Check: Did the server block us?
        if hasattr(feed, 'status'):
            print(f"Server Status Code: {feed.status}")
        if not feed.entries:
            print("WARNING: The news server returned 0 articles! (Possible IP block or empty feed).")
            continue
            
        for entry in reversed(feed.entries):
            link = entry.link
            title = entry.title.replace("<b>", "").replace("</b>", "")
            summary = entry.summary.replace("<b>", "").replace("</b>", "") if 'summary' in entry else ""

            if link not in processed_urls:
                if not is_duplicate_news(title, processed_titles) and is_critical_safety_event(title, summary):
                    
                    send_instant_email(title, summary, link)

                    save_history(TITLE_HISTORY_FILE, title)
                    processed_titles.append(title)

                save_history(URL_HISTORY_FILE, link)
                processed_urls.add(link)

if __name__ == "__main__":
    main()
