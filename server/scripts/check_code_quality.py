"""Small structural code-review gates for backend source files."""

from __future__ import annotations

import ast
from pathlib import Path

MAX_FILE_LINES = 500
MAX_PARAMS = 5

CHECK_PATHS = [
    Path("config.py"),
    Path("db"),
    Path("routes"),
    Path("services"),
    Path("utils"),
]


def iter_python_files() -> list[Path]:
    files: list[Path] = []
    for path in CHECK_PATHS:
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(path.rglob("*.py"))
    return sorted(
        p for p in files
        if "__pycache__" not in p.parts
    )


def count_params(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    args = node.args
    return (
        len(args.posonlyargs)
        + len(args.args)
        + len(args.kwonlyargs)
        + bool(args.vararg)
        + bool(args.kwarg)
    )


def main() -> int:
    problems: list[str] = []
    for path in iter_python_files():
        source = path.read_text(encoding="utf-8")
        line_count = len(source.splitlines())
        if line_count > MAX_FILE_LINES:
            problems.append(f"{path}: {line_count} lines > {MAX_FILE_LINES}")

        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                params = count_params(node)
                if params > MAX_PARAMS:
                    problems.append(f"{path}:{node.lineno} {node.name} has {params} params > {MAX_PARAMS}")

    if problems:
        print("Code quality check failed:")
        for problem in problems:
            print(f"- {problem}")
        return 1

    print(f"Code quality check passed: files <= {MAX_FILE_LINES} lines, functions <= {MAX_PARAMS} params")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
