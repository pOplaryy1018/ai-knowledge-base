import pytest

from app.services.connectors.git_public import canonical_public_url
from app.services.connectors.types import ConnectorError


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/a/b",
        "https://user@github.com/a/b",
        "https://github.com/a/b?x=1",
        "https://localhost/a/b",
        "https://github.com/a/b/../c",
        "https://github.com/a/b.git/extra",
    ],
)
def test_reject_unsafe_url(url):
    with pytest.raises(ConnectorError):
        canonical_public_url(url)


def test_canonical_url():
    assert (
        canonical_public_url("https://github.com/owner/repo.git")
        == "https://github.com/owner/repo.git"
    )


def test_fetch_is_isolated_and_constrained(monkeypatch, tmp_path):
    from types import SimpleNamespace

    import app.services.connectors.git_public as module

    calls = []

    def fake_run(repo, args, **kwargs):
        calls.append((repo, args, kwargs))
        return b""

    monkeypatch.setattr(module, "run_git", fake_run)
    monkeypatch.setattr(
        module, "extract_snapshot", lambda repo, **kw: SimpleNamespace(commit="a", documents=[])
    )
    result = module.collect_public("https://github.com/owner/repo", cache_root=tmp_path)
    assert result.commit == "a"
    fetch = calls[1][1]
    assert "--no-recurse-submodules" in fetch
    assert "protocol.allow=never" in fetch
    assert "protocol.https.allow=always" in fetch
    assert fetch[-2] == "https://github.com/owner/repo.git"
    assert not calls[0][0].exists()


@pytest.mark.parametrize("storage_budget", [None, 1024 * 1024])
def test_git_does_not_inherit_netrc_credentials(monkeypatch, tmp_path, storage_budget):
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from threading import Thread

    from app.services.connectors.git_snapshot import run_git

    home = tmp_path / "original-home"
    home.mkdir()
    for name in (".netrc", "_netrc"):
        (home / name).write_text("machine 127.0.0.1 login synthetic password synthetic")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.headers.get("Authorization"))
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="git"')
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(ConnectorError):
            run_git(
                tmp_path,
                [
                    "-c",
                    "http.proxy=",
                    "ls-remote",
                    f"http://127.0.0.1:{server.server_port}/repo.git",
                ],
                storage_budget=storage_budget,
            )
        assert seen
        assert all(header is None for header in seen)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
