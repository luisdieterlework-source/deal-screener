import pytest

from deal_screener.tools import FetchError, assert_public_host, fetch_page_impl, html_to_text, normalize_url

HTML = """<html><head><title>Acme | Robots</title>
<meta name="description" content="Robots for warehouses."></head>
<body><nav>Home Pricing Login</nav><script>var x = 1;</script>
<main><h1>Pick faster</h1><p>Acme robots pick 600 items per hour.</p></main>
<footer>(c) Acme</footer></body></html>"""


def test_html_to_text_keeps_content_drops_chrome():
    title, text = html_to_text(HTML)
    assert title == "Acme | Robots"
    assert "Acme robots pick 600 items per hour." in text
    assert "Robots for warehouses." in text
    assert "var x" not in text and "Login" not in text and "(c) Acme" not in text


def test_html_to_text_truncates():
    _, text = html_to_text("<p>" + "word " * 5000 + "</p>", max_chars=100)
    assert len(text) < 130 and text.endswith("[... truncated]")


@pytest.mark.parametrize("raw,expected", [("stripe.com", "https://stripe.com"), (" https://a.io/x ", "https://a.io/x")])
def test_normalize_url(raw, expected):
    assert normalize_url(raw) == expected


@pytest.mark.parametrize("raw", ["", "ftp://x.com", "file:///etc/passwd"])
def test_normalize_url_rejects(raw):
    with pytest.raises(FetchError):
        normalize_url(raw)


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "10.0.0.5", "169.254.169.254"])
def test_private_hosts_blocked(host):
    with pytest.raises(FetchError):
        assert_public_host(host)


async def test_fetch_tool_returns_error_instead_of_raising():
    result = await fetch_page_impl({"url": "http://127.0.0.1/admin"})
    assert result["is_error"] is True
    assert result["content"][0]["text"].startswith("ERROR:")
