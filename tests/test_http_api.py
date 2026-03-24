from pathlib import Path
import tempfile
import unittest

from yinshield import Shield
from yinshield.http_api import ServiceState, build_health_payload, mask_messages_payload, mask_payload, unmask_payload


class DummyHeaders(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class HTTPAPITests(unittest.TestCase):
    def test_health_payload(self) -> None:
        payload = build_health_payload(Shield())
        self.assertEqual(payload["ok"], True)
        self.assertEqual(payload["service"], "yinshield")
        self.assertEqual(payload["mode"], "placeholder")
        self.assertEqual(payload["stateless_by_default"], True)

    def test_mask_and_unmask_payloads(self) -> None:
        state = ServiceState(mode="placeholder", strategy="strict")
        masked = mask_payload(
            {"text": "我叫张三，手机号13812345678，订单号20240324ABC123。"},
            state,
        )
        self.assertIn("<PERSON_1>", masked["text"])
        self.assertIn("<PHONE_1>", masked["text"])
        self.assertIn("<ORDER_NO_1>", masked["text"])

        restored = unmask_payload(
            {"text": masked["text"], "mapping": masked["mapping"]},
            state,
        )
        self.assertEqual(restored["text"], "我叫张三，手机号13812345678，订单号20240324ABC123。")

    def test_default_http_masking_is_stateless(self) -> None:
        state = ServiceState(mode="alias", strategy="strict")
        first = mask_payload({"text": "联系人：张三，手机号13812345678，订单号20240324ABC123。"}, state)
        second = mask_payload({"text": "请继续联系张三，手机号13812345678。"}, state)

        self.assertTrue(any(original == "20240324ABC123" for original in first["mapping"].values()))
        self.assertFalse(any(original == "20240324ABC123" for original in second["mapping"].values()))
        self.assertNotIn("session_id", first)

    def test_explicit_session_id_reuses_mapping_and_persists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session_path = Path(temp_dir) / "sessions.json"
            state = ServiceState(mode="alias", strategy="strict", session_file=str(session_path))

            first = mask_payload(
                {"text": "收件人：张三，手机号13812345678。", "session_id": "chat-1"},
                state,
            )
            second = mask_payload(
                {"text": "请继续联系张三，手机号13812345678。", "session_id": "chat-1"},
                state,
            )

            self.assertTrue(session_path.exists())
            self.assertEqual(first["mapping"], second["mapping"])
            self.assertEqual(first["session_id"], "chat-1")
            self.assertEqual(second["session_id"], "chat-1")

    def test_mapping_seed_override(self) -> None:
        state = ServiceState()
        masked = mask_payload(
            {
                "text": "我叫张三。",
                "mapping": {"<PERSON_9>": "张三"},
            },
            state,
        )
        self.assertEqual(masked["text"], "我叫<PERSON_9>。")

    def test_mask_messages_payload(self) -> None:
        state = ServiceState(mode="placeholder", strategy="strict")
        result = mask_messages_payload(
            {
                "messages": [
                    {"role": "user", "content": "我叫张三，手机号13812345678"},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "订单号20240324ABC123"},
                            {"type": "image_url", "image_url": {"url": "https://example.com/a.png"}},
                        ],
                    },
                ]
            },
            state,
        )
        self.assertEqual(result["messages"][0]["content"], "我叫<PERSON_1>，手机号<PHONE_1>")
        self.assertEqual(result["messages"][1]["content"][0]["text"], "订单号<ORDER_NO_1>")
        self.assertEqual(
            result["messages"][1]["content"][1]["image_url"]["url"],
            "https://example.com/a.png",
        )

    def test_auth_validation(self) -> None:
        state = ServiceState(auth_token="secret-token")
        with self.assertRaises(PermissionError):
            state.validate_auth(DummyHeaders())
        state.validate_auth(DummyHeaders({"Authorization": "Bearer secret-token"}))


if __name__ == "__main__":
    unittest.main()
