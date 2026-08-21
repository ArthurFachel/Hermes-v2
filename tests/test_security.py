import json
import tempfile
import unittest
from pathlib import Path

import tracer
from security import (
    ENCODED_DATA_REDACTED,
    ENV_REDACTED,
    HASH_REDACTED,
    IP_REDACTED,
    PATH_REDACTED,
    SECRET_REDACTED,
    SENSITIVE_FILE_REDACTED,
    sanitize_data,
    sanitize_text,
)


class SanitizeTextTests(unittest.TestCase):
    def test_redacts_paths_but_preserves_public_urls_and_geology(self):
        text = (
            "Fonte em /home/ubuntu/Hermes-v2/fontes/artigo.md. "
            "Diretório alternativo /fontes_de_conhecimento. "
            "Veja https://doi.org/10.1000/exemplo. "
            "O limite Aptiano/Albiano permanece válido."
        )

        result = sanitize_text(text)

        self.assertIn(PATH_REDACTED, result)
        self.assertNotIn("/home/ubuntu", result)
        self.assertNotIn("/fontes_de_conhecimento", result)
        self.assertIn("https://doi.org/10.1000/exemplo", result)
        self.assertIn("Aptiano/Albiano", result)

    def test_redacts_environment_variables_without_hiding_geology(self):
        text = (
            "HOME=/home/ubuntu\n"
            "SSH_CONNECTION=203.0.113.10 1234 10.0.0.2 22\n"
            "OPENAI_API_KEY=sk-example1234567890\n"
            "BROWSER_INACTIVITY_TIMEOUT=120\n"
            "LS_COLORS=rs=0:di=01;34\n"
            "_=/usr/bin/env\n"
            "COT=17.2%\n"
            "TMAX=435"
        )

        result = sanitize_text(text)

        self.assertEqual(result.count(ENV_REDACTED), 6)
        self.assertIn("COT=17.2%", result)
        self.assertIn("TMAX=435", result)
        self.assertNotIn("203.0.113.10", result)

    def test_redacts_tokens_hashes_ips_and_ssh_keys(self):
        digest = "a" * 64
        text = (
            "Chave malta_abcdefghijklmnopqrstuvwxyz123456. "
            f"Hash {digest}. IP 198.51.100.42 e IPv6 2001:db8::1. "
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz. "
            "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITestKeyMaterial"
        )

        result = sanitize_text(text)

        self.assertNotIn("malta_", result)
        self.assertNotIn(digest, result)
        self.assertNotIn("198.51.100.42", result)
        self.assertNotIn("2001:db8::1", result)
        self.assertIn(HASH_REDACTED, result)
        self.assertIn(IP_REDACTED, result)
        self.assertGreaterEqual(result.count(SECRET_REDACTED), 2)

    def test_redacts_sensitive_file_names_and_traversal(self):
        text = "Leia ../../.env, api_keys.json e credentials.json."

        result = sanitize_text(text)

        self.assertIn(PATH_REDACTED, result)
        self.assertNotIn("api_keys.json", result)
        self.assertNotIn("credentials.json", result)
        self.assertIn(SENSITIVE_FILE_REDACTED, result)

    def test_redacts_long_base64_payload(self):
        encoded_secret = (
            "T1BFTkFJX0FQSV9LRVk9c2stdGVzdC1ub3QtYS1yZWFsLWtleQ=="
        )

        result = sanitize_text(f"Conteúdo codificado: {encoded_secret}")

        self.assertNotIn(encoded_secret, result)
        self.assertIn(ENCODED_DATA_REDACTED, result)

    def test_sanitizes_nested_structured_data(self):
        data = {
            "response": "Servidor 192.0.2.10 em /etc/passwd",
            "key_hash": "b" * 64,
            "HOME": "/home/ubuntu",
            "COT": "17.2%",
            "nested": [{"api_key": "malta_abcdefghijklmnopqrstuvwxyz123456"}],
        }

        result = sanitize_data(data)

        self.assertNotIn("192.0.2.10", result["response"])
        self.assertNotIn("/etc/passwd", result["response"])
        self.assertEqual(result["key_hash"], SECRET_REDACTED)
        self.assertEqual(result["HOME"], ENV_REDACTED)
        self.assertEqual(result["COT"], "17.2%")
        self.assertEqual(result["nested"][0]["api_key"], SECRET_REDACTED)


class TraceSanitizationTests(unittest.TestCase):
    def test_trace_never_persists_raw_sensitive_output(self):
        original_dir = tracer.TRACES_DIR
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tracer.TRACES_DIR = Path(tmp_dir)
                tracer.save_trace(
                    trace_id="trace-test",
                    session_id="session-test",
                    request_data={"query": "Leia /etc/passwd"},
                    response_data={"response": "IP 192.0.2.1"},
                    hermes_stdout="HOME=/home/ubuntu",
                    hermes_stderr="Bearer abcdefghijklmnop",
                    hermes_returncode=0,
                    duration_s=0.1,
                    tool_calls=[],
                )

                raw_trace = json.loads(
                    (Path(tmp_dir) / "trace-test.json").read_text(encoding="utf-8")
                )
                serialized = json.dumps(raw_trace)
                self.assertNotIn("/etc/passwd", serialized)
                self.assertNotIn("192.0.2.1", serialized)
                self.assertNotIn("/home/ubuntu", serialized)
                self.assertNotIn("abcdefghijklmnop", serialized)
        finally:
            tracer.TRACES_DIR = original_dir


if __name__ == "__main__":
    unittest.main()
