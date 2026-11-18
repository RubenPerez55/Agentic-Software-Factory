from pathlib import Path

from factory_app import tools


def test_list_repo_files_allows_only_readable_roots():
    result = tools.list_repo_files("docs")
    assert result["ok"] is True
    assert "docs/REPO_MAP.md" in result["files"]

    denied = tools.list_repo_files("factory_app")
    assert denied["ok"] is False

    traversal = tools.list_repo_files("../")
    assert traversal["ok"] is False


def test_read_repo_file_enforces_allowlist_and_traversal():
    ok = tools.read_repo_file("docs/REPO_MAP.md")
    assert ok["ok"] is True
    assert "Repository Map" in ok["content"]

    assert tools.read_repo_file("factory_app/agents.py")["ok"] is False
    assert tools.read_repo_file(".env")["ok"] is False
    assert tools.read_repo_file("../../etc/passwd")["ok"] is False
    assert tools.read_repo_file("docs/DOES_NOT_EXIST.md")["ok"] is False


def test_search_repo_finds_symbols_and_respects_bounds():
    result = tools.search_repo("CapacityReachedError", prefix="campusflow")
    assert result["ok"] is True
    assert result["matches"]
    assert all(m["path"].startswith("campusflow/") for m in result["matches"])

    # Unmatched parenthesis should fall back to literal search rather than crashing.
    literal = tools.search_repo("register(", prefix="campusflow/service.py")
    assert literal["ok"] is True

    capped = tools.search_repo("def ", prefix="campusflow", max_results=2)
    assert capped["ok"] is True
    assert len(capped["matches"]) == 2
    assert capped["truncated"] is True


def test_search_repo_rejects_empty_pattern_and_disallowed_paths():
    assert tools.search_repo("")["ok"] is False
    assert tools.search_repo("GEMINI", prefix="factory_app")["ok"] is False
    assert tools.search_repo("root", prefix="../")["ok"] is False


def test_write_run_evidence_scoped_and_validated(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(tools, "REPO_ROOT", tmp_path)

    assert tools.write_run_evidence("INVALID", "01.md", "x")["ok"] is False
    assert tools.write_run_evidence("CR-001", "../escape.md", "x")["ok"] is False
    assert tools.write_run_evidence("CR-001", "script.py", "x")["ok"] is False

    written = tools.write_run_evidence("CR-001", "01-intake-report.md", "# Report")
    assert written == {"ok": True, "path": "runs/CR-001/01-intake-report.md"}
    assert (tmp_path / "runs/CR-001/01-intake-report.md").read_text(encoding="utf-8") == "# Report"
