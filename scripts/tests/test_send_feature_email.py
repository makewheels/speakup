from __future__ import annotations

import base64
import io
import json
import smtplib
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from scripts import feature_email_content
from scripts import send_feature_email as emailer


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return b'{"id":"email-id"}'


class FakeSmtp:
    def __init__(self):
        self.login_args = None
        self.message = None
        self.from_addr = None
        self.to_addrs = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def login(self, username, password):
        self.login_args = (username, password)

    def send_message(self, message, *, from_addr, to_addrs):
        self.message = message
        self.from_addr = from_addr
        self.to_addrs = to_addrs
        return {}


def base_environ() -> dict[str, str]:
    return {
        "EMAIL_PROVIDER": "smtp",
        "MAIL_FROM_NAME": "SpeakUp",
        "MAIL_FROM_ADDRESS": "updates@example.com",
        "FEATURE_MAIL_TO": "first@example.net,second@example.org",
        "FEATURE_MAIL_NOTIFICATION_ID": "run-123",
        "FEATURE_MAIL_TITLE": "结果页可以直接分享",
        "FEATURE_MAIL_SUMMARY": "现在练习结束后，可以直接分享本次结果。",
        "FEATURE_MAIL_POINTS": "- 新增分享入口\n- 保留历史页分享",
        "FEATURE_MAIL_VIEW_URL": "https://example.com/result?a=1&b=2",
    }


def smtp_environ() -> dict[str, str]:
    return {
        **base_environ(),
        "SMTP_HOST": "smtp.example.com",
        "SMTP_PORT": "465",
        "SMTP_USERNAME": "smtp-user",
        "SMTP_PASSWORD": "test-smtp-password",
    }


def resend_environ() -> dict[str, str]:
    return {
        **base_environ(),
        "EMAIL_PROVIDER": "resend",
        "RESEND_API_KEY": "test-resend-api-key",
    }


def feature_image() -> emailer.FeatureImage:
    return emailer.FeatureImage(
        content=b"\x89PNG\r\n\x1a\npreview",
        content_type="image/png",
        filename="speakup-feature.png",
        alt='结果页预览 "新版"',
    )


