"""
Утилиты для работы с электронной почтой
"""
from typing import List, Dict, Any, Optional
import smtplib
import imaplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class EmailConfig:
    """Конфигурация для подключения к почте"""
    smtp_server: str
    smtp_port: int
    imap_server: str
    imap_port: int
    username: str
    password: str
    use_tls: bool = True


@dataclass
class EmailMessage:
    """Структура email сообщения"""
    to: List[str]
    subject: str
    body: str
    attachments: Optional[List[str]] = None
    cc: Optional[List[str]] = None
    bcc: Optional[List[str]] = None


class EmailSender:
    """Класс для отправки email"""
    
    def __init__(self, config: EmailConfig):
        self.config = config
    
    def send_email(self, message: EmailMessage) -> bool:
        """
        Отправляет email сообщение
        """
        try:
            msg = MIMEMultipart()
            msg['From'] = self.config.username
            msg['To'] = ', '.join(message.to)
            msg['Subject'] = message.subject
            
            if message.cc:
                msg['Cc'] = ', '.join(message.cc)
            
            # Добавляем текст письма
            msg.attach(MIMEText(message.body, 'plain', 'utf-8'))
            
            # Добавляем вложения
            if message.attachments:
                for file_path in message.attachments:
                    self._attach_file(msg, file_path)
            
            # Отправляем письмо
            with smtplib.SMTP(self.config.smtp_server, self.config.smtp_port) as server:
                if self.config.use_tls:
                    server.starttls()
                server.login(self.config.username, self.config.password)
                
                recipients = message.to + (message.cc or []) + (message.bcc or [])
                server.send_message(msg, to_addrs=recipients)
            
            # Логируем время отправки в московском часовом поясе
            from django.utils import timezone
            import pytz
            
            moscow_tz = pytz.timezone('Europe/Moscow')
            moscow_time = timezone.now().astimezone(moscow_tz)
            
            logger.info(f"Email sent successfully to {message.to} at {moscow_time.strftime('%d.%m.%Y %H:%M')} MSK")
            return True
            
        except Exception as e:
            logger.error(f"Error sending email: {str(e)}")
            return False
    
    def _attach_file(self, msg: MIMEMultipart, file_path: str) -> None:
        """Прикрепляет файл к сообщению"""
        try:
            with open(file_path, 'rb') as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())
            
            encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename= {file_path.split("/")[-1]}'
            )
            msg.attach(part)
            
        except Exception as e:
            logger.error(f"Error attaching file {file_path}: {str(e)}")


class EmailReceiver:
    """Класс для получения и обработки входящих писем"""
    
    def __init__(self, config: EmailConfig):
        self.config = config
    
    def check_new_emails(self, folder: str = 'INBOX') -> List[Dict[str, Any]]:
        """
        Проверяет новые письма в указанной папке
        """
        try:
            with imaplib.IMAP4_SSL(self.config.imap_server, self.config.imap_port) as mail:
                mail.login(self.config.username, self.config.password)
                mail.select(folder)
                
                # Ищем непрочитанные письма
                status, messages = mail.search(None, 'UNSEEN')
                
                emails = []
                for msg_id in messages[0].split():
                    email_data = self._parse_email(mail, msg_id)
                    if email_data:
                        emails.append(email_data)
                
                logger.info(f"Found {len(emails)} new emails")
                return emails
                
        except Exception as e:
            logger.error(f"Error checking emails: {str(e)}")
            return []
    
    def _parse_email(self, mail: imaplib.IMAP4_SSL, msg_id: bytes) -> Optional[Dict[str, Any]]:
        """Парсит отдельное email сообщение"""
        try:
            status, msg_data = mail.fetch(msg_id, '(RFC822)')
            email_body = msg_data[0][1]
            email_message = email.message_from_bytes(email_body)
            
            return {
                'id': msg_id.decode(),
                'from': email_message['From'],
                'to': email_message['To'],
                'subject': email_message['Subject'],
                'date': email_message['Date'],
                'body': self._get_email_body(email_message),
                'attachments': self._get_attachments(email_message)
            }
            
        except Exception as e:
            logger.error(f"Error parsing email {msg_id}: {str(e)}")
            return None
    
    def _get_email_body(self, email_message) -> str:
        """Извлекает текст письма"""
        body = ""
        if email_message.is_multipart():
            for part in email_message.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode('utf-8')
                    break
        else:
            body = email_message.get_payload(decode=True).decode('utf-8')
        return body
    
    def _get_attachments(self, email_message) -> List[str]:
        """Извлекает список вложений"""
        attachments = []
        for part in email_message.walk():
            if part.get_content_disposition() == 'attachment':
                filename = part.get_filename()
                if filename:
                    attachments.append(filename)
        return attachments