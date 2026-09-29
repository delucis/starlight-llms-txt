"""Detect PII-shaped values in tracked Git content without reading the worktree.

The scanner deliberately has two modes:

* ``enforce`` reports only deterministic, high-confidence findings suitable for
  a commit or CI gate.
* ``audit`` includes review-required surfaces and lower-confidence indicators
  used during a repository sweep.

Exit 0 means no findings, 1 means findings, and 2 means the scan could not run.
Finding messages never contain the matched value.
"""

# The scanner remains one auditable policy unit until the parser seams tracked in
# issues #932, #933, #939, and #940 are implemented.
# pylint: disable=too-many-lines

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import sys
import unicodedata
import urllib.parse
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence
    from typing import BinaryIO

GIT_BATCH_FIELD_COUNT = 3
GIT_MODE_DIGITS = frozenset(b"01234567")
GIT_MODE_LENGTH = 6
GIT_OBJECT_ID_DIGITS = frozenset(b"0123456789abcdef")
GIT_RAW_FIELD_COUNT = 5

EXCLUDED_PATHS = {
    "scripts/check_pii.py",
    "scripts/check-pii.sh",
    "scripts/check-repo-hygiene.sh",
    "tests/test-check-pii.sh",
    "tests/test-check-repo-hygiene.sh",
}
LEGAL_BASENAMES = ("license", "copying", "notice", "authors")
MEDIA_SUFFIXES = {
    ".gif",
    ".jpeg",
    ".jpg",
    ".mov",
    ".mp4",
    ".pdf",
    ".png",
    ".svg",
    ".tif",
    ".tiff",
    ".webm",
    ".webp",
}
TEXT_MEDIA_SUFFIXES = {".svg"}
SOURCE_CODE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".hcl",
    ".java",
    ".js",
    ".jq",
    ".jsx",
    ".kt",
    ".kts",
    ".m",
    ".mm",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".source",
    ".swift",
    ".tf",
    ".ts",
    ".tsx",
}
PROSE_DOCUMENT_SUFFIXES = {".adoc", ".asciidoc", ".md", ".mdx", ".rst", ".txt"}
SOURCE_FENCE_LANGUAGES = {
    "c",
    "cpp",
    "csharp",
    "go",
    "hcl",
    "java",
    "javascript",
    "js",
    "jq",
    "jsx",
    "kotlin",
    "php",
    "py",
    "python",
    "rb",
    "ruby",
    "rust",
    "swift",
    "terraform",
    "ts",
    "tsx",
    "typescript",
}

EMAIL_RE = re.compile(
    r"(?<![-A-Za-z0-9._%+/@])"
    r"[A-Za-z0-9][-A-Za-z0-9.!#$%&'*+=?^_`{|}~]*[A-Za-z0-9]@"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,63}"
)
HOME_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:"
    r"(?P<prefix>/Users/|/home/)(?P<user>[A-Za-z0-9._${}<>-]+)"
    r"|(?P<winprefix>[A-Za-z]:\\+(?:Users)\\+)(?P<winuser>[A-Za-z0-9._${}<>-]+)"
    r")"
)
PHONE_FIELD_RE = re.compile(
    r"(?i)(?:^|[,{\s])['\"]?(?:phone(?:_number)?|mobile|telephone|fax)['\"]?"
    r"\s*[:=]\s*['\"]?(?P<value>\+?[0-9][0-9(). \-]{7,}[0-9])"
)
PERSON_FIELD_RE = re.compile(
    r"(?i)(?:^|[,{\s])['\"]?"
    r"(?P<key>full_name|first_name|last_name|given_name|family_name|display_name)"
    r"['\"]?\s*(?P<separator>[:=])\s*(?P<quote>['\"`]?)"
    r"(?P<value>(?:(?!\\[rn])[^'\"`#,\r\n}\]])+)"
)
LOCALIZATION_BUNDLE_RE = re.compile(
    r"(?:bundle\.l10n|package\.nls)(?:\.[A-Za-z0-9-]+)?\.json$",
    re.IGNORECASE,
)
VSCODE_WHEN_PROPERTY_RE = re.compile(r'"when"\s*:\s*"(?P<expression>(?:\\.|[^"\\])*)"')
VSCODE_VIEW_ITEM_TAG_RE = re.compile(
    r"\bviewItem\s*(?:==|===)\s*"
    r"(?P<tag>(?P<type>[A-Za-z_][A-Za-z0-9_.-]*):"
    r"(?P<variant>[A-Za-z_][A-Za-z0-9_.-]*))"
)
ENUM_HEADER_RE = re.compile(
    r"\b(?:const\s+)?enum(?:\s+class)?\s+"
    r"[A-Za-z_$][A-Za-z0-9_$]*",
)
SOURCE_SNIPPET_INDEX_RE = re.compile(r"\$\{[A-Za-z_$][A-Za-z0-9_$]*(?:\+\+|--)?\}")
IDENTITY_FIELD_RE = re.compile(
    r"(?i)(?P<field_prefix>^|[^A-Za-z0-9_/-])"
    r"(?P<key_open>[*_~`'\"]*)"
    r"(?P<key>tenant(?:_name|_id|-name|-id|Name|Id)?|customer(?:_name|_id|-name|-id|Name|Id)?|account(?:_name|_id|-name|-id|Name|Id)?|subscription(?:_name|_id|-name|-id|Name|Id)|project(?:_name|_id|-name|-id|Name|Id)|namespace)"
    r"(?P<key_close>[*_~`'\"]*)\s*(?P<separator>[:=])\s*(?P<quote>(?:\\['\"`]|['\"`])?)"
    r"(?P<value>(?:(?!\\[rn])[^'\"`#,\r\n}\]])+)"
)
PROSE_IDENTITY_QUANTIFIER_RE = re.compile(
    r"(?:^|\s)(?:any|each|every|no)$",
    re.IGNORECASE,
)
PROSE_SAFE_LANGUAGE_RE = re.compile(
    r"(?:use\s+the\s+documented\s+example\s+"
    r"(?:tenant|customer|account|project|namespace)"
    r"|use\s+the\s+synthetic\s+placeholder\s+value"
    r"|use\s+the\s+customer['\u2019]s\s+documented\s+example\s+tenant"
    r")[.!?]",
    re.IGNORECASE,
)
PROSE_SAFE_CONTINUATION_RE = re.compile(
    r"(?:continue\s+with\s+the\s+setup\s+instructions[.!?])?",
    re.IGNORECASE,
)
JQ_COMMAND_RE = re.compile(
    r"(?:^|[|;&(])\s*"
    r"(?:[A-Za-z_][A-Za-z0-9_]*=[^\s]+\s+)*"
    r"(?:(?:command(?:\s+--)?|exec(?:\s+--)?|nohup|"
    r"(?:[^\s;|&]*/)?nice(?:\s+(?:-n\s+\S+|-[0-9]+))?|"
    r"(?:[^\s;|&]*/)?timeout\s+\S+|"
    r"stdbuf(?:(?:\s+-(?:i|o|e)\S+))*|"
    r"(?:[^\s;|&]*/)?time(?:\s+-\S+)*|"
    r"xargs(?:(?:\s+-(?:L|n|P)\s*[0-9]+)|(?:\s+(?:-0|--null))|"
    r"(?:\s+-I(?:\s+\S+|\S+))|"
    r"(?:\s+--max-args(?:=\S+|\s+\S+))|(?:\s+-r)|"
    r"(?:\s+-d(?:\s+\S+|\S+))|(?:\s+--replace(?:=\S+)?))*|"
    r"sudo(?:(?:\s+-[nEHSkK]+)|(?:\s+-(?:g|u)\s+\S+)|"
    r"(?:\s+--group(?:=\S+|\s+\S+))|"
    r"(?:\s+--user(?:=\S+|\s+\S+))|"
    r"(?:\s+--preserve-env(?:=\S+)?)|(?:\s+--))*|"
    r"(?:[^\s;|&]*/)?env(?:(?:\s+-i)|(?:\s+-u\s+\S+)|"
    r"(?:\s+--ignore-environment)|"
    r"(?:\s+--unset(?:=\S+|\s+\S+))|(?:\s+--))*)\s+"
    r"(?:[A-Za-z_][A-Za-z0-9_]*=[^\s]+\s+)*"
    r")*"
    r"(?:[^\s;|&]*/)?jq(?:\s|$)"
)
FENCE_RE = re.compile(
    r"^(?P<leading> {0,3})"
    r"(?P<container>(?:(?:> ?|(?:[-+*]|[0-9]{1,9}[.)])[ \t]{1,4}))*)"
    r"(?P<indent> {0,3})"
    r"(?P<marker>`{3,}|~{3,})(?P<info>[^\r\n]*)$",
)
FENCE_CLOSE_RE = re.compile(
    r"^\s*(?:>\s*)*(?:(?:[-+*]|[0-9]{1,9}[.)])\s+)*"
    r"(?P<marker>`{3,}|~{3,})\s*$"
)
FENCE_CLASS_RE = re.compile(r"(?:^|[\s,])\.([A-Za-z0-9_+-]+)(?=[\s,]|$)")
ANSI_ESCAPE_RE = re.compile(
    r"(?:(?:\x1b\]|\x9d).*?(?:\x07|\x9c|\x1b\\)|"
    r"(?:\x1b[PX^_]|[\x90\x98\x9e\x9f]).*?(?:\x9c|\x1b\\)|"
    r"\x1b\[[0-?]*[ -/]*[@-~]|\x9b[0-?]*[ -/]*[@-~]|"
    r"\x1b[ -/]*[0-~]|[\x80-\x9f])",
    re.DOTALL,
)
ZERO_WIDTH_CONTROL_RE = re.compile(r"[\x01-\x08\x0b\x0c\x0e-\x1a\x1c-\x1f\x7f]")
YAML_ANCHOR_VALUE_RE = re.compile(r"&(?P<name>[A-Za-z0-9_.-]+)")
YAML_TAG_CHARACTER = r"(?:%[0-9A-Fa-f]{2}|[!A-Za-z0-9_.:/+@;&=?$~,'()#*-])"
YAML_TAG_RE = re.compile(rf"!(?:<[^>\r\n]+>|{YAML_TAG_CHARACTER}+)?\s+")
YAML_BLOCK_START_RE = re.compile(
    r":\s*(?:&(?P<anchor>[A-Za-z0-9_.-]+)\s+)?"
    r"[|>](?:[+-]?[1-9]?|[1-9][+-])\s*$"
)
SAFE_BLOCK_PROSE_RE = re.compile(
    r"(?:documented\s+example|synthetic\s+placeholder)\s+text[.!?]?",
    re.IGNORECASE,
)
TEMPLATE_PLACEHOLDER_RE = re.compile(
    r"(?:\$(?:[A-Za-z_][A-Za-z0-9_]*|[0-9]+)|\$\{[^{}\s]+\}|"
    r"\{[A-Za-z_][A-Za-z0-9_.-]*\}|<[A-Za-z_][A-Za-z0-9_.-]*>|"
    r"\{\{\s*[^{}\r\n]+?\s*\}\}|\[%\s*[^%\r\n]+?\s*%\])"
)
SHELL_DOUBLE_ESCAPE_RE = re.compile(r'\\(["\\])')
NON_OUTPUT_JQ_STRING_FUNCTIONS = {
    "IN",
    "all",
    "any",
    "bsearch",
    "capture",
    "combinations",
    "contains",
    "delpaths",
    "endswith",
    "error",
    "getpath",
    "group_by",
    "has",
    "in",
    "index",
    "indices",
    "inside",
    "isempty",
    "ltrimstr",
    "match",
    "max_by",
    "min_by",
    "rindex",
    "rtrimstr",
    "scan",
    "select",
    "sort_by",
    "split",
    "splits",
    "startswith",
    "strptime",
    "test",
    "unique_by",
    "paths",
}
NON_OUTPUT_JQ_NUMBER_FUNCTIONS = NON_OUTPUT_JQ_STRING_FUNCTIONS | {
    "combinations",
    "flatten",
}
POSITIONAL_JQ_OUTPUT_ARGUMENTS = {
    "gsub": {1},
    "limit": {1},
    "nth": {1},
    "setpath": {1},
    "sub": {1},
    "until": {1},
}
JQ_RANGE_OUTPUT_ARGUMENTS = {0, 1}
JQ_NON_INDEX_KEYWORDS = {
    "as",
    "catch",
    "do",
    "elif",
    "else",
    "end",
    "foreach",
    "if",
    "label",
    "or",
    "reduce",
    "then",
    "try",
}
SOURCE_COMMENT_EXPRESSION_RE = re.compile(
    r"(?:[A-Za-z_$][A-Za-z0-9_$]*(?:\.|::|->))+[A-Za-z_$][A-Za-z0-9_$]*"
    r"|[A-Za-z_$][A-Za-z0-9_$]*\s*\([^\r\n]*\)"
)
SOURCE_TEMPLATE_STRING_RE = re.compile(r"(?P<quote>['\"])(?P<value>(?:\\.|(?!\1).)*)\1")
JQ_OPTION_ARITY = {
    "--arg": 2,
    "--argfile": 2,
    "--argjson": 2,
    "--indent": 1,
    "--rawfile": 2,
    "--slurpfile": 2,
    "-L": 1,
}
ADDRESS_FIELD_RE = re.compile(
    r"(?i)(?:^|[,{\s])['\"]?"
    r"(?P<key>street_address|postal_address|postal_code|zip_code|date_of_birth|dob|"
    r"social_security_number|ssn)"
    r"['\"]?\s*[:=]\s*(?P<quote>['\"`]?)"
    r"(?P<value>(?:(?!\\[rn])[^'\"`#,\r\n}\]])+)"
)
QUERY_RE = re.compile(
    r"(?i)[?&](?P<key>email|phone|mobile|full_name|first_name|last_name|address|dob|ssn)="
    r"(?P<value>[^&#\s]+)"
)
IPV4_RE = re.compile(r"(?<![A-Za-z0-9.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![A-Za-z0-9.])")
DOTTED_VERSION_PREFIX_RE = re.compile(
    r"(?i)(?:"
    r"(?:chrome|headlesschrome|chromium|firefox|safari|edg|edge|opera)/\s*$"
    r"|[A-Za-z0-9_.-]*version[A-Za-z0-9_.-]*\s*[:=]\s*['\"`]?\s*$"
    r"|version[A-Za-z0-9_.-]*\)?\.to(?:be|equal)\(\s*['\"`]?\s*$"
    r")"
)
SVG_PATH_ATTRIBUTE_RE = re.compile(r"(?:^|\s)d\s*=\s*(?P<quote>['\"])", re.IGNORECASE)
PDF_AUTHOR_RE = re.compile(
    r"/(?:Author|Subject)\s*\((?P<value>[^)]{2,})\)",
    re.IGNORECASE,
)
SENSITIVE_MEDIA_TAG_RE = re.compile(
    r"GPSLatitude|GPSLongitude|OwnerName|CameraOwnerName",
    re.IGNORECASE,
)
MEDIA_AUTHOR_METADATA_RE = re.compile(
    r"(?:^|\n)(?:Author|Artist|Creator|OwnerName|CameraOwnerName)"
    r"(?:\s*[:=]\s*|\n+)(?P<value>[^\r\n]+)",
    re.IGNORECASE,
)
PROVENANCE_TRAILER_RE = re.compile(
    r"^(?:Co-authored-by|Signed-off-by|Reviewed-by|Acked-by|Tested-by):",
    re.IGNORECASE,
)
URI_USERINFO_PREFIX_RE = re.compile(
    r"(?i)\b(?P<scheme>[a-z][a-z0-9+.-]*):(?://)?[^\s/]*$",
)
PRINTABLE_ASCII_RE = re.compile(rb"[\x20-\x7e]{4,}")
NUMERIC_LITERAL_RE = re.compile(
    r"[+-]?(?:"
    r"0[xX][0-9A-Fa-f_]+|0[bB][01_]+|0[oO][0-7_]+|"
    r"[0-9][0-9_]*(?:\.[0-9_]+)?(?:[eE][+-]?[0-9][0-9_]*)?"
    r");?"
)
MAX_COMMONMARK_INDENT = 3
LIST_FENCE_CONTENT_INDENT = 2
DEFAULT_IGNORABLE_RANGES = (
    (0x034F, 0x034F),
    (0x115F, 0x1160),
    (0x17B4, 0x17B5),
    (0x180B, 0x180F),
    (0x2060, 0x206F),
    (0x3164, 0x3164),
    (0xFE00, 0xFE0F),
    (0xFFA0, 0xFFA0),
    (0xFFF0, 0xFFF8),
    (0x1BCA0, 0x1BCA3),
    (0x1D173, 0x1D17A),
    (0xE0000, 0xE0FFF),
)
SURROGATE_ESCAPE_BASE = 0xDC00
SURROGATE_ESCAPE_FIRST = 0xDC80
SURROGATE_ESCAPE_C1_LAST = 0xDC9F
SURROGATE_ESCAPE_LAST = 0xDCFF

