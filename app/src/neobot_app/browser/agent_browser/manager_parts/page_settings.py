"""PageSettingsMixin：拆分自 manager.py"""

from __future__ import annotations

import asyncio


class PageSettingsMixin:
    """对话框、Frame、等待与浏览器设备/网络仿真设置。"""

    # ── 对话框处理 ──

    async def dialog_accept(self, text: str = "") -> dict:
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(page.handle_alert, text or True)
            return {"success": True, "action": "accept"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def dialog_dismiss(self) -> dict:
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(page.handle_alert, False)
            return {"success": True, "action": "dismiss"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def dialog_status(self) -> dict:
        try:
            page = await self._ensure_page()
            has_alert = await asyncio.to_thread(
                page.run_js,
                "return window.__alertActive === true || false",
            )
            return {"success": True, "has_dialog": bool(has_alert)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Frame 切换 ──

    async def frame(self, selector_or_name: str) -> dict:
        try:
            page = await self._ensure_page()
            if selector_or_name == "main":
                await asyncio.to_thread(page.to_frame, None)
                return {"success": True, "frame": "main"}
            el = await asyncio.to_thread(self._find_element, selector_or_name)
            if el is None:
                return {"success": False, "error": f"未找到框架: {selector_or_name}"}
            await asyncio.to_thread(page.to_frame, el)
            return {"success": True, "frame": selector_or_name}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── 等待操作 ──

    async def wait(
        self,
        condition: str | int | float = "timeout",
        value: str = "",
        timeout: int = 20,
    ) -> dict:
        """等待页面条件满足，并兼容以秒数作为首参数的旧调用方式。"""
        try:
            page = await self._ensure_page()
            if isinstance(condition, (int, float)):
                seconds = min(max(float(condition), 0.0), 30.0)
                await asyncio.sleep(seconds)
                return {
                    "success": True,
                    "condition": "timeout",
                    "value": str(seconds),
                    "title": await self.get_title(),
                    "url": page.url,
                    "text_length": await self.get_text_length(),
                }
            if condition == "selector":
                matched = await asyncio.to_thread(
                    page.wait.ele_displayed,
                    value,
                    timeout=timeout,
                )
                if matched is False:
                    return {"success": False, "error": f"等待元素超时: {value}"}
            elif condition == "text":
                matched = await asyncio.to_thread(
                    page.wait.text_displayed,
                    value,
                    timeout=timeout,
                )
                if matched is False:
                    return {"success": False, "error": f"等待文本超时: {value}"}
            elif condition == "url":
                for _ in range(max(timeout, 0)):
                    if value in page.url:
                        break
                    await asyncio.sleep(1)
                else:
                    return {"success": False, "error": f"等待 URL 超时: {value}"}
            elif condition == "network_idle":
                await asyncio.to_thread(page.wait.load_complete, timeout=timeout)
                await asyncio.sleep(1)
            elif condition == "fn":
                for _ in range(timeout):
                    ok = await asyncio.to_thread(page.run_js, f"return !!({value})")
                    if ok and str(ok) != "false":
                        return {"success": True, "condition": "fn", "value": value}
                    await asyncio.sleep(0.5)
                return {"success": False, "error": f"JS 条件超时: {value}"}
            elif condition == "timeout":
                seconds = min(max(float(value or "2"), 0.0), 30.0)
                await asyncio.sleep(seconds)
            else:
                return {"success": False, "error": f"未知等待条件: {condition}"}
            return {"success": True, "condition": condition, "value": value}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── 浏览器设置 ──

    async def set_viewport(self, width: int, height: int, device_scale_factor: float = 1.0) -> dict:
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(
                page.run_cdp, "Emulation.setDeviceMetricsOverride",
                width=width, height=height,
                deviceScaleFactor=device_scale_factor, mobile=False,
            )
            self._device_metrics_override = {
                "width": width,
                "height": height,
                "deviceScaleFactor": device_scale_factor,
                "mobile": False,
            }
            return {"success": True, "viewport": f"{width}x{height}@{device_scale_factor}x"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def set_device(self, name: str) -> dict:
        """模拟移动设备。"""
        devices = {
            "iPhone 14": {"width": 390, "height": 844, "dsf": 3, "mobile": True},
            "iPhone 13": {"width": 390, "height": 844, "dsf": 3, "mobile": True},
            "iPhone 12": {"width": 390, "height": 844, "dsf": 3, "mobile": True},
            "iPhone SE": {"width": 375, "height": 667, "dsf": 2, "mobile": True},
            "Pixel 7": {"width": 412, "height": 915, "dsf": 2.625, "mobile": True},
            "Pixel 5": {"width": 393, "height": 851, "dsf": 2.75, "mobile": True},
            "iPad Pro": {"width": 1024, "height": 1366, "dsf": 2, "mobile": True},
            "iPad Mini": {"width": 768, "height": 1024, "dsf": 2, "mobile": True},
        }
        spec = devices.get(name)
        if not spec:
            return {"success": False, "error": f"未知设备: {name}，支持: {list(devices.keys())}"}
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(
                page.run_cdp, "Emulation.setDeviceMetricsOverride",
                width=spec["width"], height=spec["height"],
                deviceScaleFactor=spec["dsf"], mobile=spec["mobile"],
            )
            self._device_metrics_override = {
                "width": spec["width"],
                "height": spec["height"],
                "deviceScaleFactor": spec["dsf"],
                "mobile": spec["mobile"],
            }
            ua = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                  "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
                  "Mobile/15E148 Safari/604.1" if spec["mobile"] else "")
            if ua:
                await asyncio.to_thread(page.run_cdp, "Network.setUserAgentOverride", userAgent=ua)
            return {"success": True, "device": name}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def set_geolocation(self, latitude: float, longitude: float) -> dict:
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(
                page.run_cdp, "Emulation.setGeolocationOverride",
                latitude=latitude, longitude=longitude, accuracy=100,
            )
            return {"success": True, "lat": latitude, "lng": longitude}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def set_offline(self, offline: bool) -> dict:
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(
                page.run_cdp, "Network.emulateNetworkConditions",
                offline=offline, latency=0, downloadThroughput=0, uploadThroughput=0,
            )
            return {"success": True, "offline": offline}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def set_headers(self, headers: dict) -> dict:
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(page.run_cdp, "Network.enable")
            await asyncio.to_thread(page.run_cdp, "Network.setExtraHTTPHeaders", headers=headers)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def set_credentials(self, username: str, password: str) -> dict:
        """设置 HTTP Basic Auth。"""
        try:
            page = await self._ensure_page()
            encoded = __import__("base64").b64encode(f"{username}:{password}".encode()).decode()
            await asyncio.to_thread(page.run_cdp, "Network.enable")
            await asyncio.to_thread(
                page.run_cdp, "Network.setExtraHTTPHeaders",
                headers={"Authorization": f"Basic {encoded}"},
            )
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def set_media(self, color_scheme: str = "", reduced_motion: str = "") -> dict:
        """模拟媒体特性（color-scheme, prefers-reduced-motion）。"""
        try:
            page = await self._ensure_page()
            features = []
            if color_scheme:
                features.append({"name": "prefers-color-scheme", "value": color_scheme})
            if reduced_motion:
                features.append({"name": "prefers-reduced-motion", "value": reduced_motion})
            if features:
                await asyncio.to_thread(
                    page.run_cdp, "Emulation.setEmulatedMedia",
                    features=features,
                )
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
