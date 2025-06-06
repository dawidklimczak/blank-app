import streamlit as st
import imaplib
import email
from email.header import decode_header
import base64
import logging
from io import StringIO
import chardet
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import time
import random

# Konfiguracja logowania
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Bufor dla logów
log_buffer = StringIO()
stream_handler = logging.StreamHandler(log_buffer)
stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(stream_handler)

# Pobieranie danych logowania z sekretów Streamlit Cloud
EMAIL_ACCOUNT = st.secrets["EMAIL_USERNAME"]
EMAIL_PASSWORD = st.secrets["EMAIL_PASSWORD"]
IMAP_SERVER = st.secrets["IMAP_SERVER"]
IMAP_PORT = int(st.secrets["IMAP_PORT"])

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

def debug_email_structure(email_id, mail):
    """Funkcja debugowania - pokazuje surową strukturę maila"""
    try:
        _, msg_data = mail.fetch(email_id, '(RFC822)')
        email_body = msg_data[0][1]
        email_message = email.message_from_bytes(email_body)
        
        subject = decode_header(email_message["Subject"])[0][0]
        if isinstance(subject, bytes):
            subject = subject.decode('utf-8', errors='replace')
        
        debug_info = {
            'subject': subject,
            'raw_size': len(email_body),
            'headers': dict(email_message.items()),
            'parts': []
        }
        
        st.subheader(f"Debugowanie maila: {subject}")
        
        # Pokaż główne nagłówki
        st.write("**Główne nagłówki:**")
        for header, value in email_message.items():
            st.text(f"{header}: {value}")
        
        # Pokaż surową treść (pierwsze 2000 znaków)
        st.write("**Surowa treść maila (pierwsze 2000 znaków):**")
        raw_text = email_body.decode('utf-8', errors='replace')
        st.code(raw_text[:2000], language='text')
        
        if len(raw_text) > 2000:
            st.write(f"... (ukryto {len(raw_text) - 2000} znaków)")
        
        # Analizuj wszystkie części
        st.write("**Analiza części multipart:**")
        part_num = 0
        
        for part in email_message.walk():
            part_num += 1
            content_type = part.get_content_type()
            content_disposition = part.get('Content-Disposition')
            
            st.write(f"**Część {part_num}:**")
            st.write(f"- Content-Type: `{content_type}`")
            st.write(f"- Content-Disposition: `{content_disposition}`")
            st.write(f"- Charset: `{part.get_content_charset()}`")
            
            # Pokaż nagłówki tej części
            part_headers = dict(part.items())
            if part_headers:
                st.write("- Nagłówki części:")
                for h_name, h_value in part_headers.items():
                    st.text(f"  {h_name}: {h_value}")
            
            # Spróbuj zdekodować treść
            if content_type in ['text/plain', 'text/html']:
                try:
                    decoded_content = decode_content(part)
                    
                    # Szukaj linków leadingmail w treści
                    leadingmail_links = []
                    for line in decoded_content.split('\n'):
                        if 'leadingmail.pl' in line.lower():
                            leadingmail_links.append(line.strip())
                    
                    st.write(f"- Rozmiar treści: {len(decoded_content)} znaków")
                    
                    if leadingmail_links:
                        st.success(f"**ZNALEZIONO {len(leadingmail_links)} linków LeadingMail!**")
                        for i, link in enumerate(leadingmail_links[:3]):  # Pokaż max 3
                            st.code(link, language='text')
                        if len(leadingmail_links) > 3:
                            st.write(f"... i {len(leadingmail_links) - 3} więcej")
                    
                    # Pokaż fragment treści
                    st.write("- Fragment treści:")
                    if content_type == 'text/html':
                        # Pokaż surowy HTML
                        st.code(decoded_content[:500], language='html')
                    else:
                        st.text(decoded_content[:500])
                    
                    if len(decoded_content) > 500:
                        st.write(f"... (ukryto {len(decoded_content) - 500} znaków)")
                        
                except Exception as e:
                    st.error(f"Błąd dekodowania części {part_num}: {e}")
            
            st.divider()
        
        return debug_info
        
    except Exception as e:
        st.error(f"Błąd podczas debugowania maila: {e}")
        logger.error(f"Error in debug_email_structure: {e}")
        return None

