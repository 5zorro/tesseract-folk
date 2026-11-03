"""Guards for docs/SAFETY.md: the simulation core stays free of outside I/O.

These read the source with `ast` instead of importing it, so they catch an
import even in code paths the other tests never run.
"""
import ast
from pathlib import Path

SIM = Path(__file__).resolve().parent.parent / "sim"

# Anything that reaches the network, other processes, native code, or loads code.
FORBIDDEN_MODULES = {
    "socket", "ssl", "http", "urllib", "urllib3", "requests", "httpx", "aiohttp",
    "ftplib", "smtplib", "telnetlib", "xmlrpc", "websocket", "websockets",
    "subprocess", "multiprocessing", "os", "shutil", "ctypes", "cffi",
    "pickle", "shelve", "marshal", "dill", "importlib", "runpy", "code", "codeop",
    "anthropic", "openai",
}
FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__"}


def sim_sources():
    files = sorted(SIM.glob("*.py"))
    assert files, "no sim/*.py found"
    return [(f.name, ast.parse(f.read_text(encoding="utf-8"))) for f in files]


def test_sim_imports_no_io_or_code_loading_modules():
    hits = []
    for name, tree in sim_sources():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                mods = [node.module or ""]
            else:
                continue
            hits += [f"{name}: {m}" for m in mods if m.split(".")[0] in FORBIDDEN_MODULES]
    assert not hits, f"sim/ must not import these (see docs/SAFETY.md §3): {hits}"


def test_sim_never_calls_eval_exec_or_dynamic_import():
    hits = []
    for name, tree in sim_sources():
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id in FORBIDDEN_CALLS):
                hits.append(f"{name}:{node.lineno} {node.func.id}()")
    assert not hits, f"sim/ must not call these (see docs/SAFETY.md §3): {hits}"


def test_sim_never_enables_numpy_pickle_loading():
    hits = []
    for name, tree in sim_sources():
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "allow_pickle":
                value = node.value
                if not (isinstance(value, ast.Constant) and value.value is False):
                    hits.append(f"{name}:{value.lineno}")
    assert not hits, f"snapshots must never load pickles (see docs/SAFETY.md §4): {hits}"
