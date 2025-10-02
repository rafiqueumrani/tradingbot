import imaplib
import os
from dotenv import load_dotenv

# Load env file
load_dotenv()

EMAIL_USER = os.getenv("GMAIL_USER")
EMAIL_PASS = os.getenv("GMAIL_APP_PASSWORD")

try:
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(EMAIL_USER, EMAIL_PASS)
    print("✅ Gmail IMAP login successful!")
    mail.logout()
except Exception as e:
    print("❌ Gmail login failed:", str(e))