def load_image(url):
    """Ładuje obrazy z lepszymi nagłówkami do symulacji prawdziwej przeglądarki"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
        'Accept-Language': 'pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
    }
    
    try:
        session = requests.Session()
        session.headers.update(headers)
        response = session.get(url, timeout=10)
        response.raise_for_status()
        logger.debug(f"Loaded image from {url} - Status: {response.status_code}")
        return response.content
    except Exception as e:
        logger.error(f"Failed to load image from {url}: {e}")
        return None

def simulate_link_click(url, referer=None):
    """Poprawiona funkcja symulacji kliknięcia w link"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': 'max-age=0',
    }
    
    # Dodaj referer jeśli został podany
    if referer:
        headers['Referer'] = referer
    
    try:
        # Użyj sesji do zachowania ciasteczek
        session = requests.Session()
        session.headers.update(headers)
        
        # Symuluj prawdziwe kliknięcie - użyj GET i pobierz treść
        response = session.get(
            url, 
            allow_redirects=True, 
            timeout=15,
            stream=False
        )
        
        # Sprawdź czy żądanie było udane
        response.raise_for_status()
        
        # Loguj szczegóły odpowiedzi
        logger.debug(f"Clicked link {url}")
        logger.debug(f"Final URL after redirects: {response.url}")
        logger.debug(f"Status code: {response.status_code}")
        logger.debug(f"Response headers: {dict(response.headers)}")
        logger.debug(f"Content length: {len(response.content)} bytes")
        
        # Jeśli to strona HTML, spróbuj znaleźć dodatkowe tracking pixele
        content_type = response.headers.get('content-type', '').lower()
        if 'text/html' in content_type:
            try:
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Szukaj dodatkowych obrazów trackingowych
                tracking_images = soup.find_all('img', {'width': '1', 'height': '1'})
                tracking_images.extend(soup.find_all('img', style=lambda x: x and 'display:none' in x.replace(' ', '')))
                
                for img in tracking_images:
                    img_src = img.get('src')
                    if img_src:
                        img_url = urljoin(response.url, img_src)
                        try:
                            img_response = session.get(img_url, timeout=5)
                            logger.debug(f"Loaded tracking pixel: {img_url}")
                        except:
                            pass
                            
            except Exception as e:
                logger.debug(f"Could not parse HTML content for additional tracking: {e}")
        
        # Dodaj małe opóźnienie dla symulacji prawdziwego zachowania
        time.sleep(random.uniform(0.5, 2.0))
        
        return response.url
        
    except requests.exceptions.Timeout:
        logger.error(f"Timeout while clicking link {url}")
        return url
    except requests.exceptions.RequestException as e:
        logger.error(f"HTTP error while clicking link {url}: {e}")
        return url
    except Exception as e:
        logger.error(f"Unexpected error while clicking link {url}: {e}")
        return url

