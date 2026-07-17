import imaplib
import email
from email.header import decode_header
import re
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)

def decode_mime_words(s):
    """Decode MIME encoded words in a string."""
    if s is None:
        return ''
    decoded_parts = decode_header(s)
    decoded_string = ''
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            if encoding:
                decoded_string += part.decode(encoding)
            else:
                decoded_string += part.decode('utf-8', errors='ignore')
        else:
            decoded_string += part
    return decoded_string

def get_text_content(msg) -> str:
    """Extract plain text content from an email message."""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get('Content-Disposition'))
            # Skip attachments
            if 'attachment' in content_disposition:
                continue
            if content_type == 'text/plain':
                charset = part.get_content_charset() or 'utf-8'
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        return payload.decode(charset, errors='ignore')
                except Exception:
                    continue
            elif content_type == 'text/html':
                # We'll keep the HTML as a fallback if no plain text is found
                charset = part.get_content_charset() or 'utf-8'
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        html = payload.decode(charset, errors='ignore')
                        # Simple HTML to text: remove tags and extra whitespace
                        text = re.sub('<[^<]+?>', '', html)
                        text = re.sub(r'\s+', ' ', text).strip()
                        return text
                except Exception:
                    continue
        # If we didn't find any plain text, return empty string
        return ''
    else:
        # Not multipart
        content_type = msg.get_content_type()
        charset = msg.get_content_charset() or 'utf-8'
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                if content_type == 'text/plain':
                    return payload.decode(charset, errors='ignore')
                elif content_type == 'text/html':
                    html = payload.decode(charset, errors='ignore')
                    text = re.sub('<[^<]+?>', '', html)
                    text = re.sub(r'\s+', ' ', text).strip()
                    return text
        except Exception:
            pass
        return ''

class IMAPClient:
    def __init__(self, server: str, port: int, username: str, password: str, folder: str = 'INBOX'):
        self.server = server
        self.port = port
        self.username = username
        self.password = password
        self.folder = folder
        self.conn = None

    def connect(self):
        """Establish a connection to the IMAP server."""
        try:
            if self.port == 993:
                self.conn = imaplib.IMAP4_SSL(self.server, self.port)
            else:
                self.conn = imaplib.IMAP4(self.server, self.port)
                self.conn.starttls()  # Try to upgrade to TLS if supported
            self.conn.login(self.username, self.password)
            self.conn.select(self.folder)
            return True
        except Exception as e:
            logger.error(f"Failed to connect to IMAP server: {e}")
            self.conn = None
            return False

    def logout(self):
        """Log out and close the connection."""
        if self.conn:
            try:
                self.conn.close()
                self.conn.logout()
            except Exception:
                pass
            self.conn = None

    def fetch_emails(self, limit: int = None) -> List[Dict]:
        """
        Fetch emails from the selected folder.
        Returns a list of dictionaries with keys:
            message_id, sender, subject, date, snippet
        If limit is provided, only the most recent 'limit' emails are returned.
        """
        if not self.conn:
            if not self.connect():
                return []

        try:
            # Search for all emails
            typ, data = self.conn.search(None, 'ALL')
            if typ != 'OK':
                logger.error("Failed to search emails")
                return []

            email_ids = data[0].split()
            # If we want to limit, take the last 'limit' emails (most recent)
            if limit is not None:
                email_ids = email_ids[-limit:]

            emails = []
            for num in email_ids:
                typ, msg_data = self.conn.fetch(num, '(RFC822)')
                if typ != 'OK':
                    continue
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        # Extract headers
                        subject = decode_mime_words(msg['Subject'])
                        sender = decode_mime_words(msg['From'])
                        date_str = msg['Date']
                        message_id = msg['Message-ID']
                        if message_id:
                            message_id = message_id.strip('<>')
                        # Get the body snippet
                        snippet = get_text_content(msg)
                        # Limit snippet to 200 characters
                        if len(snippet) > 200:
                            snippet = snippet[:200] + '...'
                        emails.append({
                            'message_id': message_id,
                            'sender': sender,
                            'subject': subject,
                            'date': date_str,
                            'snippet': snippet
                        })
            return emails
        except Exception as e:
            logger.error(f"Error fetching emails: {e}")
            return []
        finally:
            # We'll log out after fetching to keep things simple.
            self.logout()

    # Optional: method to fetch only unseen emails
    def fetch_unseen_emails(self) -> List[Dict]:
        if not self.conn:
            if not self.connect():
                return []
        try:
            typ, data = self.conn.search(None, 'UNSEEN')
            if typ != 'OK':
                return []
            email_ids = data[0].split()
            emails = []
            for num in email_ids:
                typ, msg_data = self.conn.fetch(num, '(RFC822)')
                if typ != 'OK':
                    continue
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        subject = decode_mime_words(msg['Subject'])
                        sender = decode_mime_words(msg['From'])
                        date_str = msg['Date']
                        message_id = msg['Message-ID']
                        if message_id:
                            message_id = message_id.strip('<>')
                        snippet = get_text_content(msg)
                        if len(snippet) > 200:
                            snippet = snippet[:200] + '...'
                        emails.append({
                            'message_id': message_id,
                            'sender': sender,
                            'subject': subject,
                            'date': date_str,
                            'snippet': snippet
                        })
            return emails
        except Exception as e:
            logger.error(f"Error fetching unseen emails: {e}")
            return []
        finally:
            self.logout()