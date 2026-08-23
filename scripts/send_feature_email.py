"""Send a concise feature-completion email through a configured provider."""

from __future__ import annotations

import hashlib
import html
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
from urllib.parse import urlparse
from urllib.request import Request, urlopen

RESEND_EMAILS_URL = "https://api.resend.com/emails"
MAX_POINTS = 6
RequestFn = Callable[..., Any]
SmtpFactory = Callable[..., Any]


class NotificationError(Exception):
    """A safe, user-facing notification failure."""


@dataclass(frozen=True)
class FeatureMessage:
    title: str
    summary: str
    points: tuple[str, ...]
    view_url: str | None


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


def _required(environ: Mapping[str, str], name: str) -> str:
    value = environ.get(name, "").strip()
    if not value:
        raise NotificationError(
            f"缺少必要环境变量 {name}；请在 Infisical 的 /notifications 路径配置后重试。"
        )
    return value


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


def _clean_points(raw_value: str) -> tuple[str, ...]:
    points = []
    for raw_line in raw_value.splitlines():
        point = re.sub(r"^(?:[-*•]\s+|\d+[.)]\s+)", "", raw_line.strip())
        if point:
            points.append(point)
    if len(points) > MAX_POINTS:
        raise NotificationError(f"功能点最多 {MAX_POINTS} 条；请精简后重试。")
    if any(len(point) > 220 for point in points):
        raise NotificationError("单条功能点不能超过 220 个字符；请精简后重试。")
    return tuple(points)


def _validate_view_url(raw_value: str) -> str | None:
    value = raw_value.strip()
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise NotificationError("查看链接必须是无内嵌凭据的 HTTP(S) 地址；未发送任何邮件。")
    if len(value) > 2_000:
        raise NotificationError("查看链接过长；未发送任何邮件。")
    return value


def load_feature_message(environ: Mapping[str, str]) -> FeatureMessage:
    title = _required(environ, "FEATURE_MAIL_TITLE")
    summary = _required(environ, "FEATURE_MAIL_SUMMARY")
    if "\n" in title or "\r" in title or len(title) > 120:
        raise NotificationError("标题必须是 120 个字符以内的单行文字。")
    if len(summary) > 1_200:
        raise NotificationError("简述不能超过 1200 个字符；请精简后重试。")
    return FeatureMessage(
        title=title,
        summary=summary,
        points=_clean_points(environ.get("FEATURE_MAIL_POINTS", "")),
        view_url=_validate_view_url(environ.get("FEATURE_MAIL_VIEW_URL", "")),
    )


def _html_text(value: str) -> str:
    return "<br>".join(html.escape(line, quote=True) for line in value.splitlines())


def _points_html(points: tuple[str, ...]) -> str:
    if not points:
        return ""
    rows = []
    for point in points:
        rows.append(
            f"""
            <tr>
              <td width="28" valign="top" style="padding:0 0 12px 0;color:#2563eb;font-size:18px;line-height:24px;">
                &#10003;
              </td>
              <td valign="top" style="padding:0 0 12px 0;color:#25324b;font-size:15px;line-height:24px;">
                {_html_text(point)}
              </td>
            </tr>
            """
        )
    return f"""
      <tr>
        <td style="padding:0 28px 22px 28px;">
          <div style="padding:0 0 12px 0;color:#64748b;font-size:12px;font-weight:700;letter-spacing:1px;">
            本次完成
          </div>
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
            {''.join(rows)}
          </table>
        </td>
      </tr>
    """


def _link_html(view_url: str | None) -> str:
    if not view_url:
        return ""
    escaped_url = html.escape(view_url, quote=True)
    return f"""
      <tr>
        <td style="padding:2px 28px 30px 28px;">
          <table role="presentation" cellspacing="0" cellpadding="0" border="0">
            <tr>
              <td bgcolor="#2563eb" style="border-radius:10px;">
                <a href="{escaped_url}"
                   style="display:inline-block;padding:12px 20px;color:#ffffff;font-size:15px;
                          font-weight:700;line-height:20px;text-decoration:none;">
                  查看详情
                </a>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    """