SAFE_EMAIL_DOMAINS = {"example.com", "example.net", "example.org"}
PROVENANCE_EMAIL_DOMAINS = {"noreply.github.com", "users.noreply.github.com"}
SAFE_HOME_USERS = {
    "xcsh",
    "you",
    "user",
    "users",
    "username",
    "userid",
    "your-user",
    "your_username",
    "me",
    "example",
    "alice",
    "bob",
    "runner",
    "circleci",
    "travis",
    "vsts",
    "ubuntu",
    "node",
    "jenkins",
    "gitpod",
    "index",
    "vscode",
    "...",
}
SAFE_PERSON_NAMES = {
    "dana r.",
    "kiran m.",
    "quinn n.",
    "alex t.",
    "yuri s.",
    "amal b.",
    "noam k.",
    "rosario l.",
}
SCHEMA_SENTINELS = {
    "*",
    "0",
    "any",
    "boolean",
    "integer",
    "null",
    "number",
    "object",
    "optional",
    "prefix",
    "required",
    "string",
    "suffix",
    "unknown",
    "value",
}
SAFE_IDENTITY_VALUES = {
    "123456789012",
    "console",
    "customer-123",
    "default",
    "demo",
    "demo-app",
    "example-corp",
    "library",
    "namespace for resource isolation",
    "production",
    "security",
    "shared",
    "staging",
    "system",
    "tenant or organization identifier",
    "tenant_and_identity",
    "user_namespace",
    "xc container services",
    "xc kubernetes service",
}
SAFE_PERSONAL_VALUES = {"90210"}
SAFE_XC_EXTENSION_PLACEHOLDERS = {
    "x-f5xc-",
    "x-f5xc-namespace",
    "x-f5xc-tenant",
    "x-f5xc-tenant-namespace",
    "x-f5xc-user",
}
DOCUMENTATION_NETWORKS = (
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
)
SAFE_IDENTITY_VALUES_LOWER = {item.lower() for item in SAFE_IDENTITY_VALUES}


@dataclass(frozen=True, order=True)
class Finding:
    """A redacted, actionable result from one tracked blob."""

    path: str
    line: int
    category: str
    severity: str
    message: str


@dataclass
class JqScope:
    """One nested jq delimiter with its function argument position."""

    opener: str
    context: str
    argument: int = 0


@dataclass(frozen=True)
class LineScanContext:
    """Format-aware state shared by the line-oriented detectors."""

    source_code: bool
    jq_spans: tuple[tuple[int, int], ...]
    localization_spans: tuple[tuple[int, int], ...]
    source_structure: str
    source_brace_depth: int
    enum_body_depth: int | None
    yaml_aliases: dict[str, bool]
    yaml_alias_events: tuple[tuple[int, str, bool], ...]


def input_blobs(input_dir: Path) -> Iterator[tuple[str, bytes]]:
    """Read the shell-materialized path/blob pairs in deterministic order."""

    def record_number(path: Path) -> int:
        return int(path.stem)

    for path_file in sorted(input_dir.glob("*.path"), key=record_number):
        blob_file = path_file.with_suffix(".blob")
        if not blob_file.is_file():
            message = f"materialized blob is missing for record {path_file.stem}"
            raise OSError(message)
        path = path_file.read_bytes().decode("utf-8", "surrogateescape")
        yield path, blob_file.read_bytes()


def nul_records(path: Path) -> Iterator[bytes]:
    """Yield NUL-delimited records without loading the inventory into memory."""
    remainder = b""
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            records = (remainder + chunk).split(b"\0")
            remainder = records.pop()
            yield from records
    if remainder:
        message = "history inventory is not NUL-terminated"
        raise ValueError(message)


def valid_object_id(value: bytes) -> bool:
    """Return whether a Git object ID uses a supported hash format."""
    return len(value) in {40, 64} and set(value) <= GIT_OBJECT_ID_DIGITS


def history_diff_associations(
    diff_inventory: Path,
) -> Iterator[tuple[bytes, bytes, bytes]]:
    """Yield validated mode, object, and path tuples from raw Git diffs."""
    records = iter(nul_records(diff_inventory))
    while True:
        try:
            metadata = next(records)
        except StopIteration:
            break
        try:
            path = next(records)
        except StopIteration as error:
            message = "history diff inventory is incomplete"
            raise ValueError(message) from error
        fields = metadata.split()
        if len(fields) != GIT_RAW_FIELD_COUNT:
            message = "history diff inventory is malformed"
            raise ValueError(message)
        if not fields[0].startswith(b":") or not fields[4].isalpha():
            message = "history diff inventory is malformed"
            raise ValueError(message)
        old_mode = fields[0][1:]
        new_mode, old_oid, new_oid = fields[1:4]
        modes_are_octal = set(old_mode + new_mode) <= GIT_MODE_DIGITS
        if (
            len(old_mode) != GIT_MODE_LENGTH
            or len(new_mode) != GIT_MODE_LENGTH
            or not modes_are_octal
            or not valid_object_id(old_oid)
            or not valid_object_id(new_oid)
        ):
            message = "history diff inventory metadata is invalid"
            raise ValueError(message)
        yield new_mode, new_oid, path


def history_tree_associations(
    tree_inventory: Path,
) -> Iterator[tuple[bytes, bytes, bytes]]:
    """Yield validated mode, object, and path tuples from direct tree refs."""
    for record in nul_records(tree_inventory):
        try:
            metadata, path = record.split(b"\t", 1)
            mode, object_type, oid = metadata.split()
        except ValueError as error:
            message = "history tree inventory is malformed"
            raise ValueError(message) from error
        if object_type == b"commit" and mode == b"160000":
            continue
        if object_type != b"blob":
            message = "history tree inventory contains a non-blob entry"
            raise ValueError(message)
        yield mode, oid, path


def write_history_associations(
    diff_inventory: Path,
    tree_inventory: Path,
    output: Path,
    requests: Path,
) -> None:
    """Deduplicate reachable Git path/blob associations from trusted plumbing."""
    seen: set[tuple[bytes, bytes]] = set()
    seen_oids: set[bytes] = set()

    def write_association(
        stream: BinaryIO,
        request_stream: BinaryIO,
        mode: bytes,
        oid: bytes,
        path: bytes,
    ) -> None:
        if not path or not valid_object_id(oid):
            message = "history inventory contains an invalid association"
            raise ValueError(message)
        if mode in {b"000000", b"120000", b"160000"}:
            return
        if mode not in {b"100644", b"100755"}:
            message = "history inventory contains an unsupported mode"
            raise ValueError(message)
        association = (path, oid)
        if association in seen:
            return
        seen.add(association)
        stream.write(mode + b" " + oid + b"\0" + path + b"\0")
        if oid not in seen_oids:
            seen_oids.add(oid)
            request_stream.write(oid + b"\n")

    with output.open("wb") as stream, requests.open("wb") as request_stream:
        for new_mode, new_oid, path in history_diff_associations(diff_inventory):
            write_association(stream, request_stream, new_mode, new_oid, path)

        for mode, oid, path in history_tree_associations(tree_inventory):
            write_association(stream, request_stream, mode, oid, path)


def copy_exact(source: BinaryIO, destination: BinaryIO, size: int) -> None:
    """Copy exactly one Git batch payload without buffering the full blob."""
    remaining = size
    while remaining:
        chunk = source.read(min(remaining, 1024 * 1024))
        if not chunk:
            message = "Git returned a truncated blob payload"
            raise ValueError(message)
        destination.write(chunk)
        remaining -= len(chunk)


