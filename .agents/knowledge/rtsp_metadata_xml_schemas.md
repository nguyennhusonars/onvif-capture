# RTSP `vnd.onvif.metadata` XML Schemas & Coordinate Math

## 1. Real Captured `<tt:VideoAnalytics>` Frame (`stream0/metadata`)

When the AI classifier detects an object on the video frame, the camera streams an RTP packet sequence (terminated by RTP Marker bit $M=1$) containing:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<tt:MetadataStream xmlns:tt="http://www.onvif.org/ver10/schema"
                   xmlns:fc="http://www.onvif.org/ver20/analytics/humanface"
                   xmlns:bd="http://www.onvif.org/ver20/analytics/humanbody">
  <tt:VideoAnalytics>
    <tt:Frame UtcTime="2026-10-13T01:23:51.402Z" Source="AI_Classifier" Colorspace="RGB">
      <tt:Transformation>
        <tt:Translate x="-1" y="1"/>
        <tt:Scale x="2" y="-2"/>
      </tt:Transformation>
      <tt:Object ObjectId="108">
        <tt:Appearance>
          <tt:Shape>
            <tt:BoundingBox left="0.0036" top="0.0013" right="0.4144" bottom="0.9374"/>
          </tt:Shape>
          <tt:Class>
            <tt:Type Likelihood="0.78">Human</tt:Type>
          </tt:Class>
        </tt:Appearance>
      </tt:Object>
    </tt:Frame>
  </tt:VideoAnalytics>
</tt:MetadataStream>
```

---

## 2. Real Captured `<tt:Event>` Frame with Embedded Snapshot (`stream0/metadata`)

When a rule triggers (such as `ID_rule0` for `tns1:RuleEngine/Detection/Intrusion`), the camera emits an event message containing `Likelihood`, `ObjectId`, signed ONVIF `BoundingBox`, and a Base64-encoded JPEG snapshot (`Image`):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<tt:MetadataStream xmlns:tt="http://www.onvif.org/ver10/schema"
                   xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2"
                   xmlns:tns1="http://www.onvif.org/ver10/topics">
  <tt:Event>
    <wsnt:NotificationMessage>
      <wsnt:Topic Dialect="http://www.onvif.org/ver10/tev/topicExpression/ConcreteSet">
        tns1:RuleEngine/Detection/Intrusion
      </wsnt:Topic>
      <wsnt:Message>
        <tt:Message UtcTime="2026-10-13T01:23:51.402Z">
          <tt:Source>
            <tt:SimpleItem Name="VideoSource" Value="VideoSourceToken_1"/>
            <tt:SimpleItem Name="Rule" Value="ID_rule0"/>
          </tt:Source>
          <tt:Data>
            <tt:SimpleItem Name="Likelihood" Value="0.78"/>
            <tt:ElementItem Name="ObjectId">
              <tt:ObjectId>108</tt:ObjectId>
            </tt:ElementItem>
            <tt:ElementItem Name="BoundingBox">
              <tt:Rectangle left="-0.9928" top="0.9975" right="-0.1713" bottom="-0.8748"/>
            </tt:ElementItem>
            <tt:ElementItem Name="Image">
              <tt:base64Binary>/9j/4AAQSkZJRgABAQAAAQABAAD/2wBD...</tt:base64Binary>
            </tt:ElementItem>
          </tt:Data>
        </tt:Message>
      </wsnt:Message>
    </wsnt:NotificationMessage>
  </tt:Event>
</tt:MetadataStream>
```

---

## 3. Supported Profile M Appearance Extensions (`tan:GetSupportedMetadata`)

The camera's `GetSupportedMetadata` response declares five rich semantic `Appearance` structures inside `<tt:Object>`:
1. **`<tt:VehicleInfo>`**: `<tt:Type Likelihood="...">Car</tt:Type>`, `<tt:Brand Likelihood="...">Volvo</tt:Brand>`, `<tt:Model Likelihood="...">XC60</tt:Model>`
2. **`<tt:LicensePlateInfo>`**: `<tt:PlateNumber Likelihood="...">6DZG261</tt:PlateNumber>`, `<tt:PlateType Likelihood="...">Normal</tt:PlateType>`, `<tt:CountryCode Likelihood="...">US</tt:CountryCode>`, `<tt:IssuingEntity Likelihood="...">California</tt:IssuingEntity>`
3. **`<tt:HumanFace>`**: `<tt:Gender Likelihood="...">Male</tt:Gender>`, `<tt:Temperature>36.8</tt:Temperature>`, `<tt:Hair Likelihood="...">Straight</tt:Hair>`
4. **`<tt:HumanBody>`**: `<tt:BodyMetric><tt:Height>172</tt:Height><tt:BodyShape>Fat</tt:BodyShape></tt:BodyMetric>`
5. **`<tt:GeoLocation>`**: `<tt:lon>33.423</tt:lon>`, `<tt:lat>146.443</tt:lat>`

---

## 4. Coordinate Normalization Math

Notice how the same detection (`ObjectId="108"` at `2026-10-13T01:23:51.402Z`) is represented in two different coordinate spaces:
* In `<tt:VideoAnalytics><tt:Frame>`:
  $$\text{left} = 0.0036, \quad \text{top} = 0.0013, \quad \text{right} = 0.4144, \quad \text{bottom} = 0.9374$$
* In `<tt:Event><tt:ElementItem Name="BoundingBox"><tt:Rectangle>`:
  $$x_{\text{left}} = -0.9928, \quad y_{\text{top}} = 0.9975, \quad x_{\text{right}} = -0.1713, \quad y_{\text{bottom}} = -0.8748$$
* Applying the inverse transformation of `<tt:Translate x="-1" y="1"/>` and `<tt:Scale x="2" y="-2"/>`:
  $$u = \frac{x + 1}{2}, \quad v = \frac{1 - y}{2}$$
  yields the exact same $[0, 1]$ rectangle:
  $$u_1 = \frac{-0.9928 + 1}{2} = 0.0036, \quad v_1 = \frac{1 - 0.9975}{2} = 0.00125$$
  $$u_2 = \frac{-0.1713 + 1}{2} = 0.41435, \quad v_2 = \frac{1 - (-0.8748)}{2} = 0.9374$$

