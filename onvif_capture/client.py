from typing import Any, Dict, List, Optional

import requests
from lxml import etree
from onvif import ONVIFCamera
from zeep.helpers import serialize_object
from zeep.wsse.username import UsernameToken

from .parsers import clean_xml_string, local_name


import os
import sys

def _resolve_wsdl_dir() -> Optional[str]:
    candidates = []
    # If running in a PyInstaller bundle
    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            candidates.append(os.path.join(sys._MEIPASS, "wsdl"))
        candidates.append(os.path.join(os.path.dirname(sys.executable), "wsdl"))
        candidates.append(os.path.join(os.path.dirname(sys.executable), "_internal", "wsdl"))
    # System or standard python paths
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "wsdl"))
    candidates.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "wsdl"))
    candidates.append("/opt/onvif-capture/wsdl")
    candidates.append("/opt/onvif-capture/_internal/wsdl")
    candidates.append("/usr/share/onvif-capture/wsdl")
    for c in candidates:
        if os.path.isdir(c) and os.path.isfile(os.path.join(c, "devicemgmt.wsdl")):
            return c
    return None


class ONVIFProfileMClient:
    """Client for inspecting, configuring, and verifying ONVIF Profile M AI metadata and events."""

    def __init__(self, host: str, port: int, username: str, password: str, wsdl_dir: Optional[str] = None):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.wsdl_dir = wsdl_dir or _resolve_wsdl_dir()
        self.cam: Optional[ONVIFCamera] = None
        self.wsse = UsernameToken(username, password, use_digest=True)
        self.xaddrs: Dict[str, str] = {}
        self.session = requests.Session()

    def connect(self) -> Dict[str, Any]:
        if self.wsdl_dir:
            self.cam = ONVIFCamera(self.host, self.port, self.username, self.password, wsdl_dir=self.wsdl_dir)
        else:
            self.cam = ONVIFCamera(self.host, self.port, self.username, self.password)
        self.xaddrs = {}
        for svc in self.cam.devicemgmt.GetServices({"IncludeCapability": False}):
            self.xaddrs[svc.Namespace] = svc.XAddr
        return self.get_full_inventory()

    def soap_call(self, service_url: str, body_xml: str, timeout: float = 6.0) -> etree._Element:
        env = etree.fromstring(
            f"""<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
                xmlns:tds="http://www.onvif.org/ver10/device/wsdl"
                xmlns:trt="http://www.onvif.org/ver10/media/wsdl"
                xmlns:tr2="http://www.onvif.org/ver20/media/wsdl"
                xmlns:tan="http://www.onvif.org/ver20/analytics/wsdl"
                xmlns:tev="http://www.onvif.org/ver10/events/wsdl"
                xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2"
                xmlns:tt="http://www.onvif.org/ver10/schema">
              <s:Header/>
              <s:Body>{body_xml}</s:Body>
            </s:Envelope>"""
        )
        env, _ = self.wsse.apply(env, {})
        resp = self.session.post(
            service_url,
            data=etree.tostring(env),
            headers={"Content-Type": "application/soap+xml; charset=utf-8"},
            timeout=timeout,
        )
        parser = etree.XMLParser(recover=True, huge_tree=True)
        root = etree.fromstring(resp.content, parser=parser)
        fault = root.xpath("//*[local-name()='Fault']")
        if fault:
            raise RuntimeError(clean_xml_string(fault[0]))
        body_children = root.xpath("//*[local-name()='Body']/*")
        return body_children[0] if body_children else root

    @property
    def media2_url(self) -> str:
        return self.xaddrs.get(
            "http://www.onvif.org/ver20/media/wsdl",
            f"http://{self.host}:{self.port}/onvif/media2_service",
        )

    @property
    def analytics_url(self) -> str:
        return self.xaddrs.get(
            "http://www.onvif.org/ver20/analytics/wsdl",
            f"http://{self.host}:{self.port}/onvif/analytics_service",
        )

    def get_full_inventory(self) -> Dict[str, Any]:
        """Query verified Profile M scopes, Media1/Media2 profiles, metadata config, analytics modules, rules, topics, and supported metadata schemas."""
        if not self.cam:
            raise RuntimeError("Camera not connected")

        dev_info = serialize_object(self.cam.devicemgmt.GetDeviceInformation())
        scopes_raw = self.cam.devicemgmt.GetScopes()
        scopes = [s.ScopeItem for s in scopes_raw if getattr(s, "ScopeItem", None)]
        is_profile_m = any("Profile/M" in s for s in scopes)

        media1 = self.cam.create_media_service()
        m1_profiles = media1.GetProfiles()
        profiles_info = []
        for p in m1_profiles:
            uri_obj = media1.GetStreamUri(
                {
                    "StreamSetup": {"Stream": "RTP-Unicast", "Transport": {"Protocol": "RTSP"}},
                    "ProfileToken": p.token,
                }
            )
            res = p.VideoEncoderConfiguration.Resolution if getattr(p, "VideoEncoderConfiguration", None) else None
            profiles_info.append(
                {
                    "name": p.Name,
                    "token": p.token,
                    "width": res.Width if res else 0,
                    "height": res.Height if res else 0,
                    "encoding": p.VideoEncoderConfiguration.Encoding
                    if getattr(p, "VideoEncoderConfiguration", None)
                    else "",
                    "rtsp_uri": uri_obj.Uri,
                }
            )

        meta_configs = media1.GetMetadataConfigurations()
        meta_cfg_dict = serialize_object(meta_configs[0]) if meta_configs else {}
        analytics_enabled = bool(meta_cfg_dict.get("Analytics", False))
        events_enabled = meta_cfg_dict.get("Events") is not None

        try:
            m2_resp = self.soap_call(
                self.media2_url, "<tr2:GetProfiles><tr2:Type>All</tr2:Type></tr2:GetProfiles>"
            )
            media2_profiles_xml = clean_xml_string(m2_resp)
        except Exception as exc:
            media2_profiles_xml = f"Media2 query error: {exc}"

        vacs = media1.GetVideoAnalyticsConfigurations()
        vac_token = vacs[0].token if vacs else "VideoAnalyticsConfigurationToken_1"

        analytics_svc = self.cam.create_analytics_service()
        supported_mods_obj = analytics_svc.GetSupportedAnalyticsModules({"ConfigurationToken": vac_token})
        supported_modules = []
        for desc in getattr(supported_mods_obj, "AnalyticsModuleDescription", []) or []:
            topics = [
                m.ParentTopic for m in (getattr(desc, "Messages", None) or []) if getattr(m, "ParentTopic", None)
            ]
            simple_params = (
                [
                    {"name": s.Name, "type": s.Type}
                    for s in (getattr(desc.Parameters, "SimpleItemDescription", None) or [])
                ]
                if getattr(desc, "Parameters", None)
                else []
            )
            data_simple = []
            data_element = []
            for m in getattr(desc, "Messages", None) or []:
                if getattr(m, "Data", None):
                    for s in getattr(m.Data, "SimpleItemDescription", None) or []:
                        data_simple.append(f"{s.Name} ({s.Type})")
                    for e in getattr(m.Data, "ElementItemDescription", None) or []:
                        data_element.append(f"{e.Name} ({e.Type})")
            supported_modules.append(
                {
                    "type": desc.Name,
                    "topics": topics,
                    "parameters": simple_params,
                    "data_simple": data_simple,
                    "data_element": data_element,
                }
            )

        active_modules = self.get_analytics_modules(vac_token)
        rules = self.get_rules(vac_token)

        try:
            sm_resp = self.soap_call(self.analytics_url, "<tan:GetSupportedMetadata/>")
            supported_metadata_xml = clean_xml_string(sm_resp)
        except Exception as exc:
            supported_metadata_xml = f"GetSupportedMetadata error: {exc}"

        events_svc = self.cam.create_events_service()
        ep = events_svc.GetEventProperties()
        topics_list = []
        if getattr(ep, "TopicSet", None) and getattr(ep.TopicSet, "_value_1", None):
            for elem in ep.TopicSet._value_1:
                for sub in elem.xpath(".//*[@*[local-name()='topic']='true']"):
                    anc = [
                        local_name(a.tag)
                        for a in sub.iterancestors()
                        if local_name(a.tag) not in ("Envelope", "Body", "GetEventPropertiesResponse", "TopicSet")
                    ]
                    path = "/".join(reversed(anc))
                    leaf = local_name(sub.tag)
                    full_topic = f"{path}/{leaf}" if path else leaf
                    msg_desc = sub.xpath("./*[local-name()='MessageDescription']")
                    source_fields = []
                    data_fields = []
                    is_prop = False
                    if msg_desc:
                        is_prop = msg_desc[0].get("IsProperty", "false") == "true"
                        for sf in msg_desc[0].xpath("./*[local-name()='Source']/*"):
                            source_fields.append(f"{sf.get('Name')}:{sf.get('Type')}")
                        for df in msg_desc[0].xpath("./*[local-name()='Data']/*"):
                            data_fields.append(f"{df.get('Name')}:{df.get('Type')}")
                    topics_list.append(
                        {
                            "topic": f"tns1:{full_topic}",
                            "is_property": is_prop,
                            "source": source_fields,
                            "data": data_fields,
                        }
                    )

        return {
            "device_info": dev_info,
            "scopes": scopes,
            "is_profile_m": is_profile_m,
            "xaddrs": self.xaddrs,
            "profiles": profiles_info,
            "metadata_config": meta_cfg_dict,
            "analytics_enabled": analytics_enabled,
            "events_enabled": events_enabled,
            "vac_token": vac_token,
            "supported_modules": supported_modules,
            "active_modules": active_modules,
            "rules": rules,
            "topics": topics_list,
            "media2_profiles_xml": media2_profiles_xml,
            "supported_metadata_xml": supported_metadata_xml,
        }

    def set_metadata_analytics_enabled(self, enable_analytics: bool = True, enable_events: bool = True) -> Dict[str, Any]:
        """Enable or disable Analytics and Events in the camera's MetadataConfiguration."""
        if not self.cam:
            raise RuntimeError("Camera not connected")
        media1 = self.cam.create_media_service()
        configs = media1.GetMetadataConfigurations()
        if not configs:
            raise RuntimeError("No MetadataConfiguration found on camera")
        mc = configs[0]
        mc.Analytics = bool(enable_analytics)
        if enable_events:
            mc.Events = {"Filter": None, "SubscriptionPolicy": None}
        else:
            mc.Events = None
        media1.SetMetadataConfiguration({"Configuration": mc, "ForcePersistence": True})
        updated = media1.GetMetadataConfiguration({"ConfigurationToken": mc.token})
        return serialize_object(updated)

    def get_analytics_modules(self, vac_token: str = "VideoAnalyticsConfigurationToken_1") -> List[Dict[str, Any]]:
        resp = self.soap_call(
            self.analytics_url,
            f"<tan:GetAnalyticsModules><tan:ConfigurationToken>{vac_token}</tan:ConfigurationToken></tan:GetAnalyticsModules>",
        )
        modules = []
        for mod in resp.xpath(".//*[local-name()='AnalyticsModule']"):
            params = {}
            for si in mod.xpath(".//*[local-name()='SimpleItem']"):
                params[si.get("Name", "")] = si.get("Value", "")
            modules.append(
                {
                    "name": mod.get("Name", ""),
                    "type": mod.get("Type", ""),
                    "parameters": params,
                }
            )
        return modules

    def get_rules(self, vac_token: str = "VideoAnalyticsConfigurationToken_1") -> List[Dict[str, Any]]:
        resp = self.soap_call(
            self.analytics_url,
            f"<tan:GetRules><tan:ConfigurationToken>{vac_token}</tan:ConfigurationToken></tan:GetRules>",
        )
        rules = []
        for rule in resp.xpath(".//*[local-name()='Rule']"):
            params = {}
            for si in rule.xpath(".//*[local-name()='SimpleItem']"):
                params[si.get("Name", "")] = si.get("Value", "")
            rules.append(
                {
                    "name": rule.get("Name", ""),
                    "type": rule.get("Type", ""),
                    "parameters": params,
                }
            )
        return rules

    def modify_rule(
        self,
        rule_name: str,
        rule_type: str,
        parameters: Dict[str, str],
        vac_token: str = "VideoAnalyticsConfigurationToken_1",
    ) -> None:
        simple_items_xml = "\n".join(f'<tt:SimpleItem Name="{k}" Value="{v}"/>' for k, v in parameters.items())
        body = f"""
        <tan:ModifyRules>
          <tan:ConfigurationToken>{vac_token}</tan:ConfigurationToken>
          <tan:Rule Name="{rule_name}" Type="{rule_type}">
            <tt:Parameters>
              {simple_items_xml}
            </tt:Parameters>
          </tan:Rule>
        </tan:ModifyRules>
        """
        self.soap_call(self.analytics_url, body)

