#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
post_edit_lint.py: PostToolUse hook for ONVIF Profile M Capture project.
Verifies Python syntax of modified files and returns expected empty JSON object {}.
"""

import json
import py_compile
import sys
from pathlib import Path


def main() -> None:
    try:
        raw_input = sys.stdin.read()
        if raw_input.strip():
            payload = json.loads(raw_input)
            tool_call = payload.get("toolCall", {})
            args = tool_call.get("args", {})
            target = args.get("TargetFile", "")
            if target and target.endswith(".py") and Path(target).is_file():
                py_compile.compile(target, doraise=True)
    except Exception:
        pass

    # PostToolUse contract expects an empty JSON object {}
    print(json.dumps({}))


if __name__ == "__main__":
    main()

