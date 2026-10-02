"""
Notification service for Telegram and Email.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional
from .models import NotificationQueue
from .exceptions import NotificationFailed

logger = logging.getLogger(__name__)


@dataclass
class SMTPConfig:
    """SMTP configuration for email notifications."""

    host: str = "smtp.gmail.com"
    port: int = 587
    username: str = ""
    password: str = ""
    from_email: str = "Shift Scheduler <noreply@localhost>"
    use_tls: bool = True


class TelegramProvider:
    """Telegram notification provider using python-telegram-bot."""

    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self._bot = None

    async def _get_bot(self):
        """Lazy initialization of bot."""
        if self._bot is None:
            try:
                from telegram import Bot

                self._bot = Bot(token=self.bot_token)
            except ImportError:
                raise NotificationFailed("python-telegram-bot not installed")
        return self._bot

    async def send_message(self, chat_id: str, message: str) -> bool:
        """Send message to a chat."""
        try:
            bot = await self._get_bot()
            await bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")
            return True
        except Exception as e:
            logger.error(f"Telegram send failed to {chat_id}: {e}")
            return False


class EmailProvider:
    """Email notification provider using aiosmtplib."""

    def __init__(self, config: SMTPConfig):
        self.config = config

    async def send_email(self, to_email: str, subject: str, body: str) -> bool:
        """Send email via SMTP."""
        try:
            import aiosmtplib
            from email.message import EmailMessage

            message = EmailMessage()
            message["From"] = self.config.from_email
            message["To"] = to_email
            message["Subject"] = subject
            message.set_content(body)

            await aiosmtplib.send(
                message,
                hostname=self.config.host,
                port=self.config.port,
                username=self.config.username,
                password=self.config.password,
                start_tls=self.config.use_tls,
            )
            return True
        except Exception as e:
            logger.error(f"Email send failed to {to_email}: {e}")
            return False


class NotificationService:
    """Main notification service with queue processing and retry logic."""

    def __init__(
        self,
        telegram_token: str = "",
        smtp_config: SMTPConfig = None,
        max_retries: int = 3,
        retry_delay: float = 5.0,
    ):
        self.telegram = TelegramProvider(telegram_token) if telegram_token else None
        self.email = EmailProvider(smtp_config) if smtp_config else None
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._queue: list[NotificationQueue] = []
        self._running = False

    def queue_notification(
        self, target_type: str, target_id: str, message: str
    ) -> NotificationQueue:
        """Add notification to queue."""
        notification = NotificationQueue(
            target_type=target_type,
            target_id=target_id,
            message=message,
            status="pending",
            retries=0,
        )
        self._queue.append(notification)
        return notification

    def queue_multiple(
        self, notifications: list[tuple[str, str, str]]
    ) -> list[NotificationQueue]:
        """Queue multiple notifications at once."""
        return [self.queue_notification(t, i, m) for t, i, m in notifications]

    async def _send_notification(self, notification: NotificationQueue) -> bool:
        """Send a single notification based on target type."""
        if notification.target_type == "person_dm" and self.telegram:
            return await self.telegram.send_message(
                notification.target_id, notification.message
            )

        elif (
            notification.target_type in ("team_group", "all_teams_group")
            and self.telegram
        ):
            return await self.telegram.send_message(
                notification.target_id, notification.message
            )

        elif notification.target_type == "email" and self.email:
            # Parse subject from message (first line) or use default
            lines = notification.message.split("\n", 1)
            subject = lines[0] if len(lines) > 1 else "Shift Scheduler Notification"
            body = lines[1] if len(lines) > 1 else notification.message
            return await self.email.send_email(notification.target_id, subject, body)

        else:
            logger.warning(f"No provider for target_type: {notification.target_type}")
            return False

    async def process_queue(self, limit: int = 100) -> dict:
        """Process pending notifications with retry logic."""
        pending = [n for n in self._queue if n.status == "pending"]
        pending = pending[:limit]

        results = {"sent": 0, "failed": 0, "retried": 0}

        for notification in pending:
            success = await self._send_notification(notification)

            if success:
                notification.status = "sent"
                notification.sent_at = __import__("datetime").datetime.now().isoformat()
                results["sent"] += 1
            else:
                notification.retries += 1
                if notification.retries >= self.max_retries:
                    notification.status = "failed"
                    results["failed"] += 1
                else:
                    notification.status = "pending"
                    results["retried"] += 1
                    # Exponential backoff delay
                    await asyncio.sleep(
                        self.retry_delay * (2 ** (notification.retries - 1))
                    )

        return results

    async def start_processor(self, interval: float = 30.0):
        """Start background queue processor."""
        self._running = True
        while self._running:
            await self.process_queue()
            await asyncio.sleep(interval)

    def stop_processor(self):
        """Stop background queue processor."""
        self._running = False

    def get_pending_count(self) -> int:
        """Get count of pending notifications."""
        return len([n for n in self._queue if n.status == "pending"])

    def get_failed_notifications(self) -> list[NotificationQueue]:
        """Get failed notifications for manual retry."""
        return [n for n in self._queue if n.status == "failed"]

    def retry_failed(self, notification_ids: list[int] = None):
        """Reset failed notifications to pending for retry."""
        for notification in self._queue:
            if notification.status == "failed" and (
                notification_ids is None or notification.id in notification_ids
            ):
                notification.status = "pending"
                notification.retries = 0


# Notification message templates
def format_assignment_notification(
    person_name: str, date: str, shift: str, team: str
) -> str:
    return f"📅 <b>New Shift Assignment</b>\n{person_name}: {date} - {shift} shift ({team})"


def format_substitution_notification(
    original_name: str, substitute_name: str, date: str, shift: str, team: str
) -> str:
    return (
        f"🔄 <b>Substitution Made</b>\n"
        f"{original_name} → {substitute_name}\n"
        f"{date} - {shift} shift ({team})"
    )


def format_swap_notification(
    person_a: str, shift_a: str, person_b: str, shift_b: str, date: str
) -> str:
    return (
        f"🔀 <b>Shift Swap Approved</b>\n"
        f"{person_a} ({shift_a}) ↔ {person_b} ({shift_b})\n"
        f"Date: {date}"
    )


def format_schedule_regenerated_notification(
    start_date: str, end_date: str, stats: dict
) -> str:
    return (
        f"📊 <b>Schedule Regenerated</b>\n"
        f"Period: {start_date} to {end_date}\n"
        f"Assignments: {stats.get('assignments', 0)}\n"
        f"Substitutions: {stats.get('substitutions', 0)}\n"
        f"Unfilled: {stats.get('unfilled', 0)}"
    )
