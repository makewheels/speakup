"""Validate and render feature-email content, including an optional inline SVG."""

from __future__ import annotations

import hashlib
import html
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

MAX_POINTS = 6
MAX_IMAGE_BYTES = 2 * 1024 * 1024
FEATURE_IMAGE_CID = "speakup-feature-image"
FEATURE_REPO_ROOT = Path(__file__).resolve().parents[1]
FEATURE_IMAGE_ROOT = FEATURE_REPO_ROOT / "docs/assets/feature-notifications"


class NotificationError(Exception):
    """A safe, user-facing notification failure."""


@dataclass(frozen=True)
class FeatureImage:
    content: bytes
    content_type: str
    filename: str
    alt: str


@dataclass(frozen=True)
class FeatureMessage:
    title: str
    summary: str
    points: tuple[str, ...]
    view_url: str | None
    image: FeatureImage | None = None


def _required(environ: Mapping[str, str], name: str) -> str:
    value = environ.get(name, "").strip()
    if not value:
        raise NotificationError(
            f"缺少必要环境变量 {name}；请在 Infisical 的 /notifications 路径配置后重试。"
        )
    return value


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


_DANGEROUS_SVG = re.compile(
    r"<(?:script|foreignObject|iframe|object|embed|audio|video)\b"
    r"|\bon[a-z]+\s*="
    r"|(?:href|src)\s*=\s*['\"]\s*(?:https?:|//|data:)"
    r"|url\s*\(\s*['\"]?\s*(?:https?:|//|data:)"
    r"|<!DOCTYPE|<!ENTITY",
    flags=re.IGNORECASE,
)


def _validate_svg(content: bytes) -> bool:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return False
    stripped = text.lstrip("\ufeff\t\r\n ")
    if not (stripped.startswith("<svg") or stripped.startswith("<?xml")):
        return False
    if "<svg" not in stripped[:500] or _DANGEROUS_SVG.search(text):
        return False
    return True


def _load_feature_image(environ: Mapping[str, str]) -> FeatureImage | None:
    raw_path = environ.get("FEATURE_MAIL_IMAGE_PATH", "").strip()
    if not raw_path:
        return None
    path = Path(raw_path)
    if path.is_absolute():
        raise NotificationError("功能截图路径必须是仓库内相对路径；未发送任何邮件。")
    root = FEATURE_IMAGE_ROOT.resolve()
    resolved = (FEATURE_REPO_ROOT / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise NotificationError("功能截图只能来自 docs/assets/feature-notifications；未发送任何邮件。") from None
    if not resolved.is_file():
        raise NotificationError("功能截图不存在；未发送任何邮件。")
    with resolved.open("rb") as image_file:
        content = image_file.read(MAX_IMAGE_BYTES + 1)
    if not content:
        raise NotificationError("功能截图不能为空；未发送任何邮件。")
    if len(content) > MAX_IMAGE_BYTES:
        raise NotificationError("功能截图不能超过 2 MB；未发送任何邮件。")
    if resolved.suffix.lower() != ".svg" or not _validate_svg(content):
        raise NotificationError("功能说明图仅支持不含脚本或外部资源的安全 SVG；未发送任何邮件。")
    content_type, extension = "image/svg+xml", "svg"
    alt = environ.get("FEATURE_MAIL_IMAGE_ALT", "").strip() or "功能说明图"
    if len(alt) > 120 or "\n" in alt or "\r" in alt:
        raise NotificationError("功能说明图描述必须是 120 个字符以内的单行文字。")
    return FeatureImage(
        content=content,
        content_type=content_type,
        filename=f"speakup-feature.{extension}",
        alt=alt,
    )


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
        image=_load_feature_image(environ),
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
              <td width="28" valign="top" style="padding:0 0 12px 0;color:#2563eb;font-size:18px;line-height:24px;">&#10003;</td>
              <td valign="top" style="padding:0 0 12px 0;color:#25324b;font-size:15px;line-height:24px;">{_html_text(point)}</td>
            </tr>
            """
        )
    return f"""
      <tr>
        <td style="padding:0 28px 22px 28px;">
          <div style="padding:0 0 12px 0;color:#64748b;font-size:12px;font-weight:700;letter-spacing:1px;">本次完成</div>
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">{''.join(rows)}</table>
        </td>
      </tr>
    """


def _image_html(image: FeatureImage | None) -> str:
    if not image:
        return ""
    return f"""
      <tr>
        <td style="padding:0 28px 24px 28px;">
          <div style="padding:0 0 10px 0;color:#64748b;font-size:12px;font-weight:700;letter-spacing:1px;">界面预览</div>
          <img src="cid:{FEATURE_IMAGE_CID}" alt="{html.escape(image.alt, quote=True)}" width="544"
               style="display:block;width:100%;max-width:544px;height:auto;border:1px solid #e6ebf2;border-radius:12px;">
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
          <table role="presentation" cellspacing="0" cellpadding="0" border="0"><tr>
            <td bgcolor="#2563eb" style="border-radius:10px;">
              <a href="{escaped_url}" style="display:inline-block;padding:12px 20px;color:#ffffff;font-size:15px;font-weight:700;line-height:20px;text-decoration:none;">查看详情</a>
            </td>
          </tr></table>
        </td>
      </tr>
    """


def render_html(message: FeatureMessage) -> str:
    title = _html_text(message.title)
    summary = _html_text(message.summary)
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title></head>
  <body style="margin:0;padding:0;background-color:#f3f6fb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',Arial,sans-serif;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">SpeakUp 已完成一项功能更新。</div>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" bgcolor="#f3f6fb"><tr>
      <td align="center" style="padding:24px 12px;">
        <table role="presentation" width="600" cellspacing="0" cellpadding="0" border="0" style="width:100%;max-width:600px;background-color:#ffffff;border:1px solid #e6ebf2;border-radius:16px;overflow:hidden;">
          <tr><td bgcolor="#172554" style="padding:24px 28px;color:#ffffff;"><div style="font-size:13px;font-weight:700;letter-spacing:1.2px;opacity:0.78;">SPEAKUP · 功能更新</div><div style="padding-top:10px;font-size:24px;font-weight:800;line-height:32px;">{title}</div></td></tr>
          <tr><td style="padding:26px 28px 22px 28px;color:#334155;font-size:16px;line-height:27px;">{summary}</td></tr>
          {_image_html(message.image)}
          {_points_html(message.points)}
          {_link_html(message.view_url)}
          <tr><td style="padding:18px 28px;background-color:#f8fafc;border-top:1px solid #edf1f5;color:#8491a7;font-size:12px;line-height:19px;">这是一封由 SpeakUp 工作流发送的功能完成通知。</td></tr>
        </table>
      </td>
    </tr></table>
  </body>
</html>
"""


def render_text(message: FeatureMessage) -> str:
    lines = [f"SpeakUp 功能更新：{message.title}", "", message.summary]
    if message.image:
        lines.extend(["", f"邮件中附有功能说明图：{message.image.alt}"])
    if message.points:
        lines.extend(["", "本次完成：", *(f"- {point}" for point in message.points)])
    if message.view_url:
        lines.extend(["", f"查看详情：{message.view_url}"])
    lines.extend(["", "这是一封由 SpeakUp 工作流发送的功能完成通知。"])
    return "\n".join(lines)


def message_fingerprint(message: FeatureMessage) -> str:
    image_digest = hashlib.sha256(message.image.content).hexdigest() if message.image else ""
    content = "\0".join(
        (message.title, message.summary, *message.points, message.view_url or "", image_digest)
    )
    return hashlib.sha256(content.encode()).hexdigest()