def materialize_history_objects(
    requests: Path,
    batch_output: Path,
    object_dir: Path,
) -> dict[bytes, Path]:
    """Validate and materialize each uniquely requested Git blob."""
    object_dir.mkdir()
    objects: dict[bytes, Path] = {}
    requested_oids = requests.read_bytes().splitlines()

    with batch_output.open("rb") as source:
        for expected_oid in requested_oids:
            header = source.readline().rstrip(b"\n")
            fields = header.split()
            if (
                len(fields) != GIT_BATCH_FIELD_COUNT
                or fields[0] != expected_oid
                or fields[1] != b"blob"
                or not fields[2].isdigit()
            ):
                message = "Git returned an invalid blob header"
                raise ValueError(message)
            object_path = object_dir / expected_oid.decode("ascii")
            with object_path.open("wb") as destination:
                copy_exact(source, destination, int(fields[2]))
            if source.read(1) != b"\n":
                message = "Git returned an unterminated blob payload"
                raise ValueError(message)
            objects[expected_oid] = object_path
        if source.read(1):
            message = "Git returned unexpected trailing blob data"
            raise ValueError(message)
    return objects


def materialize_history_associations(
    associations: Path,
    requests: Path,
    batch_output: Path,
    input_dir: Path,
    start_index: int,
) -> int:
    """Materialize one validated input per path/blob association."""
    object_dir = input_dir / "history-objects"
    objects = materialize_history_objects(requests, batch_output, object_dir)

    index = start_index
    association_records = iter(nul_records(associations))
    while True:
        try:
            metadata = next(association_records)
        except StopIteration:
            break
        try:
            path = next(association_records)
            mode, oid = metadata.split()
            object_path = objects[oid]
        except (KeyError, StopIteration, ValueError) as error:
            message = "validated history association is malformed"
            raise ValueError(message) from error
        if mode not in {b"100644", b"100755"} or not path:
            message = "validated history association metadata is invalid"
            raise ValueError(message)
        index += 1
        (input_dir / f"{index}.path").write_bytes(path)
        os.link(object_path, input_dir / f"{index}.blob")
    return index


def is_legal_attribution_path(path: str) -> bool:
    """Return whether a path carries a narrow legal attribution exception."""
    basename = PurePosixPath(path).name.lower()
    return basename.startswith(LEGAL_BASENAMES)


def is_excluded(path: str) -> bool:
    """Return whether a scanner implementation fixture must be self-excluded."""
    return path in EXCLUDED_PATHS


def invisible_format_character(character: str) -> bool:
    """Return whether Unicode renders a format mark without visible width."""
    codepoint = ord(character)
    ranges = (first <= codepoint <= last for first, last in DEFAULT_IGNORABLE_RANGES)
    default_ignorable = any(ranges)
    return unicodedata.category(character) == "Cf" or default_ignorable


def safe_email(value: str) -> bool:
    """Return whether an email-shaped value is reserved or provenance-only."""
    if value.lower() == "git@github.com":
        return True
    domain = value.rsplit("@", 1)[1].lower().rstrip(".")
    return domain in SAFE_EMAIL_DOMAINS | PROVENANCE_EMAIL_DOMAINS or any(
        domain.endswith(f".{safe_domain}") for safe_domain in SAFE_EMAIL_DOMAINS
    )


def is_uri_userinfo(line: str, match: re.Match[str]) -> bool:
    """Return whether an address-shaped value belongs to URI authority userinfo."""
    prefix = URI_USERINFO_PREFIX_RE.search(line[: match.start()])
    return bool(prefix and prefix.group("scheme").lower() != "mailto")


def safe_home_user(user: str) -> bool:
    """Return whether a home path uses a documented portable placeholder."""
    if user.isdigit() or user in SAFE_HOME_USERS:
        return True
    return user.startswith(("$", "{", "<")) or "${" in user


def normalized_value(value: str) -> str:
    """Remove serialization punctuation surrounding a structured value."""
    return value.strip().strip("'\"").strip()


def serialization_nesting(text: str) -> int:
    """Count unmatched flow-collection delimiters outside quoted strings."""
    nesting = 0
    quote: str | None = None
    escaped = False
    for character in text:
        if quote:
            if character == quote and not escaped:
                quote = None
            escaped = character == "\\" and not escaped
            if character != "\\":
                escaped = False
        elif character in {"'", '"'}:
            quote = character
        elif character in "[{":
            nesting += 1
        elif character in "]}" and nesting:
            nesting -= 1
    return nesting


def balanced_dollar_brace_end(value: str, start: int = 0) -> int | None:
    """Return the end of one balanced dollar-brace placeholder."""
    index = start
    while index < len(value) and value[index] == "\\":
        index += 1
    if not value.startswith("${", index):
        return None
    depth = 1
    index += 2
    while index < len(value):
        if value.startswith("${", index):
            depth += 1
            index += 2
            continue
        if value[index] == "{":
            depth += 1
        elif value[index] == "}":
            depth -= 1
            if not depth:
                return index + 1
        index += 1
    return None


def placeholder_token_end(value: str, start: int) -> int | None:
    """Return the end of a balanced or simple whole placeholder token."""
    if end := balanced_dollar_brace_end(value, start):
        return end
    placeholder = TEMPLATE_PLACEHOLDER_RE.match(value, start)
    return placeholder.end() if placeholder else None


def top_level_character(value: str, target: str) -> int | None:
    """Locate a character outside nested braces in placeholder content."""
    depth = 0
    for index, character in enumerate(value):
        if character == "{":
            depth += 1
        elif character == "}" and depth:
            depth -= 1
        elif character == target and not depth:
            return index
    return None


def vscode_snippet_placeholder_safety(value: str) -> bool | None:
    """Classify a whole VS Code snippet placeholder and its literal defaults."""
    candidate = value
    while candidate.startswith("\\"):
        candidate = candidate[1:]
    end = balanced_dollar_brace_end(candidate)
    result: bool | None = None
    if end == len(candidate):
        content = candidate[2:-1]
        colon = top_level_character(content, ":")
        choice = top_level_character(content, "|")

        if colon is not None:
            selector = content[:colon]
            default = content[colon + 1 :]
            numeric_selector = bool(re.fullmatch(r"[0-9]+", selector))
            dynamic_selector = bool(SOURCE_SNIPPET_INDEX_RE.fullmatch(selector))
            if numeric_selector or dynamic_selector:
                result = placeholder_value(default)
        elif choice is not None and content.endswith("|"):
            selector = content[:choice]
            if re.fullmatch(r"[0-9]+", selector):
                choices = content[choice + 1 : -1].split(",")
                choice_safety = (placeholder_value(item) for item in choices)
                result = bool(choices) and all(choice_safety)
        elif re.fullmatch(r"(?:[0-9]+|[A-Z_][A-Z0-9_]*)", content):
            result = True
    return result


def json_string_end(text: str, start: int) -> int | None:
    """Return the closing quote for one JSON string token."""
    index = start + 1
    while index < len(text):
        if text[index] == "\\":
            index += 2
            continue
        if text[index] == '"':
            return index
        index += 1
    return None


def localization_top_level_string_spans(
    path: str,
    text: str,
) -> dict[int, tuple[tuple[int, int], ...]]:
    """Return top-level message-string spans in a valid localization bundle."""
    if not LOCALIZATION_BUNDLE_RE.fullmatch(PurePosixPath(path).name):
        return {}
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    if not isinstance(parsed, dict):
        return {}

    spans: dict[int, list[tuple[int, int]]] = {}
    stack: list[str] = []
    line_number = 1
    line_start = 0
    index = 0
    while index < len(text):
        character = text[index]
        if character == "\n":
            line_number += 1
            line_start = index + 1
            index += 1
            continue
        if character == '"':
            string_line = line_number
            string_start = index + 1
            previous = index - 1
            while previous >= 0 and text[previous] in " \t\r\n":
                previous -= 1
            top_level_value = stack == ["{"] and previous >= 0 and text[previous] == ":"
            string_end = json_string_end(text, index)
            if string_end is None:
                return {}
            cursor = string_end + 1
            while cursor < len(text) and text[cursor] in " \t\r\n":
                cursor += 1
            at_top_level = stack == ["{"]
            top_level_key = at_top_level and cursor < len(text) and text[cursor] == ":"
            if top_level_key or top_level_value:
                line_spans = spans.setdefault(string_line, [])
                line_spans.append((string_start - line_start, string_end - line_start))
            index = string_end + 1
            continue
        if character in "[{":
            stack.append(character)
        elif character in "]}":
            if not stack:
                return {}
            stack.pop()
        index += 1
    return {line: tuple(items) for line, items in spans.items()}


def source_structure_line(
    line: str,
    block_comment: bool,
    quote: str | None,
) -> tuple[str, bool, str | None]:
    """Mask source strings and comments while retaining structural columns."""
    structure = [" "] * len(line)
    index = 0
    while index < len(line):
        if block_comment:
            closing = line.find("*/", index)
            if closing < 0:
                return "".join(structure), True, quote
            block_comment = False
            index = closing + 2
            continue
        if quote:
            if line[index] == "\\":
                index += 2
                continue
            if line[index] == quote:
                quote = None
            index += 1
            continue
        if line.startswith("//", index):
            break
        if line.startswith("/*", index):
            block_comment = True
            index += 2
            continue
        if line[index] in {"'", '"', "`"}:
            quote = line[index]
            index += 1
            continue
        structure[index] = line[index]
        index += 1
    if quote in {"'", '"'}:
        quote = None
    return "".join(structure), block_comment, quote


def numeric_enum_member(
    match: re.Match[str],
    value: str,
    context: LineScanContext,
) -> bool:
    """Return whether a numeric field-shaped assignment is an enum member."""
    assignment = context.enum_body_depth is not None and match.group("separator") == "="
    wrapped = any(match.group(group) for group in ("quote", "key_open", "key_close"))
    if not assignment or wrapped or not NUMERIC_LITERAL_RE.fullmatch(value):
        return False
    prefix = context.source_structure[: match.start("key")]
    depth_at_key = context.source_brace_depth + prefix.count("{") - prefix.count("}")
    if depth_at_key != context.enum_body_depth:
        return False
    boundary = max(prefix.rfind("{"), prefix.rfind(","))
    if prefix[boundary + 1 :].strip():
        return False
    value_end = match.start("value") + len(value)
    return bool(re.match(r"\s*(?:,|})", context.source_structure[value_end:]))


def source_field_alias(
    match: re.Match[str],
    value: str,
    context: LineScanContext,
) -> bool:
    """Recognize exact schema field names in active source object properties.

    This does not make field-name strings safe in serialized data, comments or
    strings containing source. The masked structure must retain the property
    key and colon inside braces, with no expression following the quoted token.
    """
    if not context.source_code or match.group("separator") != ":":
        return False
    if match.group("quote") not in {"'", '"'}:
        return False
    key = match.group("key")
    aliases = {
        "first_name": "given_name",
        "given_name": "first_name",
        "last_name": "family_name",
        "family_name": "last_name",
    }
    if value not in {key, aliases.get(key)}:
        return False
    structure = context.source_structure
    if structure[match.start("key") : match.end("key")] != key:
        return False
    prefix = structure[: match.start("key")]
    depth = context.source_brace_depth + prefix.count("{") - prefix.count("}")
    if depth <= 0:
        return False
    value_end = match.start("value") + len(value) + 1
    return bool(re.match(r"\s*(?:[,;}]|$)", structure[value_end:]))


def is_vscode_view_item_context_tag(
    path: str,
    line: str,
    match: re.Match[str],
) -> bool:
    """Return whether a field-shaped token is a typed VS Code context tag."""
    if PurePosixPath(path).name != "package.json" or match.group("separator") != ":":
        return False
    for prop in VSCODE_WHEN_PROPERTY_RE.finditer(line):
        expression_start = prop.start("expression")
        expression_end = prop.end("expression")
        if not expression_start <= match.start("key") < expression_end:
            continue
        expression = prop.group("expression")
        for tag in VSCODE_VIEW_ITEM_TAG_RE.finditer(expression):
            tag_start = expression_start + tag.start("tag")
            separator = tag_start + len(tag.group("type"))
            if (
                match.start("key") == tag_start
                and match.start("separator") == separator
                and tag.group("type").lower() == match.group("key").lower()
            ):
                return True
    return False