def process_html_content(html_content, email_message, should_click_links=True):
    """Przetwarzanie treści HTML z opcjonalnym klikaniem jednego losowego linku"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Liczniki do śledzenia ilości przetworzonych elementów
    processed_images = 0
    clicked_links = 0
    
    # Przetwarzanie obrazów (zawsze)
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
                        processed_images += 1
                        break
            else:
                # Obraz zewnętrzny - ładuj z nagłówkami przeglądarki
                full_url = urljoin(email_message.get('From', ''), src)
                img_data = load_image(full_url)
                if img_data:
                    # Spróbuj określić typ obrazu na podstawie nagłówków
                    try:
                        import imghdr
                        img_type = imghdr.what(None, h=img_data)
                        if img_type:
                            mime_type = f"image/{img_type}"
                        else:
                            mime_type = "image/png"  # fallback
                    except:
                        mime_type = "image/png"
                    
                    encoded_image = base64.b64encode(img_data).decode()
                    img['src'] = f"data:{mime_type};base64,{encoded_image}"
                    processed_images += 1
    
    # Przetwarzanie linków - kliknij w jeden losowy link jeśli should_click_links=True
    if should_click_links:
        base_url = email_message.get('From', '')
        all_links = soup.find_all('a')
        
        # Filtruj linki które mają href
        valid_links = [a for a in all_links if a.get('href')]
        
        if valid_links:
            # Weź pierwsze 10 linków (lub mniej jeśli jest mniej dostępnych)
            links_to_choose_from = valid_links[:10]
            
            # Wylosuj jeden link
            chosen_link = random.choice(links_to_choose_from)
            href = chosen_link.get('href')
            
            full_url = urljoin(base_url, href)
            # Symuluj kliknięcie w wylosowany link
            clicked_url = simulate_link_click(full_url, referer=base_url)
            chosen_link['href'] = clicked_url
            clicked_links = 1
            
            logger.debug(f"Clicked random link: {href} (chosen from {len(links_to_choose_from)} available links)")
        else:
            logger.debug("No valid links found to click")
        
        logger.debug(f"Processed {processed_images} images and clicked {clicked_links} link")
    else:
        logger.debug(f"Processed {processed_images} images, links not clicked")
    
    # Dodanie stylów do body
    body = soup.find('body')
    if body:
        body['style'] = 'max-width: 800px; margin: auto; padding: 20px; font-family: Arial, sans-serif;'
    
    return str(soup), clicked_links

def delete_email(mail, email_id):
    try:
        mail.store(email_id, '+FLAGS', '\\Deleted')
        mail.expunge()
        logger.debug(f"Deleted email {email_id}")
        return True
    except Exception as e:
        logger.error(f"Error deleting email {email_id}: {e}")
        return False

def count_emails_by_subject(subject):
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
        mail.select("inbox")
        
        _, search_data = mail.search(None, f'SUBJECT "{subject}"')
        email_ids = search_data[0].split()
        
        mail.close()
        mail.logout()
        
        return len(email_ids)
    except Exception as e:
        logger.error(f"Error counting emails: {e}")
        return 0

def get_first_email_by_subject(mail, subject):
    """Pobiera ID pierwszego maila o danym temacie"""
    try:
        _, search_data = mail.search(None, f'SUBJECT "{subject}"')
        email_ids = search_data[0].split()
        
        if email_ids:
            return email_ids[0]
        return None
    except Exception as e:
        logger.error(f"Error searching emails: {e}")
        return None

def process_email(email_id, mail, should_click_links=True):
    """Przetwarzanie pojedynczego maila z opcjonalnym klikaniem linków"""
    try:
        _, msg_data = mail.fetch(email_id, '(RFC822)')
        email_body = msg_data[0][1]
        email_message = email.message_from_bytes(email_body)
        
        subject = decode_header(email_message["Subject"])[0][0]
        if isinstance(subject, bytes):
            subject = subject.decode('utf-8', errors='replace')
        
        logger.debug(f"Processing email with subject: {subject}, click_links: {should_click_links}")
        
        content = ""
        html_content = ""
        html_parts = []
        
        # Zbierz wszystkie części HTML i sprawdź które zawierają linki trackingowe
        for part in email_message.walk():
            if part.get_content_type() == "text/plain":
                content += decode_content(part)
            elif part.get_content_type() == "text/html":
                decoded_html = decode_content(part)
                html_parts.append({
                    'content': decoded_html,
                    'has_leadingmail': 'leadingmail.pl' in decoded_html.lower(),
                    'leadingmail_count': decoded_html.lower().count('leadingmail.pl')
                })
        
        # Wybierz najlepszą część HTML (z trackingiem jeśli dostępna)
        links_clicked = 0
        if html_parts:
            # Preferuj części z linkami LeadingMail
            tracking_parts = [p for p in html_parts if p['has_leadingmail']]
            
            if tracking_parts:
                # Wybierz część z największą liczbą linków trackingowych
                best_part = max(tracking_parts, key=lambda x: x['leadingmail_count'])
                html_content = best_part['content']
                logger.debug(f"Using HTML part with {best_part['leadingmail_count']} LeadingMail links")
            else:
                # Jeśli żadna część nie ma linków trackingowych, użyj ostatniej
                html_content = html_parts[-1]['content']
                logger.debug("No LeadingMail links found in any HTML part, using last part")
            
            logger.debug(f"Total HTML parts found: {len(html_parts)}, parts with tracking: {len(tracking_parts)}")
        
        if html_content:
            final_content, links_clicked = process_html_content(html_content, email_message, should_click_links)
        else:
            final_content = content
            links_clicked = 0
        
        # Usuń wiadomość po przetworzeniu
        delete_success = delete_email(mail, email_id)
        
        if delete_success:
            logger.debug(f"Email processed and deleted successfully")
        else:
            logger.warning(f"Email processed but deletion failed")
            
        return subject, final_content, delete_success, links_clicked
    except Exception as e:
        logger.error(f"Error processing email: {e}")
        return None, None, False, 0

def open_emails_by_subject(subject, count=None, interval=10, click_percentage=100):
    """Otwieranie maili z kontrolą procentu klikanych linków"""
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
        mail.select("inbox")
        
        # Sprawdź ile maili o danym temacie jest dostępnych
        _, search_data = mail.search(None, f'SUBJECT "{subject}"')
        all_email_ids = search_data[0].split()
        
        if not all_email_ids:
            st.warning(f"Nie znaleziono maili o temacie '{subject}'")
            mail.close()
            mail.logout()
            return []
        
        total_emails = len(all_email_ids)
        emails_to_process = min(count or total_emails, total_emails)
        
        # Wylosuj które maile będą miały kliknięte linki
        emails_to_click = int(emails_to_process * click_percentage / 100)
        click_indices = set(random.sample(range(emails_to_process), emails_to_click))
        
        logger.debug(f"Will click links in {emails_to_click} out of {emails_to_process} emails")
        logger.debug(f"Click indices: {sorted(click_indices)}")
        
        processed_emails = []
        processed_count = 0
        error_count = 0
        total_links_clicked = 0
        
        # Kontenery na wyświetlanie maili (będziemy je odwracać na końcu)
        email_containers = []
        
        # Główny kontener na postęp
        progress_container = st.container()
        
        with progress_container:
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # Pokaż informację o ustawieniach klikania
            if click_percentage < 100:
                status_text.text(f"Rozpoczynam przetwarzanie {emails_to_process} maili (linki kliknięte w {emails_to_click} mailach, {click_percentage}%)")
            else:
                status_text.text(f"Rozpoczynam przetwarzanie {emails_to_process} maili (linki kliknięte we wszystkich)")
            
            for i in range(emails_to_process):
                # Sprawdź czy w tym mailu mają być kliknięte linki
                should_click = i in click_indices
                
                # Pobierz pierwszy dostępny mail o podanym temacie
                email_id = get_first_email_by_subject(mail, subject)
                
                if not email_id:
                    status_text.text(f"Nie znaleziono więcej maili o temacie '{subject}'")
                    break
                
                # Aktualizacja paska postępu
                progress = (i + 1) / emails_to_process
                progress_bar.progress(progress)
                action_text = "z klikaniem linków" if should_click else "bez klikania linków"
                status_text.text(f"Przetwarzanie maila {i+1} z {emails_to_process} ({action_text})")
                
                # Dodaj nowy kontener dla maila (będzie na początku listy)
                email_container = st.container()
                email_containers.insert(0, email_container)
                
                # Przetwórz mail
                mail_subject, mail_content, delete_success, links_clicked = process_email(email_id, mail, should_click)
                
                if mail_subject and mail_content:
                    processed_emails.append((mail_subject, mail_content))
                    processed_count += 1
                    total_links_clicked += links_clicked
                    
                    # Aktualizujemy wyświetlanie maila
                    with email_container:
                        # Dodaj wskaźnik czy link został kliknięty
                        if should_click and links_clicked > 0:
                            st.subheader(f"Email {i+1}: {mail_subject} ✅ Kliknięto losowy link")
                        elif should_click and links_clicked == 0:
                            st.subheader(f"Email {i+1}: {mail_subject} ⚠️ Planowano kliknięcie, ale nie znaleziono linków")
                        else:
                            st.subheader(f"Email {i+1}: {mail_subject} 📧 Tylko otwarty")
                        
                        st.components.v1.html(mail_content, height=400, scrolling=True)
                        if not delete_success:
                            st.warning("Email został otwarty, ale nie udało się go usunąć")
                        st.divider()
                else:
                    error_count += 1
                    with email_container:
                        st.error(f"Błąd podczas przetwarzania maila {i+1}")
                        st.divider()
                
                # Losowa wartość interwału (±50%)
                if i < emails_to_process - 1:  # Nie czekaj po ostatnim mailu
                    random_interval = interval * (0.5 + random.random())
                    status_text.text(f"Czekam {random_interval:.2f}s przed kolejnym mailem...")
                    time.sleep(random_interval)
            
            # Końcowa informacja o statusie
            if error_count > 0:
                status_text.text(f"Zakończono: przetworzono {processed_count} maili, błędy: {error_count}, kliknięto linki łącznie: {total_links_clicked}")
            else:
                status_text.text(f"Zakończono przetwarzanie {processed_count} maili, kliknięto linki łącznie: {total_links_clicked}")
        
        mail.close()
        mail.logout()
            
        return processed_emails
    except Exception as e:
        st.error(f"Wystąpił błąd podczas otwierania maili: {e}")
        logger.error(f"Error in open_emails_by_subject: {e}")
        return []

def debug_single_email(subject):
    """Funkcja do debugowania pojedynczego maila"""
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
        mail.select("inbox")
        
        email_id = get_first_email_by_subject(mail, subject)
        if email_id:
            debug_info = debug_email_structure(email_id, mail)
            return debug_info
        else:
            st.warning(f"Nie znaleziono maila o temacie '{subject}'")
            return None
            
    except Exception as e:
        st.error(f"Błąd podczas debugowania: {e}")
        return None
    finally:
        try:
            mail.close()
            mail.logout()
        except:
            pass

def check_imap_connection():
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
        mail.logout()
        return True
    except Exception as e:
        logger.error(f"Error connecting to IMAP server: {e}")
        return False

def main():
    st.title("Otwieracz do maili")
    
    # Sprawdź połączenie do serwera IMAP
    connection_status = check_imap_connection()
    
    if not connection_status:
        st.error(f"Nie udało się połączyć z serwerem IMAP ({IMAP_SERVER}:{IMAP_PORT}). Sprawdź ustawienia połączenia.")
    else:
        st.success(f"Połączono z serwerem IMAP: {EMAIL_ACCOUNT}")
    
    subject_to_search = st.text_input("Podaj temat maila")
    
    # Dodaj przycisk do debugowania
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("Sprawdź liczbę maili"):
            if not subject_to_search:
                st.error("Podaj temat maila")
                return
                
            with st.spinner("Sprawdzanie liczby maili..."):
                email_count = count_emails_by_subject(subject_to_search)
                
            st.session_state['email_count'] = email_count
            st.session_state['subject'] = subject_to_search
            
            if email_count > 0:
                st.success(f"Znaleziono {email_count} maili o temacie '{subject_to_search}'")
            else:
                st.warning(f"Nie znaleziono maili o temacie '{subject_to_search}'")
    
    with col2:
        if st.button("Debuguj strukturę maila"):
            if not subject_to_search:
                st.error("Podaj temat maila")
                return
                
            with st.spinner("Analizowanie struktury maila..."):
                debug_single_email(subject_to_search)
    
    if 'email_count' in st.session_state and st.session_state['email_count'] > 0:
        st.subheader("Ustawienia otwierania")
        
        col1, col2 = st.columns(2)
        
        with col1:
            open_all = st.radio("Które maile otworzyć?", ["Wszystkie", "Tylko część"])
        
        with col2:
            if open_all == "Tylko część":
                email_count_to_open = st.number_input("Ile maili otworzyć?", 
                                                     min_value=1, 
                                                     max_value=st.session_state['email_count'], 
                                                     value=min(5, st.session_state['email_count']))
            else:
                email_count_to_open = st.session_state['email_count']
        
        # Nowe ustawienie procentu klikanych maili
        click_percentage = st.slider(
            "Procent maili z klikniętymi linkami", 
            min_value=0, 
            max_value=100, 
            value=100,
            help="Wybierz jaki procent otwieranych maili ma mieć również kliknięte linki. Maile będą wybierane losowo."
        )
        
        # Pokaż ile maili będzie miało kliknięte linki
        emails_to_click = int(email_count_to_open * click_percentage / 100)
        if click_percentage < 100:
            st.info(f"Z {email_count_to_open} maili, linki zostaną kliknięte w {emails_to_click} mailach (wybrane losowo)")
        
        interval = st.slider("Interwał między otwieraniem maili (sekundy)", 
                            min_value=1, 
                            max_value=60, 
                            value=10,
                            help="Faktyczny interwał będzie losowy w zakresie ±50% podanej wartości")
        
        if st.button("Zacznij otwierać maile"):
            if not connection_status:
                st.error("Nie można otworzyć maili z powodu błędu połączenia z serwerem")
                return
                
            with st.spinner("Otwieranie maili..."):
                open_emails_by_subject(
                    st.session_state['subject'], 
                    count=email_count_to_open if open_all == "Tylko część" else None,
                    interval=interval,
                    click_percentage=click_percentage
                )
    
    # Wyświetlanie logów debugowania
    with st.expander("Logi debugowania", expanded=False):
        log_contents = log_buffer.getvalue()
        st.text_area("Logi", log_contents, height=300)
        if st.button("Wyczyść logi"):
            log_buffer.truncate(0)
            log_buffer.seek(0)

if __name__ == "__main__":
    main()