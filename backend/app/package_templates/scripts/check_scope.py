"""Compare what changed with what a task allows: files outside its Files list, and dependency manifests.

Usage: python check_scope.py .ai/specs/01-booking-core.md T2 [--base HEAD]

Exit 0 when every changed file is in the task's Files (or is the spec itself) and no dependency manifest changed;
exit 1 otherwise, listing each finding; exit 2 when the spec or task cannot be read. Standard library only.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

MANIFESTS = {
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "bun.lockb",
    "pyproject.toml",
    "uv.lock",
    "poetry.lock",
    "Pipfile",
    "Pipfile.lock",
    "setup.py",
    "setup.cfg",
    "go.mod",
    "go.sum",
    "Cargo.toml",
    "Cargo.lock",
    "Gemfile",
    "Gemfile.lock",
    "composer.json",
    "composer.lock",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
}


def task_files(spec: str, task: str) -> list[str]:
    """The backticked paths on the task's **Files:** line."""
    heading = re.search(
        rf"^###\s+{re.escape(task)}\b.*$", spec, re.MULTILINE | re.IGNORECASE
    )
    if heading is None:
        raise ValueError(f"no '### {task}' section in the spec")
    rest = spec[heading.end() :]
    end = re.search(r"^##", rest, re.MULTILINE)
    section = rest[: end.start()] if end else rest
    line = re.search(r"\*\*Files:\*\*(.*?)(?:\n\*\*|\n\n|$)", section, re.DOTALL)
    if line is None:
        raise ValueError(f"{task} has no **Files:** line")
    return [normal(path) for path in re.findall(r"`([^`]+)`", line.group(1))]


def normal(path: str) -> str:
    return str(PurePosixPath(path.strip().replace("\\", "/").removeprefix("./")))


def changed(base: str) -> list[str]:
    def git(*args: str) -> list[str]:
        out = subprocess.run(
            ["git", *args], capture_output=True, text=True, check=True
        ).stdout
        return [normal(line) for line in out.splitlines() if line.strip()]

    return sorted(
        set(git("diff", "--name-only", base))
        | set(git("ls-files", "--others", "--exclude-standard"))
    )


def allowed(path: str, files: list[str]) -> bool:
    return any(
        path == item or path.startswith(item.rstrip("/") + "/") for item in files
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec")
    parser.add_argument("task", help="the task id, such as T2")
    parser.add_argument(
        "--base", default="HEAD", help="the commit to compare with (default HEAD)"
    )
    args = parser.parse_args()
    try:
        files = task_files(Path(args.spec).read_text(encoding="utf-8"), args.task)
        diff = changed(args.base)
    except (OSError, ValueError, subprocess.CalledProcessError) as problem:
        print(f"check_scope: {problem}", file=sys.stderr)
        return 2
    spec = normal(args.spec)
    unexpected = [path for path in diff if path != spec and not allowed(path, files)]
    # A manifest the task lists is an intended change (a spec that names its dependency); any other is flagged apart.
    manifests = [path for path in unexpected if PurePosixPath(path).name in MANIFESTS]
    outside = [path for path in unexpected if path not in manifests]
    if outside:
        print(f"Changed outside {args.task}'s Files:")
        print("\n".join(f"  {path}" for path in outside))
    if manifests:
        print(
            f"Dependency manifests changed outside {args.task}'s Files (a dependency the spec does not name):"
        )
        print("\n".join(f"  {path}" for path in manifests))
    if not outside and not manifests:
        print(f"In scope: {len(diff)} changed file(s), all within {args.task}'s Files.")
    return 1 if outside or manifests else 0


if __name__ == "__main__":
    sys.exit(main())
