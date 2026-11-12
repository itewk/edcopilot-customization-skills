"""End-to-end branch workflow through the CLI as real subprocesses.

Ported from the old test_e2e_branch_workflow.py and adapted to the command line:
every step is a separate ``edcg`` process against two temporary git
repositories. Separate processes prove the active branch is derived from git
state, not from memory in a single interpreter.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from edcg import cli
from edcg.repo.gitrepo import GitRepo
from support import init_repo, run_git as _git

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "skills" / "edcopilot-system-content" / "scripts" / "edcg.py"


def _init_repo(root: Path) -> None:
    """A repository with an identity but no commit yet."""
    init_repo(root)


def _environment(tmp_path: Path) -> tuple[Path, Path, dict]:
    content_root = tmp_path / "content"
    runtime_root = tmp_path / "runtime"

    _init_repo(content_root)
    _init_repo(runtime_root)
    (content_root / "systems").mkdir(parents=True, exist_ok=True)
    (content_root / "README.md").write_text("# content\n", encoding="utf-8")
    _git(content_root, "add", "-A")
    _git(content_root, "commit", "-m", "initial")

    (runtime_root / "EDCoPilot.SpeechExtensions.Custom.txt").write_text(
        "", encoding="utf-8"
    )
    _git(runtime_root, "add", "-A")
    _git(runtime_root, "commit", "-m", "initial")

    env = dict(os.environ)
    env.update(
        {
            "EDCG_CONTENT_DEFINITIONS_ROOT": str(content_root),
            "EDCG_EDCOPILOT_ROOT": str(runtime_root),
            "EDCG_AUTO_COMMIT": "true",
        }
    )
    return content_root, runtime_root, env


def _cli(env: dict, cwd: Path, *args: str, stdin: str | None = None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _json(reply) -> dict:
    assert reply.returncode == 0, reply.stderr
    return json.loads(reply.stdout)


def test_full_branch_workflow_across_processes(tmp_path):
    content_root, runtime_root, env = _environment(tmp_path)

    # branch start in one process
    started = _json(_cli(env, content_root, "branch", "start", "test feature"))
    branch_name = started["branch_name"]
    assert branch_name
    assert "content" in started["repos_branched"]
    assert "runtime" in started["repos_branched"]

    # a separate process reads the active branch back from git
    status = _json(_cli(env, content_root, "branch", "status"))
    assert status["active_branch"] == branch_name
    assert status["content_current_branch"] == branch_name
    assert status["runtime_current_branch"] == branch_name

    # save the definition on the feature branch
    dossier = "# Dossier\n"
    rules = '[system]\nnames = ["Test System"]\ndossier = "test-system.md"\n'
    saved = _json(
        _cli(
            env,
            content_root,
            "save-definition",
            stdin=json.dumps(
                {
                    "system_name": "Test System",
                    "dossier_md": dossier,
                    "rules_toml": rules,
                }
            ),
        )
    )
    assert saved["commit_hash"] is not None

    # write content on the feature branch
    written = _json(
        _cli(
            env,
            content_root,
            "write-content",
            stdin=json.dumps(
                {
                    "system_name": "Test System",
                    "content_block": "@SystemGreeting<~>Test System\nHello commander.\n",
                }
            ),
        )
    )
    assert written["commit_hash"] is not None

    # review in a fresh process finds both commits
    review = _cli(env, content_root, "branch", "review")
    assert review.returncode == 0, review.stderr
    assert "Branch Review Summary" in review.stdout
    assert "test" in review.stdout.lower()

    # finalize merges into the default branch of both repositories
    finalized = _json(_cli(env, content_root, "branch", "finalize"))
    assert finalized["merged"] is True
    assert finalized["content_merge_commit"] is not None
    assert finalized["runtime_merge_commit"] is not None

    content_repo = GitRepo(content_root)
    runtime_repo = GitRepo(runtime_root)
    try:
        assert content_repo.current_branch() in ("main", "master")
        assert runtime_repo.current_branch() in ("main", "master")
    finally:
        content_repo.close()
        runtime_repo.close()

    # after finalize the derived state is "no active branch"
    assert _json(_cli(env, content_root, "branch", "status"))["active_branch"] is None

    # the merge left both working trees clean
    assert _git(content_root, "status", "--porcelain").strip() == ""
    assert _git(runtime_root, "status", "--porcelain").strip() == ""


def test_branch_abort_variant_across_processes(tmp_path):
    content_root, runtime_root, env = _environment(tmp_path)

    started = _json(_cli(env, content_root, "branch", "start", "abort feature"))
    branch_name = started["branch_name"]

    # preview in a separate process: nothing is discarded yet
    preview = _json(_cli(env, content_root, "branch", "abort"))
    assert preview["confirmed"] is False
    assert preview["discarded_branch"] == branch_name

    # confirm: the branch disappears from both repositories
    aborted = _json(_cli(env, content_root, "branch", "abort", "--confirm"))
    assert aborted["confirmed"] is True
    assert aborted["content_discarded"] is True
    assert aborted["runtime_discarded"] is True

    for root in (content_root, runtime_root):
        repo = GitRepo(root)
        try:
            assert branch_name not in repo.list_branches()
        finally:
            repo.close()

    assert _json(_cli(env, content_root, "branch", "status"))["active_branch"] is None


def test_branch_start_uses_the_stored_edcopilot_root(tmp_path):
    """With no env var, branch start resolves the root from the config file."""
    content_root, runtime_root, env = _environment(tmp_path)
    stored_env = {
        key: value
        for key, value in env.items()
        if key != "EDCG_EDCOPILOT_ROOT"
    }
    (content_root / "edcopilot-customization-generator.toml").write_text(
        f'[roots]\nedcopilot = "{runtime_root.as_posix()}"\n', encoding="utf-8"
    )

    started = _json(_cli(stored_env, content_root, "branch", "start", "stored root"))

    assert "content" in started["repos_branched"]
    assert "runtime" in started["repos_branched"]
    for root in (content_root, runtime_root):
        repo = GitRepo(root)
        try:
            assert repo.current_branch() == started["branch_name"]
        finally:
            repo.close()


def test_branch_start_names_a_stale_stored_edcopilot_root(tmp_path):
    content_root, _, env = _environment(tmp_path)
    stored_env = {
        key: value
        for key, value in env.items()
        if key != "EDCG_EDCOPILOT_ROOT"
    }
    missing = tmp_path / "gone"
    (content_root / "edcopilot-customization-generator.toml").write_text(
        f'[roots]\nedcopilot = "{missing.as_posix()}"\n', encoding="utf-8"
    )

    reply = _cli(stored_env, content_root, "branch", "start", "stale root")

    assert reply.returncode == 1
    error = json.loads(reply.stdout)["error"]
    assert "configured path no longer exists" in error
    assert str(missing) in error


def test_branch_start_fails_clearly_without_any_edcopilot_root(tmp_path):
    content_root, _, env = _environment(tmp_path)
    bare_env = {
        key: value
        for key, value in env.items()
        if key != "EDCG_EDCOPILOT_ROOT"
    }

    reply = _cli(bare_env, content_root, "branch", "start", "no root")

    assert reply.returncode == 1
    error = json.loads(reply.stdout)["error"]
    assert "without a configured EDCoPilot root" in error


def test_branch_finalize_push_flag_reports_failure(
    monkeypatch, tmp_path, capsys
):
    """`branch finalize --push` reports a refused push honestly (in-process)."""
    content_root, runtime_root, env = _environment(tmp_path)
    for key in (
        "EDCG_CONTENT_DEFINITIONS_ROOT",
        "EDCG_EDCOPILOT_ROOT",
        "EDCG_AUTO_COMMIT",
    ):
        monkeypatch.setenv(key, env[key])

    started = _json(_cli(env, content_root, "branch", "start", "push feature"))
    assert started["branch_name"]

    (content_root / "systems" / "change.txt").write_text(
        "change\n", encoding="utf-8"
    )
    _git(content_root, "add", "-A")
    _git(content_root, "commit", "-m", "change")

    calls: list[str] = []

    def failing_push(self, remote: str = "origin"):
        calls.append(remote)
        return False

    monkeypatch.setattr(GitRepo, "push", failing_push)

    assert cli.main(["branch", "finalize", "--push"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["merged"] is True
    assert data["pushed"] is False
    assert data["push_status"] == "failed"
    assert calls == ["origin", "origin"]
