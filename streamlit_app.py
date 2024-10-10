import streamlit as st
from imapclient import IMAPClient
import email
from email.header import decode_header

# Dane logowania do skrzynek
MAILBOXES =[
    {"email": "otwieraczmaili@wp.pl", "password": "Ku6hCTgMvwtnq8w", "imap_server": "imap.wp.pl"},
    # Dodaj więcej kont według potrzeb
]

def search_emails(mailbox, subject_query):
    try:
        # Używanie IMAPClient do połączenia z serwerem IMAP
        with IMAPClient(mailbox['imap_server']) as client:
            client.login(mailbox['email'], mailbox['password'])
            client.select_folder('INBOX')

            # Wyszukiwanie e-maili po temacie
            messages = client.search(['SUBJECT', subject_query])

            # Pobieranie i dekodowanie wiadomości
            emails = []
            for uid in messages:
                raw_message = client.fetch([uid], ['RFC822'])[uid][b'RFC822']
                msg = email.message_from_bytes(raw_message)

                # Dekodowanie nagłówka "Subject"
                subject, encoding = decode_header(msg["subject"])[0]
                if isinstance(subject, bytes):
                    subject = subject.decode(encoding or 'utf-8', errors='ignore')

                # Dekodowanie nadawcy "From"
                from_, encoding = decode_header(msg["from"])[0]
                if isinstance(from_, bytes):
                    from_ = from_.decode(encoding or 'utf-8', errors='ignore')

                # Dodanie dekodowanych danych do listy e-maili
                emails.append({"subject": subject, "from": from_})

            return emails

    except Exception as e:
        return str(e)

# Streamlit - Interfejs użytkownika
st.title('Wyszukiwarka e-maili według tematu')

subject_query = st.text_input('Podaj temat e-maila do wyszukania:')

if st.button('Wyszukaj'):
    if subject_query:
        all_results = []
        for mailbox in MAILBOXES:
            st.write(f"Wyszukiwanie w skrzynce: {mailbox['email']}")
            result = search_emails(mailbox, subject_query)
            if isinstance(result, str):
                st.error(f"Błąd: {result}")
            else:
                for email_info in result:
                    st.write(f"Temat: {email_info['subject']}, Od: {email_info['from']}")
    else:
        st.warning("Podaj temat e-maila do wyszukania.")
