import streamlit as st
import imaplib
import email
from email.header import decode_header
import base64
import re
import quopri
import logging
from io import StringIO
import chardet
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# Konfiguracja logowania
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Bufor dla logów
log_buffer = StringIO()
stream_handler = logging.StreamHandler(log_buffer)
stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(stream_handler)

# Dane logowania do skrzynek (w praktyce lepiej przechowywać je bezpiecznie)
accounts = [
    {"email": "otwieraczmaili@wp.pl", "password": "Ku6hCTgMvwtnq8w", "imap_server": "imap.wp.pl"},
    {"email": "otwieraczmaili10@wp.pl", "password": "Ku6hCTgMvwtnq8w", "imap_server": "imap.wp.pl"},
    # Dodaj więcej kont według potrzeb
]

def decode_content(part):
    content = part.get_payload(decode=True)
    charset = part.get_content_charset()
    if charset is None:
        detected = chardet.detect(content)
        charset = detected['encoding']
    if charset:
        try:
            return content.decode(charset)
        except UnicodeDecodeError:
            return content.decode(charset, errors='replace')
    return content.decode('utf-8', errors='replace')

def load_image(url):
    try:
        response = requests.get(url, timeout=5)
        logger.debug(f"Loaded image from {url}")
        return response.content
    except Exception as e:
        logger.error(f"Failed to load image from {url}: {e}")
        return None

def simulate_link_click(url):
    try:
        response = requests.head(url, allow_redirects=True, timeout=5)
        logger.debug(f"Simulated click on link {url}")
        return response.url
    except Exception as e:
        logger.error(f"Failed to simulate click on {url}: {e}")
        return url

def process_html_content(html_content, email_message):
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Przetwarzanie obrazów
    for img in soup.find_all('img'):
        src = img.get('src')
        if src:
            if src.startswith('cid:'):
                # Obraz osadzony
                cid = src[4:]
                for part in email_message.walk():
                    if part.get('Content-ID') and part.get('Content-ID').strip('<>') == cid:
                        img_data = part.get_payload(decode=True)
                        img_type = part.get_content_type()
                        encoded_image = base64.b64encode(img_data).decode()
                        img['src'] = f"data:{img_type};base64,{encoded_image}"
                        break
            else:
                # Obraz zewnętrzny
                full_url = urljoin(email_message['From'], src)
                img_data = load_image(full_url)
                if img_data:
                    encoded_image = base64.b64encode(img_data).decode()
                    img['src'] = f"data:image/png;base64,{encoded_image}"
    
    # Przetwarzanie linków
    for a in soup.find_all('a'):
        href = a.get('href')
        if href:
            full_url = urljoin(email_message['From'], href)
            a['href'] = simulate_link_click(full_url)
    
    # Dodanie stylów do body
    body = soup.find('body')
    if body:
        body['style'] = 'max-width: 800px; margin: auto; padding: 20px;'
    
    return str(soup)

def mark_as_read(mail, email_id):
    mail.store(email_id, '+FLAGS', '\\Seen')
    logger.debug(f"Marked email {email_id} as read")

def fetch_email_by_subject(account, subject):
    logger.debug(f"Attempting to fetch email with subject: {subject}")
    mail = imaplib.IMAP4_SSL(account["imap_server"])
    mail.login(account["email"], account["password"])
    mail.select("inbox")
    
    # Lista metod wyszukiwania
    search_methods = [
        lambda: mail.search(None, f'SUBJECT "{subject}"'),
        lambda: mail.search(None, f'SUBJECT "{subject.encode("utf-8").decode("latin-1")}"'),
        lambda: mail.uid('SEARCH', 'CHARSET', 'UTF-8', 'SUBJECT', subject),
        lambda: mail.search(None, 'ALL')
    ]
    
    email_ids = []
    for i, search_method in enumerate(search_methods):
        try:
            logger.debug(f"Trying search method {i+1}")
            _, search_data = search_method()
            email_ids = search_data[0].split()
            logger.debug(f"Search method {i+1} result: {email_ids}")
            if email_ids:
                break
        except Exception as e:
            logger.error(f"Error in search method {i+1}: {e}")
    
    if email_ids:
        for email_id in reversed(email_ids):  # Sprawdzamy od najnowszych
            try:
                _, msg_data = mail.fetch(email_id, '(RFC822)')
                email_body = msg_data[0][1]
                email_message = email.message_from_bytes(email_body)
                
                current_subject = decode_header(email_message["Subject"])[0][0]
                if isinstance(current_subject, bytes):
                    current_subject = current_subject.decode('utf-8', errors='replace')
                
                logger.debug(f"Checking email with subject: {current_subject}")
                
                if subject.lower() in current_subject.lower():
                    content = ""
                    html_content = ""
                    
                    for part in email_message.walk():
                        if part.get_content_type() == "text/plain":
                            content += decode_content(part)
                        elif part.get_content_type() == "text/html":
                            html_content += decode_content(part)
                    
                    final_content = process_html_content(html_content, email_message) if html_content else content
                    
                    # Oznacz wiadomość jako przeczytaną
                    mark_as_read(mail, email_id)
                    
                    mail.close()
                    mail.logout()
                    logger.debug(f"Email found, processed, and marked as read successfully")
                    return current_subject, final_content
            except Exception as e:
                logger.error(f"Error processing email: {e}")
    
    mail.close()
    mail.logout()
    logger.debug("No matching email found")
    return None, None

st.title("Multi-account Email Viewer")

subject_to_search = st.text_input("Enter email subject to search for:")

if st.button("Search Emails"):
    for account in accounts:
        st.subheader(f"Searching in {account['email']}")
        subject, content = fetch_email_by_subject(account, subject_to_search)
        if subject:
            st.write(f"Subject: {subject}")
            st.components.v1.html(content, height=600, scrolling=True)
            st.success("Email has been marked as read and open has been simulated.")
        else:
            st.write("No email found with the given subject.")
        st.markdown("---")

# Wyświetlanie logów debugowania
if st.checkbox("Show debug logs"):
    log_contents = log_buffer.getvalue()
    st.text_area("Debug Logs", log_contents, height=300)
    if st.button("Clear logs"):
        log_buffer.truncate(0)
        log_buffer.seek(0)