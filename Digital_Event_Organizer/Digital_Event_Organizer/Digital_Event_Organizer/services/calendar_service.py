import urllib.parse
from datetime import datetime, timedelta, timezone

def format_ics_datetime(dt_str, tm_str):
    """
    Combines date (YYYY-MM-DD) and time (HH:MM or HH:MM:SS) into ICS format: YYYYMMDDTHHMMSS
    """
    try:
        clean_time = tm_str.strip()
        if len(clean_time) == 5:
            clean_time += ":00"
        dt = datetime.strptime(f"{dt_str.strip()} {clean_time}", "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%Y%m%dT%H%M%S")
    except Exception:
        # Fallback to current date/time
        return datetime.now(timezone.utc).strftime("%Y%m%dT000000")

def generate_ics_content(event):
    """
    Generates an .ics calendar file for the event.
    """
    if not isinstance(event, dict):
        event = dict(event)
    title = event.get('title', 'Event')
    description = event.get('description', '')
    venue = event.get('venue', '')
    date_str = str(event.get('date', ''))
    start_time = str(event.get('time', '09:00'))
    end_time = str(event.get('end_time') or '')
    
    dtstart = format_ics_datetime(date_str, start_time)
    
    if end_time:
        dtend = format_ics_datetime(date_str, end_time)
    else:
        # Default end time: start + 2 hours
        try:
            st_obj = datetime.strptime(dtstart, "%Y%m%dT%H%M%S")
            dtend = (st_obj + timedelta(hours=2)).strftime("%Y%m%dT%H%M%S")
        except Exception:
            dtend = dtstart

    uid = f"eventorg-{event.get('event_id', '1')}-{dtstart}@eventorg.com"
    now_ics = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    ics_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//EventOrg//Event Management Platform//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{now_ics}",
        f"DTSTART:{dtstart}",
        f"DTEND:{dtend}",
        f"SUMMARY:{title}",
        f"DESCRIPTION:{description.replace(chr(10), ' ')}",
        f"LOCATION:{venue}",
        "STATUS:CONFIRMED",
        "END:VEVENT",
        "END:VCALENDAR"
    ]
    return "\r\n".join(ics_lines)

def generate_google_calendar_url(event):
    """
    Generates a Google Calendar web link for the event.
    """
    if not isinstance(event, dict):
        event = dict(event)
    title = event.get('title', 'Event')
    description = event.get('description', '')
    venue = event.get('venue', '')
    date_str = str(event.get('date', ''))
    start_time = str(event.get('time', '09:00'))
    end_time = str(event.get('end_time') or '')

    dtstart = format_ics_datetime(date_str, start_time)
    if end_time:
        dtend = format_ics_datetime(date_str, end_time)
    else:
        try:
            st_obj = datetime.strptime(dtstart, "%Y%m%dT%H%M%S")
            dtend = (st_obj + timedelta(hours=2)).strftime("%Y%m%dT%H%M%S")
        except Exception:
            dtend = dtstart

    params = {
        'action': 'TEMPLATE',
        'text': title,
        'dates': f"{dtstart}/{dtend}",
        'details': description,
        'location': venue
    }
    return f"https://calendar.google.com/calendar/render?{urllib.parse.urlencode(params)}"
