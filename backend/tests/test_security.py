import stat
import zipfile
import pytest
from app.security.repositories import extract_zip, github_clone_environment, validate_github, scan_files


@pytest.mark.parametrize("name", ["../../etc/passwd", "/tmp/file", "C:/file", "a\\b"])
def test_zip_rejects_unsafe_paths(tmp_path, name):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr(name, "malicious")
    with pytest.raises(ValueError, match="unsafe"):
        extract_zip(archive, tmp_path / "out")


def test_zip_rejects_symlinks(tmp_path):
    archive = tmp_path / "bad.zip"
    info = zipfile.ZipInfo("link.py")
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr(info, "../../secret")
    with pytest.raises(ValueError, match="symbolic"):
        extract_zip(archive, tmp_path / "out")


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/a/b",
        "https://evil.com/a/b",
        "https://github.com/a/b;pwd",
        "https://github.com/a/b?x=1",
        "https://github.com/../b",
        "file:///tmp/repo",
    ],
)
def test_github_url_rejects_noncanonical_repo_urls(url):
    with pytest.raises(ValueError):
        validate_github(url)


def test_github_url_accepts_canonical_url():
    assert validate_github("https://github.com/tree-sitter/tree-sitter.git")


def test_private_clone_token_uses_process_environment_not_url():
    env = github_clone_environment("secret-token")
    assert env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
    assert env["GIT_CONFIG_VALUE_0"].startswith("Authorization: Basic ")
    assert "secret-token" not in env["GIT_CONFIG_VALUE_0"]


def test_scan_ignores_symlinks_vendor_minified(tmp_path):
    (tmp_path / "real.py").write_text("def ok(): pass")
    (tmp_path / "linked.py").symlink_to(tmp_path / "real.py")
    (tmp_path / "bundle.min.js").write_text("const x = 1;")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules/x.js").write_text("secret()")
    assert [p.name for p in scan_files(tmp_path)] == ["real.py"]


def test_zip_expansion_limit(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings(), "max_file_bytes", 10)
    archive = tmp_path / "big.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("big.py", "x" * 11)
    with pytest.raises(ValueError, match="size"):
        extract_zip(archive, tmp_path / "out")
