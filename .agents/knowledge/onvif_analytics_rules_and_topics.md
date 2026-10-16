# ONVIF Analytics Modules, Active Rules & Event TopicSet Reference

## 1. Supported & Active Analytics Modules (`VideoAnalyticsConfigurationToken_1`)

All 9 modules below are instantiated in `VideoAnalyticsConfigurationName_1` (`VideoAnalyticsConfigurationToken_1`):

| Active Module Name | ONVIF Module Type | Parent Event Topic | Event Data (`SimpleItem`) | Event Data (`ElementItem`) |
| :--- | :--- | :--- | :--- | :--- |
| `MyMotionRegionDetector0` | `tt:MotionRegionDetector` | `tns1:RuleEngine/MotionRegionDetector/Motion` | `State (xs:boolean)` | — |
| `MyFaceRecognitionModule0` | `tt:FaceRecognition` | `tns1:RuleEngine/Recognition/Face` | `EnrollmentID (xs:string)`, `Likelihood (xs:float)` | *(Live events include `ObjectId`, `BoundingBox`, `Image` [JPEG], `Template` [base64 biometric embedding])* |
| `MyFaceDetectionModule0` | `tt:FaceDetection` | `tns1:RuleEngine/FaceDetector/Detected` | `State (xs:boolean)` | *(Live events also include `ObjectId`, `BoundingBox`, `Image`)* |
| `MyCrowdDetectionModule0` | `tt:CrowdDetection` | `tns1:RuleEngine/Detection/Crowd` | `State (xs:boolean)` | — |
| `MyIntrusionDetectionModule0` | `tt:IntrusionDetection` | `tns1:RuleEngine/Detection/Intrusion` | `State (xs:boolean)` / `Likelihood (xs:float)` | `ObjectId`, `BoundingBox`, `Image` (`xs:base64Binary`) |
| `MyLineCrossModule0` | `tt:LineCross` | `tns1:RuleEngine/LineDetector/Crossed` | `Count (xs:integer)` | — |
| `MyRedLightViolationModule0` | `tt:RedLightViolation` | `tns1:RuleEngine/Traffic/RedLight` | `Likelihood (xs:float)` | `LicensePlateInfo (tt:LicensePlateInfo)` |
| `MyWrongParkingModule0` | `tt:WrongParking` | `tns1:RuleEngine/Traffic/WrongParking` | `Likelihood (xs:float)` | `LicensePlateInfo (tt:LicensePlateInfo)` |
| `MyLicensePlateRecognitionModule0` | `tt:LicensePlateRecognition` | `tns1:RuleEngine/Recognition/LicensePlate` | `Likelihood (xs:float)` | `LicensePlateInfo (tt:LicensePlateInfo)` |

---

## 2. Active Rule Configurations (`tan:GetRules` / `tan:ModifyRules`)

| Rule Name | Rule Type | Configurable Parameters (`SimpleItem`) | Default Camera Values |
| :--- | :--- | :--- | :--- |
| `MRD_rule0` | `tt:MotionRegionDetector` | `Sensitivity` (`xs:integer`) | `Sensitivity = 1` |
| `FR_rule0` | `tt:FaceRecognition` | `EnrollmentID` (`xs:string`), `Likelihood` (`xs:float`) | `EnrollmentID = 123456`, `Likelihood = 0.45` |
| `FD_rule0` | `tt:FaceDetection` | `Threshold` (`xs:float`) | `Threshold = 0.98` |
| `CD_rule0` | `tt:CrowdDetection` | `Threshold` (`xs:float`), `Detection number` (`xs:integer`) | `Threshold = 0.25`, `Detection number = 3` |
| `ID_rule0` | `tt:IntrusionDetection` | `Threshold` (`xs:float`) | `Threshold = 0.25` |
| `LC_rule0` | `tt:LineCross` | `Threshold` (`xs:float`) | `Threshold = 0.25` |
| `RLV_rule0` | `tt:RedLightViolation` | `Delay time` (`xs:integer`) | `Delay time = 0` |
| `WP_rule0` | `tt:WrongParking` | `Parking time` (`xs:integer`), `Stopping time` (`xs:integer`), `Time` (`xs:integer`) | `Parking time = 900`, `Stopping time = 60`, `Time = 1074791425` |
| `LPR_rule0` | `tt:LicensePlateRecognition` | `Likelihood` (`xs:float`) | `Likelihood = 0.05` |

---

## 3. Modifying Rules via SOAP (`tan:ModifyRules`)

```xml
<tan:ModifyRules>
  <tan:ConfigurationToken>VideoAnalyticsConfigurationToken_1</tan:ConfigurationToken>
  <tan:Rule Name="FD_rule0" Type="tt:FaceDetection">
    <tt:Parameters>
      <tt:SimpleItem Name="Threshold" Value="0.85"/>
    </tt:Parameters>
  </tan:Rule>
</tan:ModifyRules>
```

