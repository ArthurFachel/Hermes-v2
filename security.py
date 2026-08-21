"""
Sanitização defensiva de dados antes de expô-los pela API.

O Hermes continua com acesso às ferramentas necessárias para consultar a base
geológica. Este módulo atua na fronteira de saída e remove dados operacionais
que não devem aparecer em respostas, históricos ou traces.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any


PATH_REDACTED = "[CAMINHO_REMOVIDO]"
SECRET_REDACTED = "[SEGREDO_REMOVIDO]"
HASH_REDACTED = "[HASH_REMOVIDO]"
IP_REDACTED = "[IP_REMOVIDO]"
ENV_REDACTED = "[VARIAVEL_DE_AMBIENTE_REMOVIDA]"
SSH_REDACTED = "[DADO_SSH_REMOVIDO]"
SENSITIVE_FILE_REDACTED = "[ARQUIVO_SENSIVEL_REMOVIDO]"
ENCODED_DATA_REDACTED = "[DADO_CODIFICADO_REMOVIDO]"


_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?"
    r"-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.DOTALL,
)
_SSH_PUBLIC_KEY_RE = re.compile(
    r"\bssh-(?:rsa|dss|ed25519)\s+[A-Za-z0-9+/=]{20,}|"
    r"\b(?:ecdsa-sha2-nistp(?:256|384|521))\s+"
    r"[A-Za-z0-9+/=]{20,}",
    re.IGNORECASE,
)
_BEARER_RE = re.compile(
    r"(?i)\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{8,}"
)
_JWT_RE = re.compile(
    r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\."
    r"[A-Za-z0-9_-]{5,}\b"
)
_BASE64_BLOB_RE = re.compile(
    r"(?<![A-Za-z0-9+/=:])[A-Za-z0-9+/]{40,}={0,2}"
    r"(?![A-Za-z0-9+/=])"
)
_KNOWN_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(?:"
    r"malta_[A-Za-z0-9_-]{2,}|"
    r"sk-[A-Za-z0-9_-]{12,}|"
    r"(?:AKIA|ASIA)[A-Z0-9]{16}|"
    r"gh[opurs]_[A-Za-z0-9]{20,}|"
    r"xox[baprs]-[A-Za-z0-9-]{10,}"
    r")(?![A-Za-z0-9_-])",
    re.IGNORECASE,
)
_HASH_RE = re.compile(
    r"(?<![A-Fa-f0-9])[A-Fa-f0-9]{32,128}(?![A-Fa-f0-9])"
)
_IPV4_CANDIDATE_RE = re.compile(
    r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}"
    r"(?=$|[^\d.]|\.(?!\d))"
)
_IPV6_CANDIDATE_RE = re.compile(
    r"(?<![A-Fa-f0-9:])"
    r"(?=[A-Fa-f0-9:]*:)[A-Fa-f0-9:]{2,}"
    r"(?![A-Fa-f0-9:])"
)
_WINDOWS_PATH_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_])(?:[A-Z]:\\|\\\\)"
    r"(?:[^\\\r\n<>:\"|?*]+\\)*[^\\\r\n<>:\"|?*]*"
)
_POSIX_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_:/])(?:~|/)"
    r"[A-Za-z0-9._@+~-]+"
    r"(?:/[A-Za-z0-9._@+~-]+)*/?"
)
_TRAVERSAL_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_.])(?:\.\./)+(?:[A-Za-z0-9._@+~-]+/?)+"
)
_SENSITIVE_FILE_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_.-])(?:"
    r"\.env(?:\.[A-Za-z0-9_.-]+)?|"
    r"api_keys?\.json|credentials(?:\.[A-Za-z0-9_.-]+)?"
    r")(?![A-Za-z0-9_.-])"
)
_ENV_ASSIGNMENT_RE = re.compile(
    r"(?m)^(?P<indent>[ \t]*(?:[-*]\s*)?)"
    r"(?P<name>[A-Z_][A-Z0-9_]*)"
    r"(?P<separator>\s*=\s*)(?P<value>[^\r\n]*)$"
)
_SENSITIVE_STRUCTURED_VALUE_RE = re.compile(
    r"(?i)(?P<label>[\"']?(?:"
    r"api[_-]?key|access[_-]?key|secret(?:[_-]?access)?[_-]?key|"
    r"password|passwd|token|authorization|cookie|"
    r"key[_-]?hash|key[_-]?prefix|private[_-]?key|"
    r"ssh[_-]?(?:client|connection|tty)"
    r")[\"']?\s*(?:[:=|])\s*)"
    r"(?P<value>\"[^\"\r\n]*\"|'[^'\r\n]*'|[^|,\s}\r\n]+)"
)

_SENSITIVE_FIELD_RE = re.compile(
    r"(?i)(?:"
    r"api[_-]?key|access[_-]?key|secret(?:[_-]?access)?[_-]?key|"
    r"password|passwd|token|authorization|cookie|"
    r"key[_-]?hash|key[_-]?prefix|private[_-]?key|"
    r"ssh[_-]?(?:client|connection|tty)"
    r")"
)

_SENSITIVE_ENV_NAMES = {
    "HOME",
    "OLDPWD",
    "PATH",
    "PWD",
    "SHELL",
    "USER",
    "LOGNAME",
    "LANG",
    "TERM",
    "SHLVL",
    "LESSOPEN",
    "LESSCLOSE",
    "DBUS_SESSION_BUS_ADDRESS",
    "VIRTUAL_ENV",
    "VIRTUAL_ENV_PROMPT",
}
_SENSITIVE_ENV_PREFIXES = (
    "AWS_",
    "AZURE_",
    "DATABASE_",
    "DB_",
    "GCP_",
    "GOOGLE_",
    "HERMES_",
    "OPENAI_",
    "SSH_",
    "TERMINAL_",
    "XDG_",
)
_SENSITIVE_ENV_FRAGMENTS = (
    "API_KEY",
    "AUTH",
    "COOKIE",
    "CREDENTIAL",
    "PASSWORD",
    "PASSWD",
    "PRIVATE_KEY",
    "SECRET",
    "TOKEN",
)
_SCIENTIFIC_ASSIGNMENT_ALLOWLIST = {
    "COT",
    "EH",
    "IH",
    "IO",
    "PH",
    "PI",
    "RO",
    "S1",
    "S2",
    "S3",
    "TMAX",
    "TOC",
}


def _is_sensitive_env_name(name: str) -> bool:
    upper_name = name.upper()
    if upper_name in _SCIENTIFIC_ASSIGNMENT_ALLOWLIST:
        return False
    return (
        upper_name in _SENSITIVE_ENV_NAMES
        or upper_name.startswith(_SENSITIVE_ENV_PREFIXES)
        or any(fragment in upper_name for fragment in _SENSITIVE_ENV_FRAGMENTS)
        # Uma linha NOME=valor em caixa alta tem formato de variável/config.
        # A allowlist acima evita apagar parâmetros geológicos conhecidos.
        or (
            name == upper_name
            and (upper_name == "_" or upper_name.isupper())
        )
    )


def _redact_env_assignment(match: re.Match[str]) -> str:
    if not _is_sensitive_env_name(match.group("name")):
        return match.group(0)
    return f"{match.group('indent')}{ENV_REDACTED}"


def _redact_ip_candidate(match: re.Match[str]) -> str:
    candidate = match.group(0)
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return candidate
    return IP_REDACTED


def sanitize_text(value: str) -> str:
    """Remove dados operacionais sensíveis de um texto."""
    if not value:
        return value

    text = _PRIVATE_KEY_RE.sub(SECRET_REDACTED, value)
    text = _SSH_PUBLIC_KEY_RE.sub(SSH_REDACTED, text)
    text = _ENV_ASSIGNMENT_RE.sub(_redact_env_assignment, text)
    text = _BEARER_RE.sub(SECRET_REDACTED, text)
    text = _JWT_RE.sub(SECRET_REDACTED, text)
    text = _KNOWN_TOKEN_RE.sub(SECRET_REDACTED, text)
    text = _HASH_RE.sub(HASH_REDACTED, text)
    text = _BASE64_BLOB_RE.sub(ENCODED_DATA_REDACTED, text)
    text = _SENSITIVE_STRUCTURED_VALUE_RE.sub(
        lambda match: f"{match.group('label')}{SECRET_REDACTED}",
        text,
    )
    text = _IPV4_CANDIDATE_RE.sub(_redact_ip_candidate, text)
    text = _IPV6_CANDIDATE_RE.sub(_redact_ip_candidate, text)
    text = _WINDOWS_PATH_RE.sub(PATH_REDACTED, text)
    text = _TRAVERSAL_PATH_RE.sub(PATH_REDACTED, text)
    text = _POSIX_PATH_RE.sub(PATH_REDACTED, text)
    text = _SENSITIVE_FILE_RE.sub(SENSITIVE_FILE_REDACTED, text)
    return text


def sanitize_data(value: Any, field_name: str | None = None) -> Any:
    """Sanitiza recursivamente estruturas destinadas a respostas ou traces."""
    if field_name and _SENSITIVE_FIELD_RE.fullmatch(field_name):
        return None if value is None else SECRET_REDACTED
    if field_name and _is_sensitive_env_name(field_name):
        return None if value is None else ENV_REDACTED

    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, dict):
        return {
            key: sanitize_data(item, str(key))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_data(item) for item in value)
    return value
