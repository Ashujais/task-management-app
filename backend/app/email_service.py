import base64
import logging
from email.message import EmailMessage

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

LOGGER = logging.getLogger(__name__)
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.send"


class GmailService:
    def __init__(self, client_id, client_secret, refresh_token, sender):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.sender = sender

    @property
    def configured(self):
        return all([self.client_id, self.client_secret, self.refresh_token, self.sender])

    def send(self, recipient, subject, body):
        if not self.configured:
            raise RuntimeError("Gmail API is not configured")
        credentials = Credentials(
            token=None,
            refresh_token=self.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=[GMAIL_SCOPE],
        )
        message = EmailMessage()
        message["To"] = recipient
        message["From"] = self.sender
        message["Subject"] = subject
        message.set_content(body)
        encoded = base64.urlsafe_b64encode(message.as_bytes()).decode()
        build("gmail", "v1", credentials=credentials, cache_discovery=False).users().messages().send(
            userId="me", body={"raw": encoded}
        ).execute()

    def notify_assignment(self, task, frontend_url):
        body = (
            f"Hello {task['assignee_name']},\n\n"
            f"{task['creator_name']} assigned you a new task.\n\n"
            f"Title: {task['title']}\n"
            f"Description: {task['description'] or 'No description'}\n\n"
            f"Open tasks: {frontend_url}/dashboard\n"
        )
        self.send(task["assignee_email"], "New task assigned to you", body)

    def notify_completion(self, task, completed_by, frontend_url):
        body = (
            f"Hello {task['creator_name']},\n\n"
            f"The task \"{task['title']}\" was completed by {completed_by['name']}.\n"
            f"Completed at: {task['completed_at'].isoformat()}\n\n"
            f"View tasks: {frontend_url}/dashboard\n"
        )
        self.send(task["creator_email"], "Task completed", body)


def send_safely(callback, event_name):
    try:
        callback()
        return True
    except Exception:
        LOGGER.exception("Gmail notification failed for event %s", event_name)
        return False

