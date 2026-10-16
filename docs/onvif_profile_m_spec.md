# ONVIF Profile M Protocol Specification & Implementation Guide

## 1. Overview of ONVIF Profile M

**ONVIF Profile M** (`onvif://www.onvif.org/Profile/M`) standardizes metadata communication for analytics applications, smart cameras, and AI-enabled video management systems (VMS).

### Core Conformance Pillars:
1. **Analytics Configuration:** Configures analytics modules, rules, and event triggers via `AnalyticsEnginePort` and `RuleEnginePort`.
2. **Metadata Streaming:** Emits synchronized object tracking classifications, bounding boxes, and geometric properties over RTSP `vnd.onvif.metadata`.
3. **Event Notifications:** Emits standard rule violations, line crossing, intrusion detection, license plate recognition, and face recognition events via PullPoint and RTSP metadata.
4. **Data Extensions:** Standardized appearance models (`HumanFace`, `HumanBody`, `VehicleInfo`, `LicensePlateInfo`, `GeoLocation`).

---

## 2. XML Payload Structures

### 2.1 Spatial Video Analytics Frame (`<tt:VideoAnalytics>`)
Emitted continuously (typically 25–30 FPS) inside `<tt:MetadataStream>`:

```xml
<tt:MetadataStream xmlns:tt="http://www.onvif.org/ver10/schema">
  <tt:VideoAnalytics>
    <tt:Frame UtcTime="2026-10-15T08:30:00.120Z">
      <tt:Object ObjectId="104">
        <tt:Appearance>
          <tt:Shape>
            <tt:BoundingBox bottom="0.82" left="0.41" right="0.59" top="0.32"/>
          </tt:Shape>
          <tt:Class>
            <tt:Type Likelihood="0.94">Human</tt:Type>
          </tt:Class>
          <tt:Extension>
            <tt:HumanFace>
              <tt:Pose Pitch="1.2" Roll="-0.4" Yaw="12.5"/>
              <tt:Age Likelihood="0.85">32</tt:Age>
              <tt:Gender Likelihood="0.92">Male</tt:Gender>
            </tt:HumanFace>
          </tt:Extension>
        </tt:Appearance>
      </tt:Object>
    </tt:Frame>
  </tt:VideoAnalytics>
</tt:MetadataStream>
```

### 2.2 Security Alarm Notification (`<tt:Event>`)
Emitted upon rule violation triggers (e.g., Intrusion Detection or Face Recognition):

```xml
<tt:MetadataStream xmlns:tt="http://www.onvif.org/ver10/schema" xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2">
  <tt:Event>
    <wsnt:NotificationMessage>
      <wsnt:Topic Dialect="http://www.onvif.org/ver10/tev/topicExpression/ConcreteSet">
        tns1:RuleEngine/FaceRecognition/Face
      </wsnt:Topic>
      <wsnt:Message>
        <tt:Message PropertyOperation="Initialized" UtcTime="2026-10-15T08:30:00.120Z">
          <tt:Source>
            <tt:SimpleItem Name="VideoAnalyticsConfigurationToken" Value="VideoAnalyticsConfigurationToken_1"/>
            <tt:SimpleItem Name="Rule" Value="FaceRecognitionRule_1"/>
          </tt:Source>
          <tt:Data>
            <tt:SimpleItem Name="Likelihood" Value="0.98"/>
            <tt:SimpleItem Name="MatchedId" Value="EMP_10492"/>
            <tt:ElementItem Name="BoundingBox">
              <tt:Rectangle bottom="-0.3" left="-0.2" right="0.3" top="0.5"/>
            </tt:ElementItem>
            <tt:ElementItem Name="Image">
              <tt:base64Binary>/9j/4AAQSkZJRgABAQEASABIAAD...</tt:base64Binary>
            </tt:ElementItem>
            <tt:ElementItem Name="Template">
              <tt:base64Binary>AQIDBAUGBwgJCgsMDQ4PEBES...</tt:base64Binary>
            </tt:ElementItem>
          </tt:Data>
        </tt:Message>
      </wsnt:Message>
    </wsnt:NotificationMessage>
  </tt:Event>
</tt:MetadataStream>
```

---

## 3. Strict Separation of Snapshot JPEGs vs Biometric Templates

In ONVIF Profile M Face Recognition:
* `<tt:ElementItem Name="Image">` contains a Base64-encoded visual JPEG snapshot of the detected face.
* `<tt:ElementItem Name="Template">` (or `Feature`, `Embedding`) contains a Base64-encoded raw binary embedding vector used for biometric matching.

### Verification Implementation
To prevent corrupting visual snapshots with non-image binary data, `onvif_capture/parsers.py` verifies file signatures:
```python
# Verify JPEG magic bytes \xff\xd8 or PNG magic bytes \x89PNG
if raw_bytes.startswith(b"\xff\xd8") or raw_bytes.startswith(b"\x89PNG"):
    item.image_bytes = raw_bytes
elif "template" in elem_name or "feature" in elem_name or "embedding" in elem_name:
    item.template_bytes = raw_bytes
```

---

## 4. SOAP Envelopes & WS-Security Authentication

All SOAP requests must include a WS-Security header signed with `PasswordDigest`:

$$\text{PasswordDigest} = \text{Base64}(\text{SHA1}(\text{Nonce} + \text{Created} + \text{Password}))$$

### 4.1 Activating Metadata Streaming (`SetMetadataConfiguration`)
By default, camera metadata tokens may disable analytics. The client activates both spatial and event metadata using:
```xml
<trt:SetMetadataConfiguration xmlns:trt="http://www.onvif.org/ver10/media/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema">
  <trt:Configuration>
    <tt:token>MetadataConfigurationToken_1</tt:token>
    <tt:Name>MetadataConfig</tt:Name>
    <tt:Analytics>true</tt:Analytics>
    <tt:Events>
      <tt:Filter>
        <wsnt:TopicExpression Dialect="http://www.onvif.org/ver10/tev/topicExpression/ConcreteSet">
          //.
        </wsnt:TopicExpression>
      </tt:Filter>
    </tt:Events>
  </trt:Configuration>
  <trt:ForcePersistence>true</trt:ForcePersistence>
</trt:SetMetadataConfiguration>
```

### 4.2 Dynamic Rule Tuning (`ModifyRules`)
Direct raw SOAP call against `/onvif/analytics_service` modifying rule parameters:
```xml
<tan:ModifyRules xmlns:tan="http://www.onvif.org/ver20/analytics/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema">
  <tan:ConfigurationToken>VideoAnalyticsConfigurationToken_1</tan:ConfigurationToken>
  <tan:Rule Name="ID_rule0" Type="tt:IntrusionDetector">
    <tt:Parameters>
      <tt:SimpleItem Name="Sensitivity" Value="85"/>
      <tt:SimpleItem Name="AlarmDuration" Value="3"/>
    </tt:Parameters>
  </tan:Rule>
</tan:ModifyRules>
```

