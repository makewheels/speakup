"""Send a concise feature-completion email through a configured provider."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import smtplib
import ssl
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import formatdate, parseaddr
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

if __package__:
    from scripts.feature_email_content import (
        FEATURE_IMAGE_CID,
        FeatureImage,
        FeatureMessage,
        NotificationError,
        load_feature_message,
        message_fingerprint,
        render_html,
        render_text,
    )
else:
    from feature_email_content import (
        FEATURE_IMAGE_CID,
        FeatureImage,
        FeatureMessage,
        NotificationError,
        load_feature_message,
        message_fingerprint,
        render_html,
        render_text,
    )

RESEND_EMAILS_URL = "https://api.resend.com/emails"
RequestFn = Callable[..., Any]
SmtpFactory = Callable[..., Any]


@dataclass(frozen=True)
class DeliveryConfig:
    provider: str
    sender_name: str
    sender_address: str
    recipients: tuple[str, ...]
    notification_id: str
    resend_api_key: str | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_username: str | None = None
    smtp_password: str | None = None


def _require_config_values(environ: Mapping[str, str], names: tuple[str, ...]) -> dict[str, str]:
    missing = [name for name in names if not environ.get(name, "").strip()]
    if missing:
        joined_names = "、".join(missing)
        raise NotificationError(
            f"缺少必要环境变量：{joined_names}；请在 Infisical 的 /notifications 路径配置后重试。"
        )
    return {name: environ[name].strip() for name in names}


def _valid_email(value: str, *, allow_display_name: bool) -> bool:
    display_name, address = parseaddr(value)
    if not address or address.count("@") != 1 or any(char.isspace() for char in address):
        return False
    local_part, domain = address.rsplit("@", 1)
    if not local_part or "." not in domain or domain.startswith(".") or domain.endswith("."):
        return False
    return allow_display_name or (not display_name and address == value)


def _parse_recipients(raw_value: str) -> tuple[str, ...]:
    recipients = tuple(part.strip() for part in re.split(r"[,;\n]+", raw_value) if part.strip())
    if not recipients:
        raise NotificationError("FEATURE_MAIL_TO 未包含有效收件人；未发送任何邮件。")
    if any(not _valid_email(recipient, allow_display_name=False) for recipient in recipients):
        raise NotificationError("FEATURE_MAIL_TO 包含格式无效的地址；未发送任何邮件。")
    if len({recipient.casefold() for recipient in recipients}) != len(recipients):
        raise NotificationError("FEATURE_MAIL_TO 包含重复地址；未发送任何邮件。")
    return recipients


def _parse_smtp_port(raw_value: str) -> int:
    try:
        port = int(raw_value)
    except ValueError:
        raise NotificationError("SMTP_PORT 必须是 1 到 65535 之间的整数；未发送任何邮件。") from None
    if not 1 <= port <= 65_535:
        raise NotificationError("SMTP_PORT 必须是 1 到 65535 之间的整数；未发送任何邮件。")
    return port


def _validate_sender(name: str, address: str) -> None:
    if not name or len(name) > 80 or "\n" in name or "\r" in name:
        raise NotificationError("MAIL_FROM_NAME 必须是 80 个字符以内的单行文字；未发送任何邮件。")
    if not _valid_email(address, allow_display_name=False):
        raise NotificationError("MAIL_FROM_ADDRESS 格式无效；未发送任何邮件。")


def _base_delivery_values(environ: Mapping[str, str]) -> tuple[dict[str, str], tuple[str, ...], str]:
    values = _require_config_values(
        environ,
        ("EMAIL_PROVIDER", "MAIL_FROM_NAME", "MAIL_FROM_ADDRESS", "FEATURE_MAIL_TO"),
    )
    _validate_sender(values["MAIL_FROM_NAME"], values["MAIL_FROM_ADDRESS"])
    recipients = _parse_recipients(values["FEATURE_MAIL_TO"])
    notification_id = environ.get("FEATURE_MAIL_NOTIFICATION_ID", "").strip() or "manual"
    return values, recipients, notification_id


def load_delivery_config(environ: Mapping[str, str]) -> DeliveryConfig:
    values, recipients, notification_id = _base_delivery_values(environ)
    provider = values["EMAIL_PROVIDER"].lower()
    common = {
        "provider": provider,
        "sender_name": values["MAIL_FROM_NAME"],
        "sender_address": values["MAIL_FROM_ADDRESS"],
        "recipients": recipients,
        "notification_id": notification_id,
    }
    if provider == "smtp":
        smtp_values = _require_config_values(
            environ,
            ("SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD"),
        )
        if not re.fullmatch(r"[A-Za-z0-9.-]{1,253}", smtp_values["SMTP_HOST"]):
            raise NotificationError("SMTP_HOST 格式无效；未发送任何邮件。")
        return DeliveryConfig(
            **common,
            smtp_host=smtp_values["SMTP_HOST"],
            smtp_port=_parse_smtp_port(smtp_values["SMTP_PORT"]),
            smtp_username=smtp_values["SMTP_USERNAME"],
            smtp_password=smtp_values["SMTP_PASSWORD"],
        )
    if provider == "resend":
        resend_values = _require_config_values(environ, ("RESEND_API_KEY",))
        return DeliveryConfig(**common, resend_api_key=resend_values["RESEND_API_KEY"])
    raise NotificationError("EMAIL_PROVIDER 仅支持 smtp 或 resend；未发送任何邮件。")


def _idempotency_key(notification_id: str, recipient: str, message: FeatureMessage) -> str:
    digest = hashlib.sha256(
        f"{notification_id}\0{recipient}\0{message_fingerprint(message)}".encode()
    ).hexdigest()
    return f"speakup-feature/{digest}"


def _resend_error(error: HTTPError) -> NotificationError:
    code = "unknown"
    try:
        payload = json.loads(error.read(8_192).decode("utf-8", errors="replace"))
        candidate = payload.get("name") or payload.get("code")
        if isinstance(candidate, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", candidate):
            code = candidate
    except (AttributeError, json.JSONDecodeError, OSError):
        pass
    return NotificationError(f"Resend 请求失败（HTTP {error.code}，错误类型 {code}）；未输出邮件配置。")


def _sender_header(config: DeliveryConfig) -> str:
    return str(Address(display_name=config.sender_name, addr_spec=config.sender_address))


def _send_with_resend(
    config: DeliveryConfig,
    message: FeatureMessage,
    *,
    request_fn: RequestFn = urlopen,
    timeout_seconds: float = 20,
) -> int:
    if not config.resend_api_key:
        raise NotificationError("Resend 配置不完整；未发送任何邮件。")
    html_body = render_html(message)
    text_body = render_text(message)
    subject = f"SpeakUp 已更新｜{message.title}"
    sent_count = 0

    for recipient in config.recipients:
        payload: dict[str, Any] = {
            "from": _sender_header(config),
            "to": [recipient],
            "subject": subject,
            "html": html_body,
            "text": text_body,
            "tags": [
                {"name": "project", "value": "speakup"},
                {"name": "type", "value": "feature_complete"},
            ],
        }
        if message.image:
            payload["attachments"] = [_resend_attachment(message.image)]
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            RESEND_EMAILS_URL,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {config.resend_api_key}",
                "Content-Type": "application/json",
                "Idempotency-Key": _idempotency_key(config.notification_id, recipient, message),
                "User-Agent": "speakup-feature-notifier/1.0",
            },
        )
        try:
            with request_fn(request, timeout=timeout_seconds) as response:
                status = getattr(response, "status", 200)
                response.read()
        except HTTPError as error:
            raise _resend_error(error) from None
        except (TimeoutError, URLError, OSError) as error:
            raise NotificationError(f"连接 Resend 失败（{type(error).__name__}）；可安全重试本次工作流。") from None
        if not 200 <= status < 300:
            raise NotificationError(f"Resend 返回非成功状态 HTTP {status}；可安全重试本次工作流。")
        sent_count += 1

    return sent_count


def _resend_attachment(image: FeatureImage) -> dict[str, str]:
    return {
        "content": base64.b64encode(image.content).decode("ascii"),
        "filename": image.filename,
        "content_type": image.content_type,
        "content_id": FEATURE_IMAGE_CID,
    }


def _build_smtp_message(config: DeliveryConfig, message: FeatureMessage) -> EmailMessage:
    email_message = EmailMessage()
    email_message["Subject"] = f"SpeakUp 已更新｜{message.title}"
    email_message["From"] = Address(display_name=config.sender_name, addr_spec=config.sender_address)
    email_message["To"] = "undisclosed-recipients:;"
    email_message["Date"] = formatdate(localtime=False)
    message_id_source = f"{config.notification_id}\0{message_fingerprint(message)}"
    message_id = hashlib.sha256(message_id_source.encode()).hexdigest()
    sender_domain = config.sender_address.rsplit("@", 1)[1]
    email_message["Message-ID"] = f"<speakup-feature-{message_id}@{sender_domain}>"
    email_message.set_content(render_text(message))
    email_message.add_alternative(render_html(message), subtype="html")
    if message.image:
        html_part = email_message.get_payload()[-1]
        image_subtype = message.image.content_type.split("/", 1)[1]
        html_part.add_related(
            message.image.content,
            maintype="image",
            subtype=image_subtype,
            cid=f"<{FEATURE_IMAGE_CID}>",
            filename=message.image.filename,
            disposition="inline",
        )
    return email_message


def _smtp_response_error(error: smtplib.SMTPResponseException) -> NotificationError:
    return NotificationError(
        f"SMTP 服务返回失败状态 {error.smtp_code}（{type(error).__name__}）；未输出邮件配置。"
    )


def _send_with_smtp(
    config: DeliveryConfig,
    message: FeatureMessage,
    *,
    smtp_factory: SmtpFactory = smtplib.SMTP_SSL,
    timeout_seconds: float = 20,
) -> int:
    if not all((config.smtp_host, config.smtp_port, config.smtp_username, config.smtp_password)):
        raise NotificationError("SMTP 配置不完整；未发送任何邮件。")
    email_message = _build_smtp_message(config, message)
    try:
        with smtp_factory(
            config.smtp_host,
            config.smtp_port,
            timeout=timeout_seconds,
            context=ssl.create_default_context(),
        ) as smtp:
            smtp.login(config.smtp_username, config.smtp_password)
            refused = smtp.send_message(
                email_message,
                from_addr=config.sender_address,
                to_addrs=list(config.recipients),
            )
    except smtplib.SMTPRecipientsRefused as error:
        raise NotificationError(f"SMTP 拒绝了 {len(error.recipients)} 个收件人；未输出邮件配置。") from None
    except smtplib.SMTPResponseException as error:
        raise _smtp_response_error(error) from None
    except (smtplib.SMTPException, TimeoutError, OSError) as error:
        raise NotificationError(f"SMTP 连接或发送失败（{type(error).__name__}）；未输出邮件配置。") from None
    if refused:
        raise NotificationError(f"SMTP 未接受 {len(refused)} 个收件人；未输出邮件配置。")
    return len(config.recipients)


def send_feature_email(
    config: DeliveryConfig,
    message: FeatureMessage,
    *,
    request_fn: RequestFn = urlopen,
    smtp_factory: SmtpFactory = smtplib.SMTP_SSL,
    timeout_seconds: float = 20,
) -> int:
    if config.provider == "smtp":
        return _send_with_smtp(
            config,
            message,
            smtp_factory=smtp_factory,
            timeout_seconds=timeout_seconds,
        )
    if config.provider == "resend":
        return _send_with_resend(
            config,
            message,
            request_fn=request_fn,
            timeout_seconds=timeout_seconds,
        )
    raise NotificationError("邮件 provider 未受支持；未发送任何邮件。")


def main(
    *,
    environ: Mapping[str, str] | None = None,
    request_fn: RequestFn = urlopen,
    smtp_factory: SmtpFactory = smtplib.SMTP_SSL,
) -> int:
    current_environ = os.environ if environ is None else environ
    try:
        message = load_feature_message(current_environ)
        config = load_delivery_config(current_environ)
        sent_count = send_feature_email(
            config,
            message,
            request_fn=request_fn,
            smtp_factory=smtp_factory,
        )
    except NotificationError as error:
        print(f"功能通知发送失败：{error}", file=sys.stderr)
        return 1

    print(f"功能通知发送成功：共发送 {sent_count} 封。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
