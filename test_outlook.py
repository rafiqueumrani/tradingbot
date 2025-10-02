import imaplib

IMAP_HOST = "outlook.office365.com"
IMAP_PORT = 993
IMAP_USER = "umranirafique@outlook.com"
IMAP_PASS = "sdxbapkiupwpgmyh"  # App password paste karo

print("🔎 Connecting to server...")
try:
    mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    print("✅ Connected to IMAP server")

    print("🔎 Trying login...")
    resp, data = mail.login(IMAP_USER, IMAP_PASS)
    print("✅ Login successful!", resp, data)

    mail.logout()
except Exception as e:
    print("❌ Error:", e)