def quoted_structured_field_value(
    line: str,
    start: int,
    quote: str,
) -> str:
    """Read a quoted structured value through escapes and YAML quote doubling."""
    index = start
    while index < len(line):
        backslashes = 0
        before = index - 1
        while before >= start and line[before] == "\\":
            backslashes += 1
            before -= 1
        yaml_single_quote = quote == "'"
        next_character_is_quote = index + 1 < len(line) and line[index + 1] == quote
        doubled_yaml_quote = yaml_single_quote and next_character_is_quote
        if line[index] == quote and doubled_yaml_quote:
            index += 2
            continue
        if line[index] == quote and backslashes % 2 == 0:
            return line[start:index]
        index += 1
    return line[start:]


def placeholder_terminates_structured_value(
    path: str,
    line: str,
    placeholder_end: int,
    flow_context: bool,
) -> bool:
    """Return whether a placeholder is the complete structured field value."""
    raw_remainder = line[placeholder_end:]
    remainder = raw_remainder.lstrip()
    if not remainder:
        return True
    if raw_remainder != remainder and remainder.startswith("#"):
        return True
    if flow_context and remainder[0] in ",}]":
        return True

    prose = PurePosixPath(path).suffix.lower() in PROSE_DOCUMENT_SUFFIXES
    if prose and re.fullmatch(r"[).;!?]+", remainder):
        return True
    following_identity = IDENTITY_FIELD_RE.match(remainder[1:].lstrip())
    return prose and remainder.startswith(",") and bool(following_identity)


def structured_field_value(path: str, line: str, match: re.Match[str]) -> str:
    """Read one field value without truncating quoted punctuation or YAML scalars."""
    start = match.start("value")
    quote = match.group("quote")
    if quote:
        return quoted_structured_field_value(line, start, quote[-1])

    suffix = PurePosixPath(path).suffix.lower()
    yaml = suffix in {".yaml", ".yml"}
    prose = suffix in PROSE_DOCUMENT_SUFFIXES
    prefix = line[:start]
    flow_context = serialization_nesting(prefix) > 0
    placeholder_end = placeholder_token_end(line, start)
    if placeholder_end is not None and placeholder_terminates_structured_value(
        path,
        line,
        placeholder_end,
        flow_context,
    ):
        return line[start:placeholder_end]

    index = start
    while index < len(line):
        character = line[index]
        if character in "}]`" or (character == "," and (not yaml or flow_context)):
            break
        if character == "#" and (index == start or line[index - 1].isspace()):
            break
        index += 1
    value = line[start:index]
    return value.rstrip(").;!?") if prose else value


def unwrapped_identity_value(value: str) -> str:
    """Remove YAML reference syntax and Markdown emphasis from a field value."""
    value = normalized_value(value)
    if tag := YAML_TAG_RE.match(value):
        return unwrapped_identity_value(value[tag.end() :])
    anchor = re.fullmatch(r"&[A-Za-z0-9_.-]+(?:\s+(.*))?", value)
    if anchor:
        return unwrapped_identity_value(anchor.group(1) or "")
    strong_emphasis = re.fullmatch(r"(?:\*\*|__)(.+?)(?:\*\*|__)", value)
    if strong_emphasis:
        return unwrapped_identity_value(strong_emphasis.group(1))
    emphasis = re.fullmatch(r"[*_](.+?)[*_]", value)
    if emphasis:
        return unwrapped_identity_value(emphasis.group(1))
    alias = re.fullmatch(r"\*([A-Za-z0-9_.-]+)", value)
    return unwrapped_identity_value(alias.group(1)) if alias else value


def schema_placeholder_value(lower: str) -> bool:
    """Return whether a normalized value is a safe schema placeholder."""
    if lower in SCHEMA_SENTINELS:
        return True
    if lower in SAFE_IDENTITY_VALUES_LOWER:
        return True
    return lower in SAFE_XC_EXTENSION_PLACEHOLDERS


def placeholder_value(value: str) -> bool:
    """Return whether a value is synthetic, schematic, or schema syntax."""
    value = unwrapped_identity_value(value)
    if not value:
        return True
    snippet_safety = vscode_snippet_placeholder_safety(value)
    if snippet_safety is not None:
        return snippet_safety
    lower = value.lower()
    if (
        schema_placeholder_value(lower)
        or lower in {"false", "true", "~"}
        or decimal_numeric_value(value) == 0
        or bool(re.fullmatch(r"[|>](?:[+-]?[1-9]?|[1-9][+-])", value))
    ):
        return True
    if re.fullmatch(r"example(?:[-_.][a-z0-9]+)*", lower):
        return True
    if re.fullmatch(r"x[A-Z][A-Z0-9_]*x", value):
        return True
    first, separator, second = value.partition("|")
    if first and separator and second and "|" not in second:
        safe_composite = placeholder_value(first) and placeholder_value(second)
    else:
        safe_composite = False
    return (
        safe_composite
        or lower in SAFE_PERSON_NAMES
        or bool(TEMPLATE_PLACEHOLDER_RE.fullmatch(value))
        or bool(re.fullmatch(r"[A-Z][A-Z0-9_]*", value))
    )


def is_proven_prose_identity_label(path: str, line: str, match: re.Match[str]) -> bool:
    """Return whether an identity-shaped token is demonstrably an ordinary prose label."""
    if (
        PurePosixPath(path).suffix.lower() not in PROSE_DOCUMENT_SUFFIXES
        or match.group("separator") != ":"
        or not match.group("field_prefix").isspace()
        or bool(match.group("key_open"))
        or bool(match.group("key_close"))
    ):
        return False
    before = line[: match.start()].rstrip()
    if not PROSE_IDENTITY_QUANTIFIER_RE.search(before):
        return False
    prose = line[match.start("separator") + 1 :].strip()
    quote_pairs = {"'": "'", '"': '"', "\u2018": "\u2019", "\u201c": "\u201d"}
    closing_quote = quote_pairs.get(prose[:1])
    if closing_quote:
        closing = prose.find(closing_quote, 1)
        if closing < 0:
            return False
        trailing_prose = prose[closing + 1 :].strip()
        if not PROSE_SAFE_CONTINUATION_RE.fullmatch(trailing_prose):
            return False
        prose = prose[1:closing]
    return bool(PROSE_SAFE_LANGUAGE_RE.fullmatch(prose))


def is_structured_identity_field(path: str, line: str, match: re.Match[str]) -> bool:
    """Return whether an identity-shaped token should be enforced as structured data."""
    key_open = match.group("key_open")
    key_close = match.group("key_close")
    whole_inline_field = key_open == "`" and "`" in line[match.end() :]
    balanced_wrappers = sorted(key_open) == sorted(key_close)
    if not balanced_wrappers and not whole_inline_field:
        return False
    if match.group("field_prefix") == "." and match.group("separator") != "=":
        return False
    if is_vscode_view_item_context_tag(path, line, match):
        return False
    return not is_proven_prose_identity_label(path, line, match)


def is_source_comment(line: str, match: re.Match[str]) -> bool:
    """Return whether a field-shaped token occurs after a source comment marker."""
    prefix = line[: match.start("key")]
    prefix = re.sub(
        r"(^|[\s;])#(?=[A-Za-z_$][A-Za-z0-9_$]*\s*\()",
        r"\1",
        prefix,
    )
    return bool(re.search(r"(?:^|[\s;])(?://|#|/\*|\*)\s*[^\r\n]*$", prefix))


def match_is_in_spans(match: re.Match[str], spans: tuple[tuple[int, int], ...]) -> bool:
    """Return whether a field key begins inside one of the supplied source spans."""
    key_start = match.start("key")
    return any(start <= key_start < end for start, end in spans)


def jq_field_expression(line: str, start: int, shell_quote: str | None) -> str:
    """Return one jq field expression, honoring strings and nested delimiters."""
    expression = line[start:]
    if shell_quote == '"':
        expression = SHELL_DOUBLE_ESCAPE_RE.sub(r"\1", expression)
    quote: str | None = None
    escaped = False
    nesting = 0
    for index, character in enumerate(expression):
        if quote:
            if character == quote and not escaped:
                quote = None
            escaped = character == "\\" and not escaped
            if character != "\\":
                escaped = False
            continue
        if character in {"'", '"'}:
            quote = character
        elif character in "([{":
            nesting += 1
        elif character in ")]}":
            if nesting:
                nesting -= 1
            elif character == "}":
                return expression[:index]
        elif character == "," and not nesting:
            return expression[:index]
    return expression


def jq_bracket_is_index(prefix: str) -> bool:
    """Return whether an opening bracket indexes a preceding jq filter."""
    structured_filter = bool(
        re.search(
            r"(?:[)\]}]|\$[A-Za-z_]\w*|\.(?:[A-Za-z_]\w*)?|"
            r"[A-Za-z_$]\w*(?:\.[A-Za-z_$]\w*)+)\s*$",
            prefix,
        )
    )
    bare_filter = re.search(r"([A-Za-z_]\w*)\s*$", prefix)
    if not bare_filter:
        return structured_filter
    return structured_filter or bare_filter.group(1) not in JQ_NON_INDEX_KEYWORDS


def decimal_numeric_value(value: str) -> Decimal | None:
    """Parse a jq-compatible decimal literal for semantic comparisons."""
    compact = value.replace("_", "").rstrip(";")
    try:
        return Decimal(compact)
    except InvalidOperation:
        return None


def jq_arithmetic_literal_is_neutral(value: str) -> bool:
    """Return whether a numeric operand is a conventional arithmetic modifier."""
    numeric = decimal_numeric_value(value)
    return numeric in {Decimal(-1), Decimal(0), Decimal(1)}


def jq_interpolation_end(value: str, start: int) -> int | None:
    """Return the closing parenthesis for one jq string interpolation."""
    quote: str | None = None
    escaped = False
    depth = 1
    index = start
    while index < len(value):
        character = value[index]
        if quote:
            if character == quote and not escaped:
                quote = None
            escaped = character == "\\" and not escaped
            if character != "\\":
                escaped = False
        elif character in {"'", '"'}:
            quote = character
        elif character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if not depth:
                return index
        index += 1
    return None


def jq_string_end(value: str, start: int, quote: str) -> int:
    """Return a jq string's closing quote without stopping inside interpolation."""
    index = start
    while index < len(value):
        if value[index] == "\\":
            run_end = index
            while run_end < len(value) and value[run_end] == "\\":
                run_end += 1
            odd_backslashes = (run_end - index) % 2 == 1
            interpolation = quote == '"' and odd_backslashes
            interpolation = interpolation and value[run_end : run_end + 1] == "("
            if interpolation:
                closing = jq_interpolation_end(value, run_end + 1)
                if closing is None:
                    return len(value)
                index = closing + 1
                continue
            escaped_character = (run_end - index) % 2 == 1 and run_end < len(value)
            index = run_end + 1 if escaped_character else run_end
            continue
        if value[index] == quote:
            return index
        index += 1
    return len(value)


def jq_unwrap_outer_groups(value: str) -> str:
    """Remove redundant parentheses enclosing an entire jq expression."""
    candidate = value.strip()
    while candidate.startswith("("):
        closing = jq_interpolation_end(candidate, 1)
        if closing != len(candidate) - 1:
            break
        candidate = candidate[1:closing].strip()
    return candidate


def jq_top_level_pipe_parts(value: str) -> list[str]:
    """Split a jq expression only at pipelines outside strings and delimiters."""
    parts: list[str] = []
    quote: str | None = None
    escaped = False
    nesting = 0
    start = 0
    for index, character in enumerate(value):
        if quote:
            if character == quote and not escaped:
                quote = None
            escaped = character == "\\" and not escaped
            if character != "\\":
                escaped = False
            continue
        if character in {"'", '"'}:
            quote = character
        elif character in "([{":
            nesting += 1
        elif character in ")]}" and nesting:
            nesting -= 1
        elif character == "|" and not nesting:
            parts.append(value[start:index].strip())
            start = index + 1
    parts.append(value[start:].strip())
    return parts


