"""Custom `fetch_page` tool: download a URL and return readable text for the agent.

Web search uses the SDK's built-in WebSearch tool. Page reading is our own tool so that we
control timeouts, size caps and the exact text the model sees (it can quote and cite it).
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

MAX_DOWNLOAD_BYTES = 2_000_000
MAX_TEXT_CHARS = 12_000
TIMEOUT_SECONDS = 15
USER_AGENT = "Mozilla/5.0 (compatible; DealScreener/0.1; research bot)"
_DROP_TAGS = ("script", "style", "noscript", "svg", "iframe", "form", "nav", "footer", "header", "aside")


class FetchError(RuntimeError):
    """Raised when a page cannot be fetched or is not allowed."""


def normalize_url(url: str) -> str:
    """Add https:// if missing and reject non-http(s) schemes."""
    url = url.strip()
    if not url:
        raise FetchError("empty URL")
    if "://" not in url:
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise FetchError(f"unsupported URL: {url!r}")
    return url


def assert_public_host(hostname: str) -> None:
    """Block localhost and private networks (SSRF guard for the hosted web UI)."""
    if hostname.lower() in ("localhost",) or hostname.endswith(".local"):
        raise FetchError(f"refusing to fetch private host {hostname!r}")
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise FetchError(f"cannot resolve {hostname!r}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise FetchError(f"refusing to fetch private address {ip} ({hostname})")


def html_to_text(html: str, max_chars: int = MAX_TEXT_CHARS) -> tuple[str, str]:
    """Extract (title, readable text) from HTML, dropping navigation and scripts."""
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.get_text(strip=True) if soup.title else "") or ""
    meta = soup.find("meta", attrs={"name": "description"})
    description = meta.get("content", "").strip() if meta else ""
    for tag in soup(_DROP_TAGS):
        tag.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    lines = [ln.strip() for ln in root.get_text("\n").splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    if description and description not in text:
        text = f"{description}\n{text}"
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] + "\n[... truncated]"
    return title, text


def fetch_url(url: str, timeout: float = TIMEOUT_SECONDS) -> tuple[str, str, str]:
    """Blocking fetch. Returns (final_url, title, text)."""
    url = normalize_url(url)
    assert_public_host(urlparse(url).hostname or "")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.5"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (scheme checked above)
            ctype = resp.headers.get("Content-Type", "")
            raw = resp.read(MAX_DOWNLOAD_BYTES)
            final_url = resp.geturl()
    except urllib.error.HTTPError as exc:
        raise FetchError(f"HTTP {exc.code} for {url}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise FetchError(f"could not fetch {url}: {exc}") from exc
    if "html" not in ctype and "text" not in ctype:
        raise FetchError(f"unsupported content type {ctype!r} for {url}")
    charset = "utf-8"
    if "charset=" in ctype:
        charset = ctype.split("charset=")[-1].split(";")[0].strip() or "utf-8"
    html = raw.decode(charset, errors="replace")
    if "html" not in ctype:
        return final_url, "", html[:MAX_TEXT_CHARS]
    title, text = html_to_text(html)
    return final_url, title, text


def format_tool_result(final_url: str, title: str, text: str) -> str:
    return f"URL: {final_url}\nTITLE: {title or '(no title)'}\n\n{text or '(no readable text)'}"


async def fetch_page_impl(args: dict[str, Any]) -> dict[str, Any]:
    """MCP tool handler: returns page text, or an error the model can react to."""
    try:
        final_url, title, text = await asyncio.to_thread(fetch_url, str(args.get("url", "")))
    except FetchError as exc:
        return {"content": [{"type": "text", "text": f"ERROR: {exc}"}], "is_error": True}
    return {"content": [{"type": "text", "text": format_tool_result(final_url, title, text)}]}


def build_research_server() -> Any:
    """Create the in-process MCP server exposing `fetch_page`."""
    from claude_agent_sdk import create_sdk_mcp_server, tool

    fetch_page = tool(
        "fetch_page",
        "Fetch a web page and return its title and readable text (max ~12k chars). "
        "Use it to read the company website, news articles, funding announcements and competitor pages.",
        {"url": str},
    )(fetch_page_impl)
    return create_sdk_mcp_server(name="research", version="1.0.0", tools=[fetch_page])