def render_html(message: FeatureMessage) -> str:
    title = _html_text(message.title)
    summary = _html_text(message.summary)
    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title}</title>
  </head>
  <body style="margin:0;padding:0;background-color:#f3f6fb;
               font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC',
                           'Microsoft YaHei',Arial,sans-serif;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">
      SpeakUp 已完成一项功能更新。
    </div>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" bgcolor="#f3f6fb">
      <tr>
        <td align="center" style="padding:24px 12px;">
          <table role="presentation" width="600" cellspacing="0" cellpadding="0" border="0"
                 style="width:100%;max-width:600px;background-color:#ffffff;
                        border:1px solid #e6ebf2;border-radius:16px;overflow:hidden;">
            <tr>
              <td bgcolor="#172554" style="padding:24px 28px;color:#ffffff;">
                <div style="font-size:13px;font-weight:700;letter-spacing:1.2px;opacity:0.78;">SPEAKUP · 功能更新</div>
                <div style="padding-top:10px;font-size:24px;font-weight:800;line-height:32px;">{title}</div>
              </td>
            </tr>
            <tr>
              <td style="padding:26px 28px 22px 28px;color:#334155;font-size:16px;line-height:27px;">
                {summary}
              </td>
            </tr>
            {_points_html(message.points)}
            {_link_html(message.view_url)}
            <tr>
              <td style="padding:18px 28px;background-color:#f8fafc;border-top:1px solid #edf1f5;
                         color:#8491a7;font-size:12px;line-height:19px;">
                这是一封由 SpeakUp 工作流发送的功能完成通知。
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""


def render_text(message: FeatureMessage) -> str:
    lines = [f"SpeakUp 功能更新：{message.title}", "", message.summary]
    if message.points:
        lines.extend(["", "本次完成：", *(f"- {point}" for point in message.points)])
    if message.view_url:
        lines.extend(["", f"查看详情：{message.view_url}"])
    lines.extend(["", "这是一封由 SpeakUp 工作流发送的功能完成通知。"])
    return "\n".join(lines)


def _message_fingerprint(message: FeatureMessage) -> str:
    content = "\0".join((message.title, message.summary, *message.points, message.view_url or ""))
    return hashlib.sha256(content.encode()).hexdigest()


def _idempotency_key(notification_id: str, recipient: str, message: FeatureMessage) -> str:
    digest = hashlib.sha256(
        f"{notification_id}\0{recipient}\0{_message_fingerprint(message)}".encode()
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
        body = json.dumps(
            {
                "from": _sender_header(config),
                "to": [recipient],
                "subject": subject,
                "html": html_body,
                "text": text_body,
                "tags": [
                    {"name": "project", "value": "speakup"},
                    {"name": "type", "value": "feature_complete"},
                ],
            },
            ensure_ascii=False,
        ).encode("utf-8")
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


def _build_smtp_message(config: DeliveryConfig, message: FeatureMessage) -> EmailMessage:
    email_message = EmailMessage()
    email_message["Subject"] = f"SpeakUp 已更新｜{message.title}"
    email_message["From"] = Address(display_name=config.sender_name, addr_spec=config.sender_address)
    email_message["To"] = "undisclosed-recipients:;"
    email_message["Date"] = formatdate(localtime=False)
    message_id_source = f"{config.notification_id}\0{_message_fingerprint(message)}"
    message_id = hashlib.sha256(message_id_source.encode()).hexdigest()
    sender_domain = config.sender_address.rsplit("@", 1)[1]
    email_message["Message-ID"] = f"<speakup-feature-{message_id}@{sender_domain}>"
    email_message.set_content(render_text(message))
    email_message.add_alternative(render_html(message), subtype="html")
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