def jq_expression_is_identity_filter(value: str) -> bool:
    """Return whether a jq expression is only grouped identity filters."""
    candidate = jq_unwrap_outer_groups(value)
    parts = jq_top_level_pipe_parts(candidate)
    if len(parts) > 1:
        return all(jq_expression_is_identity_filter(part) for part in parts)
    return candidate == "."


def jq_identity_constant_expression(value: str) -> str:
    """Remove redundant groups and identity-only pipes from a jq expression."""
    candidate = jq_unwrap_outer_groups(value)
    while candidate:
        parts = jq_top_level_pipe_parts(candidate)
        if len(parts) == 1 or not jq_expression_is_identity_filter(parts[-1]):
            break
        candidate = jq_unwrap_outer_groups("|".join(parts[:-1]))
    return candidate


def jq_constant_string(value: str) -> str | None:
    """Return the content of a simple constant jq interpolation expression."""
    candidate = jq_identity_constant_expression(value)
    if not candidate or candidate[0] not in {"'", '"'}:
        return None
    closing = jq_string_end(candidate, 1, candidate[0])
    if closing != len(candidate) - 1:
        return None
    return candidate[1:closing]


def jq_constant_scalar(value: str) -> str | None:
    """Return a scalar jq interpolation followed only by identity filters."""
    candidate = jq_identity_constant_expression(value)
    if candidate in {"false", "null", "true"}:
        return candidate
    if NUMERIC_LITERAL_RE.fullmatch(candidate):
        numeric = decimal_numeric_value(candidate)
        return str(numeric) if numeric is not None else candidate.rstrip(";")
    return None


