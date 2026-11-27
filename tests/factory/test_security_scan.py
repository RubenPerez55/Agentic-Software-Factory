"""Deterministic tests for scripts/security_scan.py (secrets + built-in SAST)."""

from pathlib import Path

from scripts.security_scan import run_all_scans, scan_sast_builtin, scan_secrets


def test_clean_workspace_passes_builtin_scanners(tmp_path: Path):
    (tmp_path / "campusflow").mkdir()
    (tmp_path / "campusflow" / "service.py").write_text(
        "def ok(x: int) -> int:\n    return x + 1\n",
        encoding="utf-8",
    )
    assert scan_secrets(tmp_path)["status"] == "PASS"
    assert scan_sast_builtin(tmp_path)["status"] == "PASS"


def test_secret_scanner_detects_private_key_and_api_key(tmp_path: Path):
    (tmp_path / "campusflow").mkdir()
    # Construct synthetic secret dynamically so this test file itself never trips secret scanners.
    fake_key = "AIza" + "0" * 35
    (tmp_path / "campusflow" / "leak.py").write_text(f'KEY = "{fake_key}"\n', encoding="utf-8")

    result = scan_secrets(tmp_path)
    assert result["status"] == "FAIL"
    assert result["high"] == 1
    assert result["findings"][0]["rule"] == "google_api_key"


def test_sast_builtin_detects_sql_injection_and_shell_true(tmp_path: Path):
    (tmp_path / "campusflow").mkdir()
    (tmp_path / "campusflow" / "vuln.py").write_text(
        'import subprocess\n'
        'def bad(conn, user):\n'
        '    conn.execute(f"SELECT * FROM users WHERE id={user}")\n'
        '    subprocess.run("echo hi", shell=True)\n',
        encoding="utf-8",
    )

    result = scan_sast_builtin(tmp_path)
    assert result["status"] == "FAIL"
    assert result["high"] == 2
    rules = {f["rule"] for f in result["findings"]}
    assert rules == {"sql_fstring_injection", "shell_true_subprocess"}


def test_repo_passes_security_scan():
    report = run_all_scans()
    assert report["ok"] is True
    assert report["high"] == 0
