from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode


EXCLUDED_EXTENSIONS = {
    ".mp4",
    ".pdf",
    ".ppt",
    ".pptx",
}

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
)
DOWNLOAD_CHUNK_SIZE = 64 * 1024 * 1024
DOWNLOAD_RETRIES = 5

HEADING_LEVELS = {
    "heading1": 0,
    "heading2": 1,
    "heading3": 2,
    "heading4": 3,
    "heading5": 4,
    "heading6": 5,
}


@dataclass(frozen=True)
class CourseFile:
    name: str
    token: str
    size: int | None
    mime_type: str
    headings: tuple[str, ...]
    relative_path: str


@dataclass(frozen=True)
class CourseSourceConfig:
    tenant_origin: str
    doc_id: str
    wiki_space_id: str
    wiki_token: str

    @property
    def client_vars_endpoint(self) -> str:
        return f"{self.tenant_origin}/space/api/docx/pages/client_vars"

    @property
    def referer(self) -> str:
        return f"{self.tenant_origin}/wiki/{self.wiki_token}"


def sanitize_path_segment(value: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]', "-", value.strip())
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or "untitled"


def text_from_block(block: dict[str, Any]) -> str:
    text = (
        block.get("data", {})
        .get("text", {})
        .get("initialAttributedTexts", {})
        .get("text", {})
    )
    if isinstance(text, dict):
        return "".join(str(text[key]) for key in sorted(text, key=_sort_text_key)).strip()
    if isinstance(text, str):
        return text.strip()
    return ""


def collect_files(payloads: list[dict[str, Any]]) -> list[CourseFile]:
    files: list[CourseFile] = []
    headings: list[str | None] = [None] * 6

    for payload in payloads:
        data = payload.get("data", {})
        block_map = data.get("block_map", {})
        for block_id in data.get("block_sequence", []):
            block = block_map.get(block_id, {})
            block_data = block.get("data", {})
            block_type = block_data.get("type")

            if block_type in HEADING_LEVELS:
                heading = sanitize_path_segment(text_from_block(block))
                if heading:
                    level = semantic_heading_level(
                        heading,
                        HEADING_LEVELS[block_type],
                        str(block_type),
                    )
                    headings[level] = heading
                    for index in range(level + 1, len(headings)):
                        headings[index] = None
                continue

            if block_type != "file":
                continue

            file_data = block_data.get("file", {})
            name = str(file_data.get("name") or "").strip()
            token = str(file_data.get("token") or "").strip()
            if not name or not token:
                continue

            if Path(name).suffix.lower() in EXCLUDED_EXTENSIONS:
                continue

            path_headings = tuple(heading for heading in headings if heading)
            relative_path = "/".join(
                [*path_headings, sanitize_path_segment(name)]
                if path_headings
                else [sanitize_path_segment(name)]
            )
            files.append(
                CourseFile(
                    name=name,
                    token=token,
                    size=_int_or_none(file_data.get("size")),
                    mime_type=str(file_data.get("mimeType") or ""),
                    headings=path_headings,
                    relative_path=relative_path,
                )
            )

    return _dedupe_files(files)


def load_json_files(paths: list[Path]) -> list[dict[str, Any]]:
    payloads = []
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            payloads.append(json.load(handle))
    return payloads


def semantic_heading_level(heading: str, fallback_level: int, block_type: str = "") -> int:
    if block_type == "heading1" and re.match(r"^第[一二三四五六七八九十0-9]+部分", heading):
        return 0
    if re.match(r"^第[一二三四五六七八九十0-9]+章", heading):
        return 1
    if re.match(r"^\d+\.\d+\.\d+(?:\D|$)", heading):
        return 3
    if re.match(r"^\d+\.\d+(?:\D|$)", heading):
        return 2
    if block_type == "heading2":
        return 2
    return fallback_level


