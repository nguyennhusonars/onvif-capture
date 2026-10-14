# ONVIF Analytics Rule Parameter Bounds & Tuning Guide

| Rule Name | Rule Type | Parameter Name | XML Type | Recommended Range / Notes |
| :--- | :--- | :--- | :--- | :--- |
| `MRD_rule0` | `tt:MotionRegionDetector` | `Sensitivity` | `xs:integer` | `1` – `5` (Default: `1`) |
| `FR_rule0` | `tt:FaceRecognition` | `EnrollmentID` | `xs:string` | Target enrolled face ID string (Default: `"123456"`) |
| `FR_rule0` | `tt:FaceRecognition` | `Likelihood` | `xs:float` | `0.10` – `0.95` similarity threshold (Default: `0.45`) |
| `FD_rule0` | `tt:FaceDetection` | `Threshold` | `xs:float` | `0.20` – `0.99` confidence threshold (Default: `0.98`; lower to `0.60` for more frequent triggers) |
| `CD_rule0` | `tt:CrowdDetection` | `Threshold` | `xs:float` | `0.10` – `0.95` person confidence (Default: `0.25`) |
| `CD_rule0` | `tt:CrowdDetection` | `Detection number` | `xs:integer` | Minimum people count to trigger crowd event (Default: `3`) |
| `ID_rule0` | `tt:IntrusionDetection` | `Threshold` | `xs:float` | `0.10` – `0.95` object confidence (Default: `0.25`) |
| `LC_rule0` | `tt:LineCross` | `Threshold` | `xs:float` | `0.10` – `0.95` object confidence (Default: `0.25`) |
| `RLV_rule0` | `tt:RedLightViolation` | `Delay time` | `xs:integer` | Seconds after red light before triggering (Default: `0`) |
| `WP_rule0` | `tt:WrongParking` | `Parking time` | `xs:integer` | Seconds before parking violation triggers (Default: `900`) |
| `WP_rule0` | `tt:WrongParking` | `Stopping time` | `xs:integer` | Seconds before stopping violation triggers (Default: `60`) |
| `WP_rule0` | `tt:WrongParking` | `Time` | `xs:integer` | Bitmask/schedule integer preserved from camera (`1074791425`) |
| `LPR_rule0` | `tt:LicensePlateRecognition` | `Likelihood` | `xs:float` | `0.05` – `0.95` OCR confidence threshold (Default: `0.05`) |