def jq_literal_fragments(value: str) -> list[str]:
    """Remove real jq interpolations while retaining escaped interpolation text."""
    fragments: list[str] = []
    current: list[str] = []
    index = 0
    while index < len(value):
        if value[index] != "\\":
            current.append(value[index])
            index += 1
            continue
        run_end = index
        while run_end < len(value) and value[run_end] == "\\":
            run_end += 1
        backslashes = run_end - index
        interpolation = run_end < len(value) and value[run_end] == "("
        if not interpolation or backslashes % 2 == 0:
            current.extend("\\" * backslashes)
            index = run_end
            continue
        current.extend("\\" * (backslashes // 2))
        closing = jq_interpolation_end(value, run_end + 1)
        if closing is None:
            current.extend(value[index:])
            break
        constant = jq_constant_string(value[run_end + 1 : closing])
        if constant is not None:
            nested_fragments = jq_literal_fragments(constant)
            constant = nested_fragments[0] if len(nested_fragments) == 1 else None
        if constant is None:
            expression = value[run_end + 1 : closing]
            constant = jq_constant_scalar(expression)
        if constant is None:
            fragments.append("".join(current))
            current = []
        else:
            current.extend(constant)
        index = closing + 1
    fragments.append("".join(current))
    return fragments


def jq_open_scope(expression: str, index: int) -> JqScope:
    """Classify a jq opening delimiter as a call, group, container, or index."""
    opener = expression[index]
    prefix = expression[:index]
    if opener == "(":
        function = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\s*$", prefix)
        return JqScope(opener, function.group(1) if function else "group")
    if opener == "[":
        context = "index" if jq_bracket_is_index(prefix) else "array"
        return JqScope(opener, context)
    return JqScope(opener, "object")


def jq_close_scope(scopes: list[JqScope], closer: str) -> None:
    """Close a well-formed jq delimiter without corrupting outer context."""
    opener = {")": "(", "]": "[", "}": "{"}[closer]
    if scopes and scopes[-1].opener == opener:
        scopes.pop()


def jq_advance_argument(scopes: list[JqScope]) -> None:
    """Advance only a semicolon's immediate function/group argument."""
    if scopes and scopes[-1].opener == "(":
        scopes[-1].argument += 1


def jq_positional_roles(scopes: list[JqScope]) -> tuple[bool, bool]:
    """Return whether active jq calls place a literal in output/control roles."""
    output = False
    control = False
    for scope in scopes:
        output_arguments = POSITIONAL_JQ_OUTPUT_ARGUMENTS.get(scope.context)
        if output_arguments is None:
            continue
        if scope.argument in output_arguments:
            output = True
        else:
            control = True
    return output, control


def jq_range_bound_is_identifier_sized(value: str) -> bool:
    """Return whether a range bound is large enough to resemble an identifier."""
    numeric = decimal_numeric_value(value)
    return numeric is not None and abs(numeric) >= Decimal(100000)


def decode_jq_unicode_escapes(value: str) -> str:
    """Decode parity-valid jq Unicode escapes for placeholder comparison."""
    decoded: list[str] = []
    index = 0
    while index < len(value):
        if value[index] != "\\":
            decoded.append(value[index])
            index += 1
            continue
        run_end = index
        while run_end < len(value) and value[run_end] == "\\":
            run_end += 1
        backslashes = run_end - index
        escape_end = run_end + 5
        unicode_escape = (
            backslashes % 2 == 1
            and escape_end <= len(value)
            and value[run_end : run_end + 1] == "u"
            and bool(re.fullmatch(r"[0-9A-Fa-f]{4}", value[run_end + 1 : escape_end]))
        )
        decoded.extend("\\" * (backslashes // 2))
        if unicode_escape:
            decoded.append(chr(int(value[run_end + 1 : escape_end], 16)))
            index = escape_end
        else:
            decoded.extend("\\" * (backslashes % 2))
            index = run_end
    return "".join(decoded)


# pylint: disable-next=too-many-locals
def jq_output_strings(expression: str) -> list[str]:
    """Return jq strings that contribute to the field value, not control functions."""
    strings: list[str] = []
    scopes: list[JqScope] = []
    index = 0
    while index < len(expression):
        character = expression[index]
        if character in "([{":
            scopes.append(jq_open_scope(expression, index))
            index += 1
            continue
        if character in ")]}":
            jq_close_scope(scopes, character)
            index += 1
            continue
        if character == ";":
            jq_advance_argument(scopes)
            index += 1
            continue
        if character not in {"'", '"'}:
            index += 1
            continue
        string_start = index
        quote = character
        index = jq_string_end(expression, index + 1, quote)
        value = expression[string_start + 1 : index]
        active_functions = {scope.context for scope in scopes}
        _, positional_control = jq_positional_roles(scopes)
        prefix = expression[:string_start]
        suffix = expression[index + 1 :]
        comparison_before = bool(re.search(r"(?:==|!=|<=|>=|<|>)\s*$", prefix))
        comparison_after = bool(re.match(r"\s*(?:==|!=|<=|>=|<|>)", suffix))
        object_key = bool(re.match(r"\s*:", suffix))
        control_string = bool(active_functions & NON_OUTPUT_JQ_STRING_FUNCTIONS)
        comparison_string = comparison_before or comparison_after
        predicate_input = bool(re.match(r"\s*\|\s*(?:IN|all|any|in|isempty)\b", suffix))
        conditional_prefix = bool(re.search(r"\b(?:elif|if)\s*$", prefix))
        suffix_has_then = bool(re.search(r"\bthen\b", suffix))
        conditional_control = conditional_prefix and suffix_has_then
        ignored_string = comparison_string or object_key or control_string
        ignored_string = ignored_string or positional_control
        ignored_string = ignored_string or predicate_input or conditional_control
        if not ignored_string:
            strings.append(value)
        index += 1
    return strings


# pylint: disable-next=too-many-locals,too-many-statements
def jq_output_numbers(expression: str) -> list[str]:
    """Return numeric literals that contribute to a jq field value."""
    numbers: list[str] = []
    scopes: list[JqScope] = []
    index = 0
    number_re = re.compile(
        r"[+-]?(?:0[xX][0-9A-Fa-f_]+|0[bB][01_]+|0[oO][0-7_]+|"
        r"[0-9][0-9_]*(?:\.[0-9_]+)?(?:[eE][+-]?[0-9][0-9_]*)?)"
    )
    while index < len(expression):
        character = expression[index]
        if character in {"'", '"'}:
            index = jq_string_end(expression, index + 1, character) + 1
            continue
        if character in "([{":
            scopes.append(jq_open_scope(expression, index))
            index += 1
            continue
        if character in ")]}":
            jq_close_scope(scopes, character)
            index += 1
            continue
        if character == ";":
            jq_advance_argument(scopes)
            index += 1
            continue
        number = number_re.match(expression, index)
        if not number:
            index += 1
            continue
        prefix = expression[:index]
        suffix = expression[number.end() :]
        leading_operator = number.group().startswith(("+", "-")) and bool(
            re.search(r"(?:[A-Za-z0-9_$.)\]}])\s*$", prefix)
        )
        identifier_prefix = index > 0 and expression[index - 1].isalnum()
        identifier_fragment = identifier_prefix and not leading_operator
        comparison = bool(re.search(r"(?:==|!=|<=|>=|<|>)\s*$", prefix))
        comparison = comparison or bool(re.match(r"\s*(?:==|!=|<=|>=|<|>)", suffix))
        object_key = bool(re.match(r"\s*:", suffix))
        active_functions = {scope.context for scope in scopes}
        control_number = bool(active_functions & NON_OUTPUT_JQ_NUMBER_FUNCTIONS)
        control_number = control_number or "index" in active_functions
        range_scopes = [scope for scope in scopes if scope.context == "range"]
        range_args = (scope.argument for scope in range_scopes)
        range_control = any(arg not in JQ_RANGE_OUTPUT_ARGUMENTS for arg in range_args)
        control_number = control_number or range_control
        positional_output, positional_control = jq_positional_roles(scopes)
        control_number = control_number or positional_control
        object_value = bool(
            re.search(
                r"(?:^|[{,])\s*(?:[A-Za-z_]\w*|['\"][^'\"]+['\"])\s*:\s*$",
                prefix,
            )
        )
        literal_container = "array" in active_functions or object_value
        output_branch = bool(re.search(r"(?:then|else|try|catch)\s*$", prefix))
        output_function = bool(
            active_functions
            - NON_OUTPUT_JQ_NUMBER_FUNCTIONS
            - POSITIONAL_JQ_OUTPUT_ARGUMENTS.keys()
            - {"array", "group", "index", "object", "range"}
        )
        group_starts_literal = bool(re.search(r"(?:^|[(:,;])\s*$", prefix))
        grouped_literal = "group" in active_functions and group_starts_literal
        arithmetic = leading_operator or bool(re.search(r"[+*/%-]\s*$", prefix))
        arithmetic = arithmetic or bool(re.match(r"\s*[+*/%-]", suffix))
        dynamic_expression = bool(
            re.search(
                r"(?:\.[A-Za-z_]|\$[A-Za-z_]|(?:env|input)\b)",
                expression,
            )
        )
        pipe_output = bool(re.search(r"\|\s*$", prefix))
        pipe_passthrough = bool(re.fullmatch(r"(?:\s*\|\s*\.)+\s*", suffix))
        constant_arithmetic = arithmetic and not dynamic_expression
        cancels_input = bool(re.search(r"(?:\*\s*0\b|\b0\s*\*)", expression))
        cancels_dynamic_input = dynamic_expression and cancels_input
        nonneutral = not jq_arithmetic_literal_is_neutral(number.group())
        sensitive_arithmetic = arithmetic and (nonneutral or cancels_dynamic_input)
        range_bound = any(s.argument in JQ_RANGE_OUTPUT_ARGUMENTS for s in range_scopes)
        identifier_sized_range = jq_range_bound_is_identifier_sized(number.group())
        range_output = range_bound and identifier_sized_range
        output_literal = literal_container or output_branch or output_function
        output_literal = (
            output_literal
            or grouped_literal
            or positional_output
            or range_output
            or pipe_output
            or pipe_passthrough
            or constant_arithmetic
            or sensitive_arithmetic
        )
        ignored = (
            identifier_fragment
            or comparison
            or object_key
            or control_number
            or (arithmetic and dynamic_expression and not sensitive_arithmetic)
        )
        if output_literal and not ignored:
            numbers.append(number.group())
        index = number.end()
    return numbers


def jq_value_is_expression(
    line: str,
    match: re.Match[str],
    jq_spans: tuple[tuple[int, int], ...],
) -> bool:
    """Return whether a value inside a jq program is computed rather than literal."""
    shell_quote: str | None = None
    for span_start, span_end in jq_spans:
        if span_start <= match.start("key") < span_end:
            if span_start and line[span_start - 1] in {"'", '"'}:
                shell_quote = line[span_start - 1]
            break
    expression = jq_field_expression(line, match.start("separator") + 1, shell_quote)
    for quoted_value in jq_output_strings(expression):
        for fragment in jq_literal_fragments(quoted_value):
            decoded_fragment = decode_jq_unicode_escapes(fragment)
            literal_fragment = decoded_fragment.strip(" -_.:/\\")
            has_identity_text = any(map(str.isalnum, literal_fragment))
            if not literal_fragment or not has_identity_text:
                continue
            repeated_example_root = literal_fragment.lower().count("example") > 1
            numeric_suffix = bool(re.search(r"[A-Za-z][0-9]{6,}$", literal_fragment))
            unsafe_composition = repeated_example_root or numeric_suffix
            if unsafe_composition or not placeholder_value(literal_fragment):
                return False
    for number in jq_output_numbers(expression):
        if not placeholder_value(number):
            return False
    fallback_numbers = re.findall(
        r"//\s*([+-]?[0-9][0-9_]*(?:\.[0-9_]+)?"
        r"(?:[eE][+-]?[0-9][0-9_]*)?)",
        expression,
    )
    return all(placeholder_value(number) for number in fallback_numbers)


def source_template_interpolation(line: str, start: int) -> tuple[str, int] | None:
    """Read one JavaScript-style template interpolation and its closing brace."""
    if not line.startswith("${", start):
        return None
    depth = 1
    index = start + 2
    quote: str | None = None
    while index < len(line):
        character = line[index]
        if quote:
            if character == "\\":
                index += 2
                continue
            if character == quote:
                quote = None
        elif character in {"'", '"'}:
            quote = character
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return line[start + 2 : index], index
        index += 1
    return None


def source_template_value_is_expression(
    line: str,
    match: re.Match[str],
) -> bool:
    """Return whether a template field computes a value without literal identity data."""
    interpolation = source_template_interpolation(line, match.start("value"))
    if interpolation is None:
        return False
    expression, closing = interpolation
    strings = SOURCE_TEMPLATE_STRING_RE.finditer(expression)
    if any(not placeholder_value(item.group("value")) for item in strings):
        return False
    expression_without_strings = SOURCE_TEMPLATE_STRING_RE.sub("", expression)
    if not re.search(r"[A-Za-z_$]", expression_without_strings):
        return False
    remainder = line[closing + 1 :]
    closes_template = remainder.startswith("`")
    starts_sentence = bool(re.match(r"^(?:[.,;!?)]\s|\s+\()", remainder))
    return closes_template or starts_sentence


def is_nonliteral_code_expression(
    line: str,
    match: re.Match[str],
    *,
    source_code: bool,
    jq_spans: tuple[tuple[int, int], ...],
    value_override: str | None = None,
) -> bool:
    """Return whether a structured field is executable or type syntax, not data."""
    value = normalized_value(value_override or match.group("value"))
    numeric_literal = bool(NUMERIC_LITERAL_RE.fullmatch(value))
    in_jq_filter = match_is_in_spans(match, jq_spans)
    in_source_comment = (source_code or in_jq_filter) and is_source_comment(line, match)
    if numeric_literal:
        return False
    if in_source_comment:
        expression = value.rstrip(";").strip()
        return bool(SOURCE_COMMENT_EXPRESSION_RE.fullmatch(expression))
    groups = match.groupdict()
    inline_key_opener = groups.get("key_open") == "`"
    inline_key_closer = bool(groups.get("key_close"))
    inline_field_closer = "`" in line[match.end() :]
    unclosed_inline_key = inline_key_opener and not inline_key_closer
    whole_inline_field = unclosed_inline_key and inline_field_closer
    if whole_inline_field:
        expression = value.rstrip(";").strip()
        named_expression = bool(SOURCE_COMMENT_EXPRESSION_RE.fullmatch(expression))
        interpolation = source_template_value_is_expression(line, match)
        return expression.startswith(".") or named_expression or interpolation
    if in_jq_filter:
        return jq_value_is_expression(line, match, jq_spans)
    return source_code and not bool(match.group("quote"))


def safe_phone(value: str) -> bool:
    """Return whether a phone number uses NANP's fictional 555-0100--0199 block."""
    digits = re.sub(r"\D", "", value)
    if len(digits) in {8, 11} and digits.startswith("1"):
        digits = digits[1:]
    return bool(re.fullmatch(r"(?:[2-9][0-9]{2})?55501[0-9]{2}", digits))


def add_finding(
    findings: set[Finding],
    *,
    path: str,
    line: int,
    category: str,
    message: str,
) -> None:
    """Add one redacted and deduplicated finding."""
    findings.add(
        Finding(
            path=redact_path(path),
            line=line,
            category=category,
            severity="high",
            message=message,
        )
    )


def add_review_finding(
    findings: set[Finding],
    *,
    path: str,
    line: int,
    category: str,
    message: str,
) -> None:
    """Add one redacted and deduplicated manual-review finding."""
    findings.add(
        Finding(
            path=redact_path(path),
            line=line,
            category=category,
            severity="review",
            message=message,
        )
    )


def redact_path(path: str) -> str:
    """Prevent a sensitive filename from being copied into scanner output."""
    redacted = EMAIL_RE.sub("<redacted-email>", path)

    def replace_home(match: re.Match[str]) -> str:
        prefix = match.group("prefix") or match.group("winprefix") or ""
        return f"{prefix}<redacted-user>"

    redacted = HOME_RE.sub(replace_home, redacted)
    if redacted != path:
        encoded_path = path.encode("utf-8", "surrogateescape")
        digest = hashlib.sha256(encoded_path).hexdigest()[:12]
        return f"{redacted} [path-sha256:{digest}]"
    return redacted


def closing_shell_quote(line: str, start: int, quote: str) -> int | None:
    """Find the end of one shell-quoted jq filter on a physical line."""
    index = start
    while index < len(line):
        backslashes = 0
        before = index - 1
        while before >= 0 and line[before] == "\\":
            backslashes += 1
            before -= 1
        quote_is_unescaped = quote == "'" or backslashes % 2 == 0
        if line[index] == quote and quote_is_unescaped:
            return index
        index += 1
    return None


def shell_words(
    line: str,
    start: int,
) -> list[tuple[int, int, int, str | None, bool]]:
    """Split a shell command into word spans without evaluating its contents."""
    words: list[tuple[int, int, int, str | None, bool]] = []
    index = start
    while index < len(line):
        while index < len(line) and line[index].isspace():
            index += 1
        if index >= len(line) or line[index] in ";|&":
            break
        quote = line[index] if line[index] in {"'", '"'} else None
        if quote:
            content_start = index + 1
            closing = closing_shell_quote(line, content_start, quote)
            if closing is None:
                words.append((content_start, len(line), len(line), quote, False))
                break
            words.append((content_start, closing, closing + 1, quote, True))
            index = closing + 1
            continue
        content_start = index
        while index < len(line):
            if line[index].isspace() or line[index] in ";|&":
                break
            index += 1
        words.append((content_start, index, index, None, True))
    return words


def jq_program_word(
    line: str,
    words: list[tuple[int, int, int, str | None, bool]],
) -> tuple[int, int, int, str | None, bool] | None:
    """Return jq's filter word after consuming options and their arguments."""
    index = 0
    while index < len(words):
        word = words[index]
        word_text = line[word[0] : word[1]]
        if word_text == "--":
            return words[index + 1] if index + 1 < len(words) else None
        if not word_text.startswith("-") or word_text == "-":
            return word
        option = word_text.split("=", 1)[0]
        index += 1 + JQ_OPTION_ARITY.get(option, 0)
    return None


def jq_filter_spans(
    line: str,
    active_quote: str | None,
) -> tuple[tuple[tuple[int, int], ...], str | None]:
    """Locate shell-quoted jq programs without leaking across command boundaries."""
    spans: list[tuple[int, int]] = []
    cursor = 0
    if active_quote:
        closing = closing_shell_quote(line, 0, active_quote)
        if closing is None:
            return ((0, len(line)),), active_quote
        spans.append((0, closing))
        cursor = closing + 1

    while command := JQ_COMMAND_RE.search(line, cursor):
        program = jq_program_word(line, shell_words(line, command.end()))
        if program is None:
            break
        content_start, content_end, raw_end, quote, closed = program
        spans.append((content_start, content_end))
        if not closed:
            return tuple(spans), quote
        cursor = raw_end
    return tuple(spans), None


def is_json_structured_literal(
    path: str,
    line: str,
    match: re.Match[str],
) -> bool:
    """Return whether a JSON regex match is a scalar object-field value.

    Generated OpenAPI JSON contains identity-shaped prose in descriptions and
    schema property objects such as ``"namespace": { ... }``. Neither is a
    literal identity value. Keep scanning real scalar fields while requiring
    the matched key to be a JSON string token and rejecting container values.
    """
    value = normalized_value(structured_field_value(path, line, match))
    json_path = PurePosixPath(path).suffix.lower() == ".json"
    if (json_path and value.startswith("{")) or value == "{":
        return False
    if not json_path or VSCODE_WHEN_PROPERTY_RE.search(line):
        return True
    key_start = match.start("key")
    key_end = match.end("key")
    key_starts_with_quote = key_start > 0 and line[key_start - 1] == '"'
    key_ends_with_quote = line[key_end : key_end + 1] == '"'
    return key_starts_with_quote and key_ends_with_quote


def is_literal_structured_identity_field(
    path: str,
    line: str,
    match: re.Match[str],
) -> bool:
    """Return whether an identity field has a scalar, literal JSON representation."""
    if not is_structured_identity_field(path, line, match):
        return False
    return is_json_structured_literal(path, line, match)


def has_literal_structured_value(
    path: str,
    line: str,
    match: re.Match[str],
    context: LineScanContext,
    value: str,
) -> bool:
    """Return whether a structured value is scalar data rather than source syntax."""
    if not is_json_structured_literal(path, line, match):
        return False
    if source_field_alias(match, value, context):
        return False
    return not is_nonliteral_code_expression(
        line,
        match,
        source_code=context.source_code,
        jq_spans=context.jq_spans,
        value_override=value,
    )


def explicitly_safe_personal_value(value: str) -> bool:
    """Return whether a value is an explicitly documented synthetic personal value."""
    return normalized_value(value) in SAFE_PERSONAL_VALUES


def scan_contacts(
    path: str,
    line_number: int,
    line: str,
    attribution_context: bool,
    findings: set[Finding],
    context: LineScanContext,
) -> None:
    """Scan one line for contact details, home paths, and person names."""
    if not attribution_context:
        for match in EMAIL_RE.finditer(line):
            if not safe_email(match.group(0)) and not is_uri_userinfo(line, match):
                add_finding(
                    findings,
                    path=path,
                    line=line_number,
                    category="email",
                    message="email address does not use a documentation-reserved domain",
                )
        for match in PERSON_FIELD_RE.finditer(line):
            if match_is_in_spans(match, context.localization_spans):
                continue
            value = structured_field_value(path, line, match)
            if not is_json_structured_literal(path, line, match):
                continue
            numeric_name = NUMERIC_LITERAL_RE.fullmatch(value)
            if numeric_name or source_field_alias(match, value, context):
                continue
            if is_nonliteral_code_expression(
                line,
                match,
                source_code=context.source_code,
                jq_spans=context.jq_spans,
                value_override=value,
            ):
                continue
            if not placeholder_value(value):
                if match.group("key").lower() == "display_name":
                    add_review_finding(
                        findings,
                        path=path,
                        line=line_number,
                        category="display-name-review",
                        message="display_name requires manual identity review",
                    )
                else:
                    add_finding(
                        findings,
                        path=path,
                        line=line_number,
                        category="person-name",
                        message=f"{match.group('key')} contains a literal person name",
                    )

    for match in HOME_RE.finditer(line):
        user = match.group("user") or match.group("winuser") or ""
        if not safe_home_user(user):
            add_finding(
                findings,
                path=path,
                line=line_number,
                category="home-path",
                message="home-directory path contains a non-placeholder user segment",
            )

    for match in PHONE_FIELD_RE.finditer(line):
        if not safe_phone(match.group("value")):
            add_finding(
                findings,
                path=path,
                line=line_number,
                category="phone",
                message="phone field does not use the fictional NANP range",
            )


def scan_structured_identity(
    path: str,
    line_number: int,
    line: str,
    findings: set[Finding],
    context: LineScanContext,
) -> None:
    """Scan structured fields for customer identifiers and personal records."""
    for match in IDENTITY_FIELD_RE.finditer(line):
        if match_is_in_spans(match, context.localization_spans):
            continue
        if not is_literal_structured_identity_field(path, line, match):
            continue
        value = structured_field_value(path, line, match)
        if numeric_enum_member(match, value, context):
            continue
        if source_field_alias(match, value, context):
            continue
        in_jq_span = match_is_in_spans(match, context.jq_spans)
        jq_literal = in_jq_span and not jq_value_is_expression(
            line,
            match,
            context.jq_spans,
        )
        if is_nonliteral_code_expression(
            line,
            match,
            source_code=context.source_code,
            jq_spans=context.jq_spans,
            value_override=value,
        ):
            continue
        alias = None
        if not match.group("quote"):
            alias = re.fullmatch(r"\*([A-Za-z0-9_.-]+)", normalized_value(value))
        if alias:
            aliases_at_value = context.yaml_aliases.copy()
            for position, name, safe in context.yaml_alias_events:
                if position >= match.start("value"):
                    break
                aliases_at_value[name] = safe
            safe_alias = aliases_at_value.get(alias.group(1), False)
        else:
            safe_alias = None
        if jq_literal or not (safe_alias if alias else placeholder_value(value)):
            add_finding(
                findings,
                path=path,
                line=line_number,
                category="customer-identifier",
                message=f"{match.group('key')} contains a literal organization identifier",
            )

    for match in ADDRESS_FIELD_RE.finditer(line):
        value = structured_field_value(path, line, match)
        if not has_literal_structured_value(path, line, match, context, value):
            continue
        if not (placeholder_value(value) or explicitly_safe_personal_value(value)):
            add_finding(
                findings,
                path=path,
                line=line_number,
                category="personal-record",
                message=f"{match.group('key')} contains a literal personal value",
            )


# fmt: off
def scan_jq_identity_writes(
    path: str,
    line_number: int,
    line: str,
    findings: set[Finding],
    _context: LineScanContext,
) -> None:
    """Inspect exact --arg/--argjson values flowing to jq identity object fields."""
    if not path.endswith(".sh") or "jq" not in line:
        return
    bindings = {
        match.group("name"): match.group("value").strip("'\"")
        for match in re.finditer(
            r"(?:--arg|--argjson)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s+(?P<value>[^\s]+)",
            line,
        )
    }
    key = r"tenant(?:_name|_id|-name|-id|Name|Id)?|customer(?:_name|_id|-name|-id|Name|Id)?|account(?:_name|_id|-name|-id|Name|Id)?|subscription(?:_name|_id|-name|-id|Name|Id)|project(?:_name|_id|-name|-id|Name|Id)|namespace"
    for field in re.finditer(
        rf"(?P<key>{key})\s*:\s*\$(?P<name>[A-Za-z_][A-Za-z0-9_]*)", line, re.IGNORECASE
    ):
        value = bindings.get(field.group("name"), "")
        if value and not placeholder_value(value):
            add_finding(
                findings,
                path=path,
                line=line_number,
                category="customer-identifier",
                message=f"{field.group('key')} contains a literal organization identifier",
            )

# fmt: on
# fmt: off
def scan_multiline_identity_fields(
    path: str, text: str, findings: set[Finding]
) -> None:
    """Cover JSON/YAML keys and scalar values separated by physical lines."""
    key = r"tenant(?:_name|_id|-name|-id|Name|Id)?|customer(?:_name|_id|-name|-id|Name|Id)?|account(?:_name|_id|-name|-id|Name|Id)?|subscription(?:_name|_id|-name|-id|Name|Id)|project(?:_name|_id|-name|-id|Name|Id)|namespace"
    pattern = re.compile(
        rf"(?im)^\s*(?:\?\s*)?['\"]?(?P<key>{key})['\"]?\s*\n\s*:\s*(?P<value>[^\r\n]+)"
    )
    for match in pattern.finditer(text):
        value = normalized_value(match.group("value").strip().strip("'\""))
        if (
            not value
            or value.startswith(("|", ">", "{", "["))
            or placeholder_value(value)
        ):
            continue
        add_finding(
            findings,
            path=path,
            line=text.count("\n", 0, match.start("value")) + 1,
            category="customer-identifier",
            message=f"{match.group('key')} contains a literal organization identifier",
        )

# fmt: on
def scan_query_parameters(
    path: str,
    line_number: int,
    line: str,
    findings: set[Finding],
) -> None:
    """Scan URL query parameters for embedded identity values."""
    for match in QUERY_RE.finditer(line):
        value = urllib.parse.unquote_plus(match.group("value"))
        if placeholder_value(value):
            continue
        if match.group("key").lower() == "email" and safe_email(value):
            continue
        add_finding(
            findings,
            path=path,
            line=line_number,
            category="pii-query-parameter",
            message=f"URL query parameter {match.group('key')} contains a literal value",
        )


def scan_public_ips(
    path: str,
    line_number: int,
    line: str,
    findings: set[Finding],
) -> None:
    """Report globally routable unicast IPv4 values outside documentation ranges."""
    for match in IPV4_RE.finditer(line):
        try:
            address = ipaddress.ip_address(match.group(0))
        except ValueError:
            continue
        if not address.is_global or address.is_multicast:
            continue
        if any(address in network for network in DOCUMENTATION_NETWORKS):
            continue
        prefix = line[max(0, match.start() - 96) : match.start()]
        if DOTTED_VERSION_PREFIX_RE.search(prefix):
            continue
        for attribute in SVG_PATH_ATTRIBUTE_RE.finditer(line, 0, match.start()):
            value = line[attribute.end() : match.start()]
            if attribute.group("quote") not in value:
                break
        else:
            attribute = None
        if attribute is not None:
            continue
        add_review_finding(
            findings,
            path=path,
            line=line_number,
            category="public-ip-review",
            message="globally routable unicast IPv4 address is outside documentation ranges",
        )


def parse_fence_language(info: str) -> str:
    """Extract a language from CommonMark, Pandoc, or RMarkdown fence info."""
    info = info.strip()
    if not info:
        return ""
    if info.startswith("{") and info.endswith("}"):
        attributes = info[1:-1].strip()
        candidates = FENCE_CLASS_RE.findall(attributes)
        if not candidates:
            items = re.split(r"[\s,]+", attributes)
            candidates = []
            for item in items:
                if not item.startswith("#"):
                    candidates.append(item.rstrip(","))
        for candidate in candidates:
            if candidate.lower() in SOURCE_FENCE_LANGUAGES | {"jq"}:
                return candidate.lower()
        return candidates[0].lower() if candidates else ""
    return info.split(maxsplit=1)[0].lower()


def yaml_syntax(line: str) -> str:
    """Mask quoted values and comments before inspecting YAML control syntax."""
    syntax: list[str] = []
    quote: str | None = None
    escaped = False
    for character in line:
        if quote:
            syntax.append(" ")
            if character == quote and not escaped:
                quote = None
            escaped = character == "\\" and not escaped
            if character != "\\":
                escaped = False
            continue
        if character in {"'", '"'}:
            quote = character
            syntax.append(" ")
        elif character == "#" and (not syntax or syntax[-1].isspace()):
            break
        else:
            syntax.append(character)
    return "".join(syntax)


def yaml_value_text(line: str) -> str:
    """Remove a YAML comment while preserving quoted scalar content."""
    value: list[str] = []
    quote: str | None = None
    escaped = False
    for character in line:
        if character == "#" and quote is None and (not value or value[-1].isspace()):
            break
        value.append(character)
        if quote:
            if character == quote and not escaped:
                quote = None
            escaped = character == "\\" and not escaped
            if character != "\\":
                escaped = False
        elif character in {"'", '"'}:
            quote = character
    return "".join(value)


def yaml_anchor_value(line: str, start: int) -> str:
    """Extract the scalar node immediately following a YAML anchor."""
    tail = yaml_value_text(line[start:]).lstrip()
    while tag := YAML_TAG_RE.match(tail):
        tail = tail[tag.end() :]
    if not tail:
        return ""
    quote = tail[0] if tail[0] in {"'", '"'} else None
    if quote:
        index = 1
        while index < len(tail):
            if quote == "'" and tail[index : index + 2] == "''":
                index += 2
                continue
            if tail[index] == quote:
                backslashes = 0
                before = index - 1
                while before >= 0 and tail[before] == "\\":
                    backslashes += 1
                    before -= 1
                if quote == "'" or backslashes % 2 == 0:
                    return normalized_value(tail[: index + 1])
            index += 1
        return normalized_value(tail)
    flow_context = serialization_nesting(line[:start]) > 0
    delimiter = re.search(r"[],}]", tail) if flow_context else None
    return normalized_value(tail[: delimiter.start()] if delimiter else tail)


def update_yaml_aliases(
    line: str,
    aliases: dict[str, bool],
) -> tuple[tuple[int, str, bool], ...]:
    """Apply scalar anchor declarations in source order within one YAML document."""
    events: list[tuple[int, str, bool]] = []
    syntax = yaml_syntax(line)
    for anchor in YAML_ANCHOR_VALUE_RE.finditer(syntax):
        value = yaml_anchor_value(line, anchor.end("name"))
        referenced = re.fullmatch(r"\*([A-Za-z0-9_.-]+)", value)
        if referenced:
            safe = aliases.get(referenced.group(1), False)
        else:
            block_value = bool(re.fullmatch(r"[|>](?:[+-]?[1-9]?|[1-9][+-])", value))
            safe = bool(value) and not block_value and placeholder_value(value)
        name = anchor.group("name")
        aliases[name] = safe
        events.append((anchor.start(), name, safe))
    return tuple(events)


def safe_yaml_block_content(value: str) -> bool:
    """Return whether a YAML block line is explicitly synthetic identity content."""
    value = normalized_value(value)
    safe_block_prose = bool(SAFE_BLOCK_PROSE_RE.fullmatch(value))
    safe_label_prose = bool(PROSE_SAFE_LANGUAGE_RE.fullmatch(value))
    safe_prose = safe_block_prose or safe_label_prose
    return not value or safe_prose or placeholder_value(value)


def scan_yaml_identity_blocks(path: str, text: str, findings: set[Finding]) -> None:
    """Inspect scalar bodies owned by YAML identity fields."""
    active_block_indent: int | None = None
    block_key = ""
    for line_number, raw_line in enumerate(text.splitlines(), 1):
        line = ANSI_ESCAPE_RE.sub("", raw_line)
        stripped = line.strip()
        indentation = len(line) - len(line.lstrip())
        if active_block_indent is not None and stripped:
            if indentation > active_block_indent:
                value = normalized_value(stripped)
                if not safe_yaml_block_content(value):
                    add_finding(
                        findings,
                        path=path,
                        line=line_number,
                        category="customer-identifier",
                        message=f"{block_key} contains a literal organization identifier",
                    )
                continue
            active_block_indent = None
        for match in IDENTITY_FIELD_RE.finditer(line):
            value = normalized_value(match.group("value"))
            if re.fullmatch(r"[|>](?:[+-]?[1-9]?|[1-9][+-])", value):
                active_block_indent = indentation
                block_key = match.group("key")
                break


# pylint: disable-next=too-many-locals,too-many-branches,too-many-statements
def scan_text(path: str, text: str, findings: set[Finding]) -> None:
    """Apply structured and line-oriented detectors to one text blob."""
    text = ANSI_ESCAPE_RE.sub("", text)
    text = ZERO_WIDTH_CONTROL_RE.sub("", text)
    visible = (char for char in text if not invisible_format_character(char))
    text = "".join(visible)
    legal_path = is_legal_attribution_path(path)
    suffix = PurePosixPath(path).suffix.lower()
    yaml = suffix in {".yaml", ".yml"}
    aliases: dict[str, bool] = {}
    localization_strings = localization_top_level_string_spans(path, text)
    if yaml or suffix in PROSE_DOCUMENT_SUFFIXES:
        scan_yaml_identity_blocks(path, text, findings)
    scan_multiline_identity_fields(path, text, findings)
    fence_marker: str | None = None
    fence_language: str | None = None
    fence_close_column: int | None = None
    fence_container: str | None = None
    active_jq_quote: str | None = None
    yaml_block_indent: int | None = None
    yaml_block_anchor: str | None = None
    yaml_block_safe = False
    yaml_block_has_content = False
    source_block_comment = False
    source_quote: str | None = None
    source_brace_depth = 0
    enum_body_depth: int | None = None
    pending_enum_body = False
    for line_number, raw_line in enumerate(text.splitlines(), 1):
        line = ANSI_ESCAPE_RE.sub("", raw_line)
        line_aliases = aliases.copy()
        yaml_alias_events: tuple[tuple[int, str, bool], ...] = ()
        if yaml:
            syntax_line = yaml_syntax(line)
            syntax = syntax_line.strip()
            indentation = len(line) - len(line.lstrip())
            inside_block = False
            if yaml_block_indent is not None:
                if not line.strip() or indentation > yaml_block_indent:
                    inside_block = True
                    if line.strip() and yaml_block_anchor:
                        yaml_block_has_content = True
                        yaml_block_safe &= safe_yaml_block_content(line.strip())
                else:
                    if yaml_block_anchor:
                        resolved_safe = yaml_block_has_content and yaml_block_safe
                        aliases[yaml_block_anchor] = resolved_safe
                    yaml_block_indent = None
                    yaml_block_anchor = None
            if not inside_block:
                if syntax in {"---", "..."}:
                    aliases.clear()
                    line_aliases = aliases.copy()
                else:
                    line_aliases = aliases.copy()
                    yaml_alias_events = update_yaml_aliases(line, aliases)
                    block = YAML_BLOCK_START_RE.search(syntax_line)
                    if block:
                        yaml_block_indent = indentation
                        yaml_block_anchor = block.group("anchor")
                        yaml_block_safe = True
                        yaml_block_has_content = False
        fence = FENCE_RE.match(line)
        fence_indent = 0
        if fence:
            fence_indent = len(fence.group("leading")) + len(fence.group("indent"))
        top_level_fence = fence and not fence.group("container")
        if top_level_fence and fence_indent > MAX_COMMONMARK_INDENT:
            fence = None
        if fence and fence.group("indent"):
            container = fence.group("container").rstrip()
            if container and container[-1] in "-+*.)":
                fence = None
        invalid_backtick_info = False
        if fence:
            backtick_marker = fence.group("marker").startswith("`")
            invalid_backtick_info = backtick_marker and "`" in fence.group("info")
        if invalid_backtick_info:
            fence = None
        if fence_marker and fence_container and line.strip():
            blockquote = fence_container.startswith(">")
            indentation = len(line) - len(line.lstrip(" "))
            in_container = indentation >= LIST_FENCE_CONTENT_INDENT
            if blockquote:
                in_container = line.lstrip().startswith(">")
            if not in_container:
                fence_marker = fence_language = fence_container = None
                fence_close_column = None
                active_jq_quote = None
        close = FENCE_CLOSE_RE.match(line) if fence_marker else None
        closing_fence = bool(
            close
            and fence_marker
            and fence_close_column is not None
            and "\t" not in line[: close.start("marker")]
            and close.start("marker") <= fence_close_column
            and fence_marker.startswith(close.group("marker")[0])
            and len(close.group("marker")) >= len(fence_marker)
        )
        opening_fence = bool(fence and fence_marker is None)
        if opening_fence and fence:
            fence_marker = fence.group("marker")
            fence_language = parse_fence_language(fence.group("info"))
            fence_container = fence.group("container")
            container_close_column = fence.start("marker") + 3
            fence_close_column = container_close_column if fence_container else 3
            active_jq_quote = None

        fence_boundary = closing_fence or opening_fence
        effective_language = None if fence_boundary else fence_language
        suffix_is_source = suffix in SOURCE_CODE_SUFFIXES
        fence_is_source = effective_language in SOURCE_FENCE_LANGUAGES
        source_code = suffix_is_source or fence_is_source
        line_source_brace_depth = source_brace_depth
        source_structure = ""
        if source_code:
            source_state = source_structure_line(
                line,
                source_block_comment,
                source_quote,
            )
            source_structure, source_block_comment, source_quote = source_state
            if enum_body_depth is None:
                enum_brace: int | None = None
                if pending_enum_body:
                    if source_structure.strip():
                        opening = re.match(r"\s*(?P<brace>\{)", source_structure)
                        pending_enum_body = False
                        if opening:
                            enum_brace = opening.start("brace")
                else:
                    header = ENUM_HEADER_RE.search(source_structure)
                    if header:
                        tail = source_structure[header.end() :]
                        opening_offset = tail.find("{")
                        semicolon_offset = tail.find(";")
                        brace_precedes_terminator = opening_offset >= 0 and (
                            semicolon_offset < 0 or opening_offset < semicolon_offset
                        )
                        if brace_precedes_terminator:
                            enum_brace = header.end() + opening_offset
                        elif not any(character in tail for character in ";={}"):
                            pending_enum_body = True
                if enum_brace is not None:
                    before_brace = source_structure[:enum_brace]
                    brace_delta = before_brace.count("{") - before_brace.count("}")
                    enum_body_depth = source_brace_depth + brace_delta + 1
        else:
            source_block_comment = False
            source_quote = None
            source_brace_depth = 0
            line_source_brace_depth = 0
            enum_body_depth = None
            pending_enum_body = False
        spans: tuple[tuple[int, int], ...]
        if suffix == ".jq" or effective_language == "jq":
            spans = ((0, len(line)),)
            active_jq_quote = None
        elif source_code:
            spans = ()
            active_jq_quote = None
        else:
            spans, active_jq_quote = jq_filter_spans(line, active_jq_quote)

        context = LineScanContext(
            source_code=source_code,
            jq_spans=spans,
            localization_spans=localization_strings.get(line_number, ()),
            source_structure=source_structure,
            source_brace_depth=line_source_brace_depth,
            enum_body_depth=enum_body_depth,
            yaml_aliases=line_aliases,
            yaml_alias_events=yaml_alias_events,
        )

        is_commit_message = path.startswith("<commit:")
        trailer_match = PROVENANCE_TRAILER_RE.match(line)
        provenance_trailer = bool(is_commit_message and trailer_match)
        scan_contacts(
            path,
            line_number,
            line,
            legal_path or provenance_trailer,
            findings,
            context,
        )
        scan_structured_identity(
            path,
            line_number,
            line,
            findings,
            context,
        )
        scan_jq_identity_writes(path, line_number, line, findings, context)
        scan_query_parameters(path, line_number, line, findings)
        scan_public_ips(path, line_number, line, findings)

        if source_code:
            source_brace_depth += source_structure.count("{")
            source_brace_depth -= source_structure.count("}")
            source_brace_depth = max(source_brace_depth, 0)
            if enum_body_depth is not None and source_brace_depth < enum_body_depth:
                enum_body_depth = None

        if closing_fence:
            fence_marker = None
            fence_language = None
            fence_close_column = None
            fence_container = None
            active_jq_quote = None


def looks_binary(data: bytes) -> bool:
    """Use NUL bytes as a conservative binary-content signal."""
    return b"\0" in data[:8192]


def scan_binary(path: str, data: bytes, findings: set[Finding], *, media: bool) -> None:
    """Inspect ASCII-compatible binary metadata without rendering the file."""
    # Keep only printable metadata runs. Treating every byte as Latin-1 lets
    # compression noise masquerade as contact syntax across arbitrary bytes.
    printable_data = data if media else data.replace(b"\0", b"")
    matches = PRINTABLE_ASCII_RE.finditer(printable_data)
    text = "\n".join(match.group(0).decode("ascii") for match in matches)
    if not media:
        scan_text(path, text, findings)
        return

    for metadata in MEDIA_AUTHOR_METADATA_RE.finditer(text):
        value = metadata.group("value")
        emails = list(EMAIL_RE.finditer(value))
        for email in emails:
            if not safe_email(email.group(0)):
                add_finding(
                    findings,
                    path=path,
                    line=0,
                    category="email",
                    message="media metadata contains a non-reserved email address",
                )
        if not emails and not placeholder_value(value):
            add_finding(
                findings,
                path=path,
                line=0,
                category="media-author",
                message="binary media contains literal author metadata",
            )
    if SENSITIVE_MEDIA_TAG_RE.search(text):
        add_finding(
            findings,
            path=path,
            line=0,
            category="location-metadata",
            message="binary media contains a location or owner metadata tag",
        )
    for match in PDF_AUTHOR_RE.finditer(text):
        if not placeholder_value(match.group("value")):
            add_finding(
                findings,
                path=path,
                line=0,
                category="media-author",
                message="binary media contains literal author metadata",
            )


def scan_blob(path: str, data: bytes, findings: set[Finding]) -> None:
    """Classify and scan one materialized tracked blob."""
    if is_excluded(path):
        return
    suffix = PurePosixPath(path).suffix.lower()
    if suffix in MEDIA_SUFFIXES:
        add_review_finding(
            findings,
            path=path,
            line=0,
            category="media-review",
            message="media requires metadata, OCR, and visual review",
        )
    if suffix in MEDIA_SUFFIXES - TEXT_MEDIA_SUFFIXES:
        scan_binary(path, data, findings, media=True)
        return
    if looks_binary(data):
        scan_binary(path, data, findings, media=False)
        return
    decoded = data.decode("utf-8", "surrogateescape")
    text: list[str] = []
    for character in decoded:
        codepoint = ord(character)
        if SURROGATE_ESCAPE_FIRST <= codepoint <= SURROGATE_ESCAPE_C1_LAST:
            text.append(chr(codepoint - SURROGATE_ESCAPE_BASE))
        elif not SURROGATE_ESCAPE_FIRST <= codepoint <= SURROGATE_ESCAPE_LAST:
            text.append(character)
    scan_text(path, "".join(text), findings)


def scan(input_dir: Path) -> set[Finding]:
    """Scan every blob materialized by the trusted shell wrapper."""
    findings: set[Finding] = set()
    for path, data in input_blobs(input_dir):
        scan_blob(path, data, findings)
    return findings


def selected_findings(findings: Iterable[Finding], mode: str) -> list[Finding]:
    """Filter advisory results from enforcement mode and sort the remainder."""

    def should_include(finding: Finding) -> bool:
        return mode == "audit" or finding.severity == "high"

    return sorted(filter(should_include, findings))


def render_text(findings: Sequence[Finding], *, scope: str, mode: str) -> str:
    """Render redacted findings as GitHub-compatible annotations."""
    if not findings:
        return f"PII {mode}: clean ({scope} scope)."
    lines = []
    for finding in findings:
        location = finding.path
        if finding.line:
            location = f"{location}:{finding.line}"
        annotation = f"[{finding.category}] {finding.message} ({location})"
        lines.append(f"::error file={finding.path},line={finding.line}::{annotation}")
    lines.append(f"PII {mode}: {len(findings)} finding(s) in {scope} scope.")
    return "\n".join(lines)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse arguments supplied by the shell wrapper."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument(
        "--scope",
        choices=("changed", "staged", "head", "history"),
        default="changed",
    )
    parser.add_argument("--mode", choices=("audit", "enforce"), default="audit")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the content scan and map its result to the documented exit codes."""
    args = parse_args(argv if argv is not None else sys.argv[1:])
    if not args.input_dir.is_dir():
        print(
            f"PII scan error: materialized input directory is missing: {args.input_dir}",
            file=sys.stderr,
        )
        return 2
    try:
        findings = selected_findings(scan(args.input_dir), args.mode)
    except OSError as error:
        print(f"PII scan error: {error}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(
            json.dumps(
                {
                    "scope": args.scope,
                    "mode": args.mode,
                    "findings": [asdict(finding) for finding in findings],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(render_text(findings, scope=args.scope, mode=args.mode))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
