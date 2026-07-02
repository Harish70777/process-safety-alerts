import os
import difflib
import feedparser
from datetime import datetime, timedelta, timezone
from ics import Calendar, Event
from google import genai

RSS_URLS = [
    os.environ.get("SAFETY_RSS_URL_1"),
    os.environ.get("SAFETY_RSS_URL_2"),
    os.environ.get("SAFETY_RSS_URL_3")
]
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

ICS_FILE = "psm_alerts.ics"
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

    prompt = f"""
    You are a process safety expert. Categorize this news headline and summary:
    Title: {title}
    Summary: {summary}

    Choose EXACTLY ONE label:
    - catastrophic industrial incident
    - minor localized spill
    - financial corporate news
    - residential or vehicle accident
    - regulatory or legal action
    - other

    Respond with ONLY the exact label name.
    """
    try:
        response = client.models.generate_content(
            model='gemini-3.1-flash-lite', contents=prompt
        )
        label = response.text.strip().lower()
        if label in ["catastrophic industrial incident", "regulatory or legal action"]:
            return True
        print(f"Filtered out: {title} ({label})")
        return False
    except Exception as e:
        print(f"API Error: {e}")
        return True

def main():
    processed_urls = set(load_history(URL_HISTORY_FILE))
    processed_titles = load_history(TITLE_HISTORY_FILE)
    calendar = Calendar(open(ICS_FILE, "r", encoding="utf-8").read()) if os.path.exists(ICS_FILE) else Calendar()
    new_alerts = 0

    for url in filter(None, RSS_URLS):
        for entry in reversed(feedparser.parse(url).entries):
            link = entry.link
            title = entry.title.replace("<b>", "").replace("</b>", "")
            summary = entry.summary.replace("<b>", "").replace("</b>", "") if 'summary' in entry else ""

            if link not in processed_urls:
                if not is_duplicate_news(title, processed_titles) and is_critical_safety_event(title, summary):
                    event = Event()
                    event.name = f"🚨 PSM Alert: {title[:40]}..."
                    event.description = f"{title}\n\n{summary}\n\n{link}"
                    event.begin = datetime.now(timezone.utc)
                    event.duration = timedelta(minutes=15)
                    calendar.events.add(event)

                    save_history(TITLE_HISTORY_FILE, title)
                    processed_titles.append(title)
                    new_alerts += 1

                save_history(URL_HISTORY_FILE, link)
                processed_urls.add(link)

    if new_alerts > 0:
        with open(ICS_FILE, "w", encoding="utf-8") as f:
            f.writelines(calendar.serialize_iter())

if __name__ == "__main__": main()
