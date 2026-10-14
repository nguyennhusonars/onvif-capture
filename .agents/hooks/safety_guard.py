#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
safety_guard.py: PreToolUse hook for ONVIF Profile M Capture project.
Audits shell commands for destructive filesystem actions or dangerous ONVIF device operations
(such as factory reset, firmware overwrite, or deleting camera analytics modules).
"""

import json
import re
import sys

DANGEROUS_PATTERNS = [
    (r"\brm\s+-[rf]{1,2}\s+/\b", "Prevent recursive deletion of root filesystem."),
    (r"\bmkfs\b", "Prevent formatting storage partitions."),
    (r"\bdd\s+if=.*\s+of=/dev/sd", "Prevent direct block-level disk overwrites."),
    (r"SetSystemFactoryDefault", "Prevent resetting the ONVIF camera to factory defaults without confirmation."),
    (r"UpgradeSystemFirmware|StartFirmwareUpgrade", "Prevent flashing camera firmware without confirmation."),
    (r"DeleteAnalyticsModules|DeleteRules", "Prevent deleting factory analytics modules or rules on the camera."),
]


def main() -> None:
    try:
        raw_input = sys.stdin.read()
        if not raw_input.strip():
            print(json.dumps({"decision": "allow"}))
            return

        payload = json.loads(raw_input)
        tool_call = payload.get("toolCall", {})
        args = tool_call.get("args", {})
        command = args.get("CommandLine", "")

        for pattern, reason in DANGEROUS_PATTERNS:
            if re.search(pattern, command):
                print(
                    json.dumps(
                        {
                            "decision": "ask",
                            "reason": f"Safety Guard: {reason} Command: '{command}'",
                        }
                    )
                )
                return

        print(json.dumps({"decision": "allow"}))
    except Exception as exc:
        print(
            json.dumps(
                {
                    "decision": "allow",
                    "reason": f"Hook bypass on parse note: {exc}",
                }
            )
        )


if __name__ == "__main__":
    main()

