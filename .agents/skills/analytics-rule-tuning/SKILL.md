---
name: analytics-rule-tuning
description: >-
  Use this skill when the user asks to view, calibrate, or modify ONVIF Profile M AI rule
  thresholds or parameters (such as FaceDetection, FaceRecognition, IntrusionDetection,
  CrowdDetection, LineCross, LicensePlateRecognition, RedLightViolation, WrongParking,
  or MotionRegionDetector) on the camera.
---

# ONVIF Analytics Rule Tuning (`tan:ModifyRules`)

Use this skill to inspect and adjust AI detection thresholds and rule parameters on `VideoAnalyticsConfigurationToken_1`.

## Steps

1. **Inspect Current Rules:**
   Query active rules using `ONVIFProfileMClient.get_rules("VideoAnalyticsConfigurationToken_1")` or run the diagnostics skill script.
2. **Consult Parameter Bounds & Semantics:**
   Read [rule_parameter_bounds.md](./references/rule_parameter_bounds.md) to verify valid parameter names, types, and recommended ranges before modifying any rule.
3. **Apply Rule Update & Verify Persistence:**
   Call `client.modify_rule(rule_name, rule_type, parameters)` and immediately re-read `client.get_rules()` to verify the camera accepted and persisted the new parameter values.

