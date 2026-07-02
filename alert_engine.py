import os
import json
import difflib
import feedparser
from datetime import datetime, timezone, timedelta
from ics import Calendar, Event
from google import genai
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Configurations
RSS_URLS = [
    os.environ.get("SAFETY_RSS_URL_1"), 
    os.environ.get("SAFETY_RSS_URL_2"), 
    os.environ.get("SAFETY_RSS_URL_3")
]
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
CALENDAR_ID = os.environ.get("TARGET_CALENDAR_ID")
SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT")

ICS_FILE = "psm_alerts.ics"
URL_HISTORY_FILE = "processed_urls.txt"
TITLE_HISTORY_FILE = "processed_titles.txt"

def get_calendar_service():
    if not SERVICE_ACCOUNT_JSON: return None
    scopes = ['https://www.googleapis.com/auth/calendar.events']
    creds_dict = json.loads(SERVICE_ACCOUNT_JSON)
    creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return build('calendar', 'v3', credentials=creds)

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
    prompt = f"Categorize this news headline and summary:\nTitle: {title}\nSummary: {summary}\n\nChoose EXACTLY ONE label:\n- catastrophic industrial incident\n- minor localized spill\n- financial corporate news\n- residential or vehicle accident\n- regulatory or legal action\n- other\n\nRespond with ONLY the exact label name."
    try:
        response = client.models.generate_content(model='gemini-3.1-flash-lite', contents=prompt)
        label = response.text.strip().lower()
        if label in ["catastrophic industrial incident", "regulatory or legal action"]:
            return True
        return False
    except Exception as e:
        return True

def main():
    processed_urls = set(load_history(URL_HISTORY_FILE))
    processed_titles = load_history(TITLE_HISTORY_FILE)
    
    # Load ICS Calendar for external clients
    ics_calendar = Calendar(open(ICS_FILE, "r", encoding="utf-8").read()) if os.path.exists(ICS_FILE) else Calendar()
    
    # Load Google API for internal team
    google_service = get_calendar_service()
    
    new_alerts = 0

    for url in filter(None, RSS_URLS):
        feed = feedparser.parse(url)
        for entry in reversed(feed.entries):
            link = entry.link
            title = entry.title.replace("<b>", "").replace("</b>", "")
            summary = entry.summary.replace("<b>", "").replace("</b>", "") if 'summary' in entry else ""

            if link not in processed_urls:
                if not is_duplicate_news(title, processed_titles) and is_critical_safety_event(title, summary):
                    
                    start_time = datetime.now(timezone.utc)
                    end_time = start_time + timedelta(minutes=15)
                    
                    # 1. Push to internal Google Calendar (Instantly)
                    if google_service and CALENDAR_ID:
                        event_body = {
                            'summary': f"🚨 PSM Alert: {title[:40]}...",
                            'description': f"Incident: {title}\n\nSummary: {summary}\n\nLink: {link}",
                            'start': {'dateTime': start_time.isoformat()},
                            'end': {'dateTime': end_time.isoformat()},
                            'colorId': '11' 
                        }
                        try:
                            google_service.events().insert(calendarId=CALENDAR_ID, body=event_body).execute()
                        except Exception as e:
                            print(f"Google API Error: {e}")

                    # 2. Add to ICS file for external Outlook/Apple clients
                    event = Event()
                    event.name = f"🚨 PSM Alert: {title[:40]}..."
                    event.description = f"{title}\n\n{summary}\n\n{link}"
                    event.begin = start_time
                    event.duration = timedelta(minutes=15)
                    ics_calendar.events.add(event)
                    
                    save_history(TITLE_HISTORY_FILE, title)
                    processed_titles.append(title)
                    new_alerts += 1

                save_history(URL_HISTORY_FILE, link)
                processed_urls.add(link)

    # Save the updated ICS file to GitHub
    if new_alerts > 0:
        with open(ICS_FILE, "w", encoding="utf-8") as f:
            f.writelines(ics_calendar.serialize_iter())

if __name__ == "__main__":
    main()
