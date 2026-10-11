from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / "lab/participant-chain/delivery/scope-hook.sh"
ZERO = "0" * 40


def git(directory: Path, *arguments: str) -> str:
    return subprocess.check_output(["git", "-C", str(directory), *arguments], text=True).strip()


def check_hook(directory: Path, old: str, new: str, branch: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", str(HOOK)],
        cwd=directory,
        input=f"{old} {new} refs/heads/{branch}\n",
        text=True,
        capture_output=True,
        check=False,
    )


def test_scope_hook_accepts_only_reconciled_branch_and_path(tmp_path: Path) -> None:
    git(tmp_path, "init", "-b", "lab-runtime")
    git(tmp_path, "config", "user.name", "lab")
    git(tmp_path, "config", "user.email", "lab@example.invalid")
    runtime = tmp_path / "runtime-builder"
    runtime.mkdir()
    (runtime / "deployment.yaml").write_text("kind: Deployment\n")
    git(tmp_path, "add", "runtime-builder/deployment.yaml")
    git(tmp_path, "commit", "-m", "baseline")
    allowed = git(tmp_path, "rev-parse", "HEAD")

    assert check_hook(tmp_path, ZERO, allowed, "lab-runtime").returncode == 0
    assert check_hook(tmp_path, ZERO, allowed, "other-branch").returncode != 0

    (tmp_path / "unrelated.yaml").write_text("kind: Secret\n")
    git(tmp_path, "add", "unrelated.yaml")
    git(tmp_path, "commit", "-m", "outside path")
    disallowed = git(tmp_path, "rev-parse", "HEAD")
    assert check_hook(tmp_path, allowed, disallowed, "lab-runtime").returncode != 0