def save_manifest(files: list[CourseFile], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    data = [
        {
            "name": item.name,
            "token": item.token,
            "size": item.size,
            "mime_type": item.mime_type,
            "headings": list(item.headings),
            "relative_path": item.relative_path,
        }
        for item in files
    ]
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_manifest(path: Path) -> list[CourseFile]:
    with path.open("r", encoding="utf-8") as handle:
        return files_from_manifest_data(json.load(handle))


def files_from_manifest_data(data: list[dict[str, Any]]) -> list[CourseFile]:
    return [
        CourseFile(
            name=str(item["name"]),
            token=str(item["token"]),
            size=_int_or_none(item.get("size")),
            mime_type=str(item.get("mime_type") or ""),
            headings=tuple(str(part) for part in item.get("headings", [])),
            relative_path=str(item["relative_path"]),
        )
        for item in data
    ]


def build_download_url(token: str, tenant_origin: str) -> str:
    return f"{tenant_origin.rstrip('/')}/space/api/box/stream/download/all/{token}"


def build_cookie_header(storage_state: dict[str, Any]) -> str:
    cookies = []
    for cookie in storage_state.get("cookies", []):
        if "feishu.cn" not in str(cookie.get("domain", "")):
            continue
        name = cookie.get("name")
        value = cookie.get("value")
        if name is None or value is None:
            continue
        cookies.append(f"{name}={value}")
    return "; ".join(cookies)


def load_storage_state(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def fetch_all_client_vars(
    config: CourseSourceConfig,
    cookie_header: str,
    limit: int = 300,
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    queue: list[str | None] = [None]
    seen_urls: set[str] = set()

    while queue:
        cursor = queue.pop(0)
        url = _build_client_vars_url(config, cursor, limit=limit)
        if url in seen_urls:
            continue
        seen_urls.add(url)

        payload = _json_request(config, url, cookie_header)
        payloads.append(payload)

        data = payload.get("data", {})
        next_cursors = [str(item) for item in data.get("next_cursors") or [] if item]
        for next_cursor in next_cursors:
            if next_cursor:
                queue.append(next_cursor)
        if not next_cursors and data.get("has_more") and data.get("cursor"):
            queue.append(str(data["cursor"]))

    return payloads


def download_files(
    files: list[CourseFile],
    root: Path,
    cookie_header: str,
    tenant_origin: str,
) -> list[Path]:
    downloaded: list[Path] = []
    for item in files:
        target = root / Path(item.relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if item.size is not None and target.exists() and target.stat().st_size == item.size:
            print(f"skip existing: {item.relative_path}")
            downloaded.append(target)
            continue

        tmp = target.with_name(target.name + ".part")
        resume_from = tmp.stat().st_size if tmp.exists() else 0
        print(f"download: {item.relative_path}")
        if item.size is None:
            _download_stream(item, tmp, cookie_header, resume_from, tenant_origin)
        else:
            _download_ranges(item, tmp, cookie_header, resume_from, tenant_origin)

        if item.size is not None and tmp.stat().st_size != item.size:
            raise RuntimeError(
                f"size mismatch for {item.relative_path}: "
                f"expected {item.size}, got {tmp.stat().st_size}"
            )
        tmp.replace(target)
        downloaded.append(target)
    return downloaded


def iter_ranges(size: int, start: int = 0, chunk_size: int = DOWNLOAD_CHUNK_SIZE) -> list[tuple[int, int]]:
    ranges = []
    position = start
    while position < size:
        end = min(position + chunk_size - 1, size - 1)
        ranges.append((position, end))
        position = end + 1
    return ranges


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download non-video/PDF/PPT Feishu course attachments by document hierarchy."
    )
    parser.add_argument(
        "json",
        nargs="*",
        type=Path,
        help="Optional client_vars response JSON files. If omitted, --state is used to fetch all pages.",
    )
    parser.add_argument("--state", type=Path, default=Path(".playwright-cli/feishu-state.json"))
    parser.add_argument("--manifest", type=Path, default=Path(".playwright-cli/feishu-course-manifest.json"))
    parser.add_argument("--output", type=Path, default=Path("."))
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--from-manifest", action="store_true")
    parser.add_argument("--save-pages", type=Path, default=Path(".playwright-cli/client-vars-full.json"))
    parser.add_argument("--tenant-origin", default=os.getenv("FEISHU_TENANT_ORIGIN"))
    parser.add_argument("--doc-id", default=os.getenv("FEISHU_DOC_ID"))
    parser.add_argument("--wiki-space-id", default=os.getenv("FEISHU_WIKI_SPACE_ID"))
    parser.add_argument("--wiki-token", default=os.getenv("FEISHU_WIKI_TOKEN"))
    args = parser.parse_args(argv)

    config = _build_config(args)

    if args.from_manifest:
        files = load_manifest(args.manifest)
        cookie_header = ""
    elif args.json:
        payloads = load_json_files(args.json)
        cookie_header = ""
        files = collect_files(payloads)
        save_manifest(files, args.manifest)
    else:
        _require_fetch_config(config)
        state = load_storage_state(args.state)
        cookie_header = build_cookie_header(state)
        payloads = fetch_all_client_vars(config, cookie_header)
        args.save_pages.parent.mkdir(parents=True, exist_ok=True)
        args.save_pages.write_text(
            json.dumps(payloads, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        files = collect_files(payloads)
        save_manifest(files, args.manifest)
    for item in files:
        print(item.relative_path)
    print(f"total: {len(files)}", file=sys.stderr)

    if args.download:
        _require_tenant_origin(config.tenant_origin)
        if not cookie_header:
            state = load_storage_state(args.state)
            cookie_header = build_cookie_header(state)
        download_files(files, args.output, cookie_header, config.tenant_origin)

    return 0


def _dedupe_files(files: list[CourseFile]) -> list[CourseFile]:
    seen: set[str] = set()
    deduped: list[CourseFile] = []
    for item in files:
        if item.token in seen:
            continue
        seen.add(item.token)
        deduped.append(item)
    return deduped


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sort_text_key(key: Any) -> tuple[int, str]:
    text = str(key)
    return (int(text), text) if text.isdigit() else (10**9, text)


def _download_ranges(
    item: CourseFile,
    tmp: Path,
    cookie_header: str,
    resume_from: int,
    tenant_origin: str,
) -> None:
    if item.size is None:
        raise ValueError("range download requires known file size")

    if resume_from > item.size:
        tmp.unlink(missing_ok=True)
        resume_from = 0

    mode = "ab" if resume_from else "wb"
    with tmp.open(mode) as handle:
        for start, end in iter_ranges(item.size, resume_from):
            headers = _base_headers(cookie_header)
            headers["Range"] = f"bytes={start}-{end}"
            request = urllib.request.Request(
                build_download_url(item.token, tenant_origin),
                headers=headers,
            )
            expected = end - start + 1
            data = _read_request_with_retries(request, expected, item.relative_path)
            handle.write(data)
            handle.flush()


def _download_stream(
    item: CourseFile,
    tmp: Path,
    cookie_header: str,
    resume_from: int,
    tenant_origin: str,
) -> None:
    headers = _base_headers(cookie_header)
    if resume_from:
        headers["Range"] = f"bytes={resume_from}-"
    request = urllib.request.Request(build_download_url(item.token, tenant_origin), headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            if resume_from and response.status != 206:
                tmp.unlink(missing_ok=True)
                resume_from = 0
            mode = "ab" if resume_from else "wb"
            with tmp.open(mode) as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"failed to download {item.relative_path}: {exc}") from exc


def _read_request_with_retries(
    request: urllib.request.Request,
    expected_size: int,
    relative_path: str,
) -> bytes:
    last_error: Exception | None = None
    for attempt in range(1, DOWNLOAD_RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = response.read()
                if response.status not in (200, 206):
                    raise RuntimeError(f"unexpected HTTP status {response.status}")
                if len(data) != expected_size:
                    raise RuntimeError(
                        f"incomplete range: expected {expected_size}, got {len(data)}"
                    )
                return data
        except (HTTPError, URLError, TimeoutError, RuntimeError) as exc:
            last_error = exc
            if attempt == DOWNLOAD_RETRIES:
                break
            time.sleep(min(2**attempt, 10))
    raise RuntimeError(f"failed to download {relative_path}: {last_error}") from last_error


def _build_client_vars_url(
    config: CourseSourceConfig,
    cursor: str | None,
    limit: int,
) -> str:
    params = {
        "id": config.doc_id,
        "mode": "7",
        "limit": str(limit),
        "wiki_space_id": config.wiki_space_id,
        "container_type": "wiki2.0",
        "container_id": config.wiki_token,
    }
    if cursor:
        params["cursor"] = cursor
    return config.client_vars_endpoint + "?" + urlencode(params)


def _json_request(config: CourseSourceConfig, url: str, cookie_header: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=_base_headers(cookie_header, config.referer))
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def _base_headers(cookie_header: str, referer: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": DEFAULT_USER_AGENT,
    }
    if referer:
        headers["Referer"] = referer
    if cookie_header:
        headers["Cookie"] = cookie_header
    return headers


def _build_config(args: argparse.Namespace) -> CourseSourceConfig:
    return CourseSourceConfig(
        tenant_origin=(args.tenant_origin or "").rstrip("/"),
        doc_id=args.doc_id or "",
        wiki_space_id=args.wiki_space_id or "",
        wiki_token=args.wiki_token or "",
    )


def _require_tenant_origin(tenant_origin: str) -> None:
    if not tenant_origin:
        raise SystemExit(
            "--tenant-origin or FEISHU_TENANT_ORIGIN is required when fetching or downloading."
        )


def _require_fetch_config(config: CourseSourceConfig) -> None:
    missing = []
    if not config.tenant_origin:
        missing.append("--tenant-origin or FEISHU_TENANT_ORIGIN")
    if not config.doc_id:
        missing.append("--doc-id or FEISHU_DOC_ID")
    if not config.wiki_space_id:
        missing.append("--wiki-space-id or FEISHU_WIKI_SPACE_ID")
    if not config.wiki_token:
        missing.append("--wiki-token or FEISHU_WIKI_TOKEN")
    if missing:
        raise SystemExit("Missing required Feishu source config: " + ", ".join(missing))


if __name__ == "__main__":
    raise SystemExit(main())
