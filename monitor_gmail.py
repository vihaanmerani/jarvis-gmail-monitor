#!/usr/bin/env python3
"""
Jarvis Gmail Monitor
- Runs every 15 minutes via cron (*/15 * * * *)
- Checks Gmail for unread emails using OAuth credentials from environment variables (GMAIL_CREDENTIALS, GMAIL_TOKEN) or local ~/.gmail-mcp/
- Tracks seen email IDs in seen_ids.json to avoid duplicate alerts
- Sends short summaries (prefixed "Jarvis: ") to:
    1. ntfy.sh topic jarvis-vihaan-merani-67
    2. Mac Messages app to +918988987777 for urgent emails (skipped on Linux)
- Never includes OTP codes or passwords in notifications
"""

import os
import json
import platform
import re
import subprocess
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SEEN_IDS_FILE = os.path.join(BASE_DIR, "seen_ids.json")
GMAIL_CREDS_PATH = os.path.expanduser("~/.gmail-mcp/credentials.json")
NTFY_TOPIC = "jarvis-vihaan-merani-67"
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"
SMS_TARGET = "+918988987777"

URGENT_KEYWORDS = [
    "iitm", "school connect", "graded assignment", "ga4", "ga3", "deadline",
    "submission", "due", "live session", "week", "content", "released",
    "available", "take home", "project", "announcement", "portal",
    "mug", "mugs", "t-shirt", "tshirt", "t shirt", "custom mug",
    "custom t-shirt", "sublimation", "order", "sublimation ink",
    "urgent", "important", "action required", "verify", "security", "recovery",
]

def load_seen_ids():
    try:
        with open(SEEN_IDS_FILE, "r") as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_seen_ids(seen_ids):
    with open(SEEN_IDS_FILE, "w") as f:
        json.dump(sorted(seen_ids), f)

def is_urgent(subject: str, snippet: str) -> bool:
    text = (subject + " " + snippet).lower()
    return any(kw in text for kw in URGENT_KEYWORDS)

def sanitize(text: str) -> str:
    text = re.sub(r"\b\d{6}\b", "[OTP]", text)
    text = re.sub(r"(password|passcode|code|pin)\s*[:=]\s*\S+", r"\1: [REDACTED]", text, flags=re.I)
    if len(text) > 160:
        text = text[:157] + "..."
    return text

def send_ntfy(message: str, priority: str = "default"):
    cmd = [
        "/usr/bin/curl", "-s", "-X", "POST",
        "-H", f"Priority: {priority}",
        "-d", message,
        NTFY_URL,
    ]
    try:
        subprocess.run(cmd, check=True, timeout=10)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] ntfy send failed: {e}", file=sys.stderr)
        return False

def send_messages(message: str, phone: str):
    if platform.system() != "Darwin":
        print("[INFO] Non-macOS environment detected; skipping macOS Messages app notification.", file=sys.stderr)
        return True

    escaped = message.replace('"', '\\"')
    script = f'''
    tell application "Messages"
        set myService to 1st service
        set myBuddy to participant "{phone}" of myService
        send "{escaped}" to myBuddy
    end tell
    '''
    try:
        subprocess.run(["/usr/bin/osascript", "-e", script], check=True, timeout=10)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Messages send failed: {e}", file=sys.stderr)
        return False

def get_gmail_service():
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        print("[WARN] googleapiclient not installed; skipping Gmail check", file=sys.stderr)
        return None

    creds = None

    # 1. Try environment variables GMAIL_CREDENTIALS / GMAIL_TOKEN
    gmail_creds_env = os.environ.get("GMAIL_CREDENTIALS")
    gmail_token_env = os.environ.get("GMAIL_TOKEN")

    if gmail_creds_env or gmail_token_env:
        try:
            token_data = None
            if gmail_token_env:
                if gmail_token_env.strip().startswith("{"):
                    token_data = json.loads(gmail_token_env)
                elif os.path.exists(gmail_token_env):
                    with open(gmail_token_env, "r") as tf:
                        token_data = json.load(tf)
            
            creds_data = None
            if gmail_creds_env:
                if gmail_creds_env.strip().startswith("{"):
                    creds_data = json.loads(gmail_creds_env)
                elif os.path.exists(gmail_creds_env):
                    with open(gmail_creds_env, "r") as cf:
                        creds_data = json.load(cf)

            scopes = [
                "https://www.googleapis.com/auth/gmail.modify",
                "https://www.googleapis.com/auth/gmail.settings.basic",
            ]

            if token_data:
                creds = Credentials.from_authorized_user_info(token_data, scopes=scopes)
            elif creds_data:
                if "refresh_token" in creds_data:
                    creds = Credentials.from_authorized_user_info(creds_data, scopes=scopes)
        except Exception as e:
            print(f"[WARN] Failed loading credentials from env vars: {e}", file=sys.stderr)

    # 2. Fallback to local files if creds not yet loaded
    if not creds:
        token_path = os.path.expanduser("~/.gmail-mcp/token.json")
        scopes = [
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/gmail.settings.basic",
        ]
        if os.path.exists(token_path):
            try:
                creds = Credentials.from_authorized_user_file(token_path, scopes=scopes)
            except Exception:
                pass
        
        if not creds and os.path.exists(GMAIL_CREDS_PATH):
            try:
                creds = Credentials.from_authorized_user_file(GMAIL_CREDS_PATH, scopes=scopes)
            except Exception:
                pass

    if not creds:
        print("[ERROR] No valid Gmail credentials found via environment variables or local storage.", file=sys.stderr)
        return None

    try:
        return build("gmail", "v1", credentials=creds)
    except Exception as e:
        print(f"[ERROR] Gmail auth failed: {e}", file=sys.stderr)
        return None


def check_gmail():
    service = get_gmail_service()
    if not service:
        return

    seen = load_seen_ids()
    new_seen = set()

    try:
        request = service.users().messages().list(userId="me", q="is:unread newer_than:20m", maxResults=50)
        while request is not None:
            resp = request.execute()
            for msg in resp.get("messages", []):
                msg_id = msg["id"]
                if msg_id in seen:
                    continue

                full = service.users().messages().get(
                    userId="me", id=msg_id, format="metadata",
                    metadataHeaders=["Subject", "From", "Date"]
                ).execute()
                headers = {h["name"]: h["value"] for h in full.get("payload", {}).get("headers", [])}
                subject = headers.get("Subject", "(no subject)")
                sender = headers.get("From", "(unknown sender)")
                snippet = full.get("snippet", "")

                urgent = is_urgent(subject, snippet)
                priority = "urgent" if urgent else "default"

                summary = sanitize(f"Jarvis: {subject} — from {sender}")
                if not urgent:
                    summary = f"Jarvis: New email: {subject}"

                send_ntfy(summary, priority)
                if urgent:
                    send_messages(summary, SMS_TARGET)

                new_seen.add(msg_id)

            next_page = resp.get("nextPageToken")
            if next_page:
                request = service.users().messages().list(
                    userId="me", q="is:unread newer_than:20m", maxResults=50, pageToken=next_page
                )
            else:
                break
    except Exception as e:
        print(f"[ERROR] Error listing/fetching Gmail messages: {e}", file=sys.stderr)

    seen.update(new_seen)
    save_seen_ids(seen)



def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        test_msg = "Jarvis: TEST urgent notification from monitor_gmail.py"
        print("Sending test urgent to ntfy...")
        send_ntfy(test_msg, "urgent")
        print("Sending test urgent to Messages...")
        send_messages(test_msg, SMS_TARGET)
        return

    check_gmail()


if __name__ == "__main__":
    main()

