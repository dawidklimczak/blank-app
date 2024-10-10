import streamlit as st
import imaplib
import email
from email.header import decode_header
import html2text

# Dane logowania do skrzynek (w praktyce lepiej przechowywać je bezpiecznie)
accounts = [
    {"email": "otwieraczmaili@wp.pl", "password": "Ku6hCTgMvwtnq8w", "imap_server": "imap.wp.pl"},
    # Dodaj więcej kont według potrzeb
]

def decode_content(part):
    content = part.get_payload(decode=True)
    charset = part.get_content_charset()
    if charset:
        return content.decode(charset)
    return content.decode()

def fetch_email_by_subject(account, subject):
    mail = imaplib.IMAP4_SSL(account["imap_server"])
    mail.login(account["email"], account["password"])
    mail.select("inbox")
    
    _, search_data = mail.search(None, f'SUBJECT "{subject}"')
    email_ids = search_data[0].split()
    
    if email_ids:
        _, msg_data = mail.fetch(email_ids[-1], "(RFC822)")
        email_body = msg_data[0][1]
        email_message = email.message_from_bytes(email_body)
        
        subject = decode_header(email_message["Subject"])[0][0]
        if isinstance(subject, bytes):
            subject = subject.decode()
        
        content = ""
        if email_message.is_multipart():
            for part in email_message.walk():
                if part.get_content_type() == "text/plain":
                    content += decode_content(part)
                elif part.get_content_type() == "text/html":
                    html_content = decode_content(part)
                    content += html2text.html2text(html_content)
        else:
            content = decode_content(email_message)
        
        mail.close()
        mail.logout()
        return subject, content
    
    mail.close()
    mail.logout()
    return None, None

st.title("Multi-account Email Viewer")

subject_to_search = st.text_input("Enter email subject to search for:")

if st.button("Search Emails"):
    for account in accounts:
        st.subheader(f"Searching in {account['email']}")
        subject, content = fetch_email_by_subject(account, subject_to_search)
        if subject:
            st.write(f"Subject: {subject}")
            st.text_area("Content:", content, height=200)
        else:
            st.write("No email found with the given subject.")
        st.markdown("---")