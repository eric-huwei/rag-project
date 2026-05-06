from __future__ import annotations

import json
from pathlib import Path


def _load_main():
    workflow_path = None
    if "__file__" in globals():
        workflow_path = Path(__file__).with_name("地址抽取.json")
    else:
        workflow_path = Path.cwd() / "backend/地址抽取.json"

    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))

    code_blocks: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("key") == "code" and isinstance(node.get("value"), str):
                code_blocks.append(node["value"])
            for value in node.values():
                walk(value)
            return

        if isinstance(node, list):
            for item in node:
                walk(item)

    walk(workflow)

    for code in code_blocks:
        if (
            "from difflib import SequenceMatcher" in code
            and "last_unmatched_address" in code
        ):
            namespace: dict[str, object] = {}
            exec(code, namespace)
            return namespace["main"]

    raise RuntimeError("address postprocess workflow code block not found")


_MAIN = _load_main()


def main(**kwargs):
    return _MAIN(**kwargs)
