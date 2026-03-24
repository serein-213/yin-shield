from pathlib import Path
import json
import tempfile
import unittest

from yinshield.http_api import generate_auth_token
from yinshield.install_openclaw import (
    DEFAULT_PLUGIN_ID,
    build_openclaw_plugin_entry,
    install_openclaw_config,
    merge_openclaw_config,
)


class InstallOpenClawTests(unittest.TestCase):
    def test_generate_auth_token_returns_non_empty_secret(self) -> None:
        token_a = generate_auth_token()
        token_b = generate_auth_token()
        self.assertTrue(token_a)
        self.assertNotEqual(token_a, token_b)

    def test_merge_openclaw_config_preserves_existing_plugins(self) -> None:
        existing = {
            "plugins": {
                "entries": {
                    "existing-plugin": {
                        "enabled": True,
                        "config": {"foo": "bar"},
                    }
                }
            }
        }
        plugin_entry = build_openclaw_plugin_entry(
            base_url="http://127.0.0.1:27811",
            mode="placeholder",
            auth_token="secret",
        )
        merged = merge_openclaw_config(existing, DEFAULT_PLUGIN_ID, plugin_entry)
        self.assertIn("existing-plugin", merged["plugins"]["entries"])
        self.assertEqual(merged["plugins"]["entries"][DEFAULT_PLUGIN_ID]["config"]["authToken"], "secret")

    def test_install_openclaw_config_writes_merged_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "openclaw.json"
            config_path.write_text(json.dumps({"plugins": {"entries": {}}}), encoding="utf-8")
            plugin_entry = build_openclaw_plugin_entry(
                base_url="http://127.0.0.1:27811",
                mode="alias",
                auth_token="secret",
            )
            result = install_openclaw_config(config_path, DEFAULT_PLUGIN_ID, plugin_entry)
            self.assertEqual(result["updated"], "true")
            stored = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(stored["plugins"]["entries"][DEFAULT_PLUGIN_ID]["config"]["mode"], "alias")

    def test_install_openclaw_config_falls_back_to_snippet_for_non_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "openclaw.json"
            config_path.write_text("{ not: valid json5-ish comment file", encoding="utf-8")
            plugin_entry = build_openclaw_plugin_entry(
                base_url="http://127.0.0.1:27811",
                mode="placeholder",
                auth_token="secret",
            )
            result = install_openclaw_config(config_path, DEFAULT_PLUGIN_ID, plugin_entry)
            self.assertEqual(result["updated"], "false")
            snippet_path = Path(result["snippet_path"])
            self.assertTrue(snippet_path.exists())


if __name__ == "__main__":
    unittest.main()
