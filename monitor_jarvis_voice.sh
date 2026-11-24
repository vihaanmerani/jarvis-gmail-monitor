#!/bin/bash
# Jarvis email monitor — runs every 5 minutes via cron
# Sends unread email notifications to ntfy.sh topic ntfy.sh/jarvis-vihaan-merani-67

TOPIC="ntfy.sh/jarvis-vihaan-merani-67"
LOG="/Users/saiteja/Desktop/Jarvis/logs/monitor.log"
mkdir -p /Users/saiteja/Desktop/Jarvis/logs

echo "$(date) - Checking for new emails" >> "$LOG"

# NOTE: To actually read Gmail, you need to configure a Gmail API client or
# use an IMAP client with OAuth2. The assistant's built-in Gmail tools are not
# callable from a shell script. This script is a placeholder that logs the check
# and can be extended with your preferred Gmail access method.

# Example (requires gmail-cli or similar):
# NEW_EMAILS=$(gmail list --query "is:unread newer_than:5m")
# for id in $NEW_EMAILS; do
#   SUBJECT=$(gmail show "$id" --format subject)
#   if echo "$SUBJECT" | grep -qiE "urgent|otp|verification|recovery|security"; then
#     curl -X POST -H "Priority: urgent" -d "Urgent email: $SUBJECT" "https://$TOPIC"
#   else
#     curl -X POST -H "Priority: default" -d "New email: $SUBJECT" "https://$TOPIC"
#   fi
# done

exit 0