class FeatureEmailTest(unittest.TestCase):
    def test_render_html_escapes_content_and_uses_inline_table_layout(self):
        message = emailer.FeatureMessage(
            title='<script>alert("x")</script>',
            summary="第一行 & 第二行",
            points=("<b>功能点</b>",),
            view_url="https://example.com/result?a=1&b=2",
        )

        rendered = emailer.render_html(message)

        self.assertNotIn("<script>", rendered)
        self.assertNotIn("<b>功能点</b>", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn("第一行 &amp; 第二行", rendered)
        self.assertIn("a=1&amp;b=2", rendered)
        self.assertIn('role="presentation"', rendered)
        self.assertIn('style="', rendered)
        self.assertNotIn("<style", rendered)

    def test_load_message_limits_feature_points(self):
        environ = base_environ()
        environ["FEATURE_MAIL_POINTS"] = "\n".join(f"功能点 {index}" for index in range(7))

        with self.assertRaisesRegex(emailer.NotificationError, "最多 6 条"):
            emailer.load_feature_message(environ)

    def test_loads_repository_image_and_renders_inline_cid(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            image_root = repo_root / "docs/assets/feature-notifications"
            image_root.mkdir(parents=True)
            image_path = image_root / "result-preview.png"
            image_path.write_bytes(feature_image().content)
            environ = {
                **base_environ(),
                "FEATURE_MAIL_IMAGE_PATH": "docs/assets/feature-notifications/result-preview.png",
                "FEATURE_MAIL_IMAGE_ALT": '结果页预览 "新版"',
            }
            with (
                patch.object(feature_email_content, "FEATURE_REPO_ROOT", repo_root),
                patch.object(feature_email_content, "FEATURE_IMAGE_ROOT", image_root),
            ):
                message = emailer.load_feature_message(environ)

        self.assertEqual(message.image.content_type, "image/png")
        rendered = emailer.render_html(message)
        self.assertIn('src="cid:speakup-feature-image"', rendered)
        self.assertIn('alt="结果页预览 &quot;新版&quot;"', rendered)

    def test_rejects_feature_image_outside_allowed_folder(self):
        environ = {**base_environ(), "FEATURE_MAIL_IMAGE_PATH": "docs/private.png"}

        with self.assertRaisesRegex(emailer.NotificationError, "只能来自"):
            emailer.load_feature_message(environ)

    def test_missing_smtp_config_fails_before_network_call(self):
        environ = smtp_environ()
        del environ["SMTP_PASSWORD"]
        network_called = False

        def unexpected_smtp(*args, **kwargs):
            nonlocal network_called
            network_called = True
            raise AssertionError("network must not be called")

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = emailer.main(environ=environ, smtp_factory=unexpected_smtp)

        self.assertEqual(result, 1)
        self.assertFalse(network_called)
        self.assertIn("SMTP_PASSWORD", stderr.getvalue())
        self.assertIn("/notifications", stderr.getvalue())
        self.assertNotIn(environ["FEATURE_MAIL_TO"], stderr.getvalue())

    def test_smtp_uses_tls_login_and_hides_recipient_headers(self):
        environ = smtp_environ()
        smtp = FakeSmtp()
        factory_args = None

        def smtp_factory(host, port, *, timeout, context):
            nonlocal factory_args
            factory_args = (host, port, timeout, context)
            return smtp

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = emailer.main(environ=environ, smtp_factory=smtp_factory)

        self.assertEqual(result, 0)
        self.assertEqual(factory_args[:3], ("smtp.example.com", 465, 20))
        self.assertIsNotNone(factory_args[3])
        self.assertEqual(smtp.login_args, ("smtp-user", "test-smtp-password"))
        self.assertEqual(smtp.from_addr, "updates@example.com")
        self.assertEqual(smtp.to_addrs, ["first@example.net", "second@example.org"])
        self.assertEqual(str(smtp.message["To"]), "undisclosed-recipients:;")
        self.assertNotIn("first@example.net", smtp.message.as_string())
        self.assertNotIn("second@example.org", smtp.message.as_string())
        self.assertTrue(smtp.message.is_multipart())
        self.assertNotIn("example.net", stdout.getvalue())
        self.assertNotIn("test-smtp-password", stdout.getvalue())
        self.assertIn("共发送 2 封", stdout.getvalue())

    def test_resend_uses_one_request_per_recipient_without_logging_addresses(self):
        environ = resend_environ()
        requests = []

        def capture_request(request, *, timeout):
            requests.append((request, timeout))
            return FakeResponse()

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = emailer.main(environ=environ, request_fn=capture_request)

        self.assertEqual(result, 0)
        self.assertEqual(len(requests), 2)
        payloads = [json.loads(request.data) for request, _ in requests]
        self.assertEqual(payloads[0]["to"], ["first@example.net"])
        self.assertEqual(payloads[1]["to"], ["second@example.org"])
        self.assertEqual(payloads[0]["from"], "SpeakUp <updates@example.com>")
        self.assertIn("<table", payloads[0]["html"])
        self.assertIn("查看详情：https://example.com/result", payloads[0]["text"])
        idempotency_keys = [request.get_header("Idempotency-key") for request, _ in requests]
        self.assertEqual(len(set(idempotency_keys)), 2)
        self.assertNotIn("first@example.net", "".join(idempotency_keys))
        self.assertNotIn("second@example.org", "".join(idempotency_keys))
        self.assertNotIn("example.net", stdout.getvalue())
        self.assertNotIn("example.org", stdout.getvalue())
        self.assertNotIn(environ["RESEND_API_KEY"], stdout.getvalue())
        self.assertIn("共发送 2 封", stdout.getvalue())

    def test_resend_embeds_image_as_cid_attachment(self):
        requests = []
        message = emailer.FeatureMessage(
            title="结果页稳定加载",
            summary="评分固定在顶部。",
            points=(),
            view_url=None,
            image=feature_image(),
        )

        def capture_request(request, *, timeout):
            requests.append(request)
            return FakeResponse()

        emailer.send_feature_email(
            emailer.load_delivery_config(resend_environ()),
            message,
            request_fn=capture_request,
        )

        payload = json.loads(requests[0].data)
        attachment = payload["attachments"][0]
        self.assertEqual(attachment["content_id"], "speakup-feature-image")
        self.assertEqual(attachment["content_type"], "image/png")
        self.assertEqual(base64.b64decode(attachment["content"]), message.image.content)
        self.assertIn('src="cid:speakup-feature-image"', payload["html"])

    def test_smtp_embeds_image_in_related_html_part(self):
        message = emailer.FeatureMessage(
            title="结果页稳定加载",
            summary="评分固定在顶部。",
            points=(),
            view_url=None,
            image=feature_image(),
        )

        mime_message = emailer._build_smtp_message(
            emailer.load_delivery_config(smtp_environ()),
            message,
        )

        image_parts = [part for part in mime_message.walk() if part.get_content_type() == "image/png"]
        self.assertEqual(len(image_parts), 1)
        self.assertEqual(image_parts[0]["Content-ID"], "<speakup-feature-image>")
        self.assertEqual(image_parts[0].get_content_disposition(), "inline")
        html_parts = [part for part in mime_message.walk() if part.get_content_type() == "text/html"]
        self.assertIn('src="cid:speakup-feature-image"', html_parts[0].get_content())

    def test_resend_error_does_not_echo_provider_message_or_configuration(self):
        environ = resend_environ()

        def rejected_request(request, *, timeout):
            body = json.dumps(
                {
                    "name": "validation_error",
                    "message": f"Rejected {environ['FEATURE_MAIL_TO']} with {environ['RESEND_API_KEY']}",
                }
            ).encode()
            raise HTTPError(request.full_url, 403, "Forbidden", {}, io.BytesIO(body))

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = emailer.main(environ=environ, request_fn=rejected_request)

        output = stderr.getvalue()
        self.assertEqual(result, 1)
        self.assertIn("HTTP 403", output)
        self.assertIn("validation_error", output)
        self.assertNotIn("first@example.net", output)
        self.assertNotIn(environ["RESEND_API_KEY"], output)

    def test_smtp_error_does_not_echo_credentials_or_addresses(self):
        environ = smtp_environ()

        def rejected_smtp(*args, **kwargs):
            raise smtplib.SMTPAuthenticationError(535, b"username or password rejected")

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = emailer.main(environ=environ, smtp_factory=rejected_smtp)

        output = stderr.getvalue()
        self.assertEqual(result, 1)
        self.assertIn("535", output)
        self.assertNotIn(environ["SMTP_USERNAME"], output)
        self.assertNotIn(environ["SMTP_PASSWORD"], output)
        self.assertNotIn("first@example.net", output)

    def test_rejects_unknown_provider_without_network(self):
        environ = base_environ()
        environ["EMAIL_PROVIDER"] = "unknown"

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = emailer.main(environ=environ)

        self.assertEqual(result, 1)
        self.assertIn("仅支持 smtp 或 resend", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
