from deal_screener.cli import main, slugify


def test_slugify():
    assert slugify("https://www.Stripe.com/") == "stripe-com"
    assert slugify("Acme Robotics") == "acme-robotics"


def test_render_mode_writes_md_json_pdf(tmp_path):
    from conftest import EXAMPLES

    assert main(["--render", str(EXAMPLES / "stripe.json"), "--out", str(tmp_path)]) == 0
    assert sorted(p.suffix for p in tmp_path.iterdir()) == [".json", ".md", ".pdf"]


def test_missing_key_exits_with_message(monkeypatch, capsys, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)  # make sure no local .env is picked up
    assert main(["https://example.com"]) == 1
    assert "ANTHROPIC_API_KEY is not set" in capsys.readouterr().err
