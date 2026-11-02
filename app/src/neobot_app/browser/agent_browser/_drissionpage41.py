"""DrissionPage 4.1 的重启连接兼容：同步 CDP 地址并回收失败的缓存对象。"""

from __future__ import annotations

import logging
from functools import wraps
from urllib.parse import urlsplit


def install_restart_fix() -> None:
    """仅在仍有该缺陷的 4.1 系列安装兼容层，不修改第三方包文件。"""
    import DrissionPage
    from DrissionPage._base.chromium import Chromium
    from DrissionPage._base.driver import BrowserDriver

    if not DrissionPage.__version__.startswith("4.1."):
        return
    if getattr(BrowserDriver.__init__, "_neobot_restart_fix", False):
        return

    driver_init = BrowserDriver.__init__
    browser_init = Chromium.__init__
    logger = logging.getLogger("neobot.browser")

    def discard_driver(driver) -> None:
        """只清理本次构造留下的驱动，保留其它浏览器连接。"""
        for key, cached in list(BrowserDriver.BROWSERS.items()):
            if cached is driver:
                BrowserDriver.BROWSERS.pop(key, None)
        try:
            driver.stop()
        except Exception as exc:
            logger.debug("回收初始化失败的浏览器驱动: %s", exc)
        finally:
            driver.is_running = False

    @wraps(driver_init)
    def init_driver(driver, browser_id, address, owner):
        # 上游重启分支只更新 owner.id，仍传入旧 browser id 的 WebSocket 地址。
        # 保留协议、主机、端口和查询串，只同步本地浏览器端点的 id。
        endpoint = urlsplit(address)
        if not owner._ws_only and endpoint.path.startswith("/devtools/browser/"):
            address = endpoint._replace(path=f"/devtools/browser/{browser_id}").geturl()
            owner._ws_address = address
        try:
            driver_init(driver, browser_id, address, owner)
        except Exception:
            discard_driver(driver)
            raise

    @wraps(browser_init)
    def init_browser(browser, *args, **kwargs):
        previous_id = browser.id
        try:
            browser_init(browser, *args, **kwargs)
        except Exception:
            # __new__ 在 __init__ 完成前就缓存对象；失败后必须移除，否则下次
            # 构造会因 _created 标记跳过初始化，拿到 _ws=None 的半成品。
            for key, cached in list(Chromium._BROWSERS.items()):
                if cached is browser:
                    Chromium._BROWSERS.pop(key, None)
            for driver in list(BrowserDriver.BROWSERS.values()):
                if getattr(driver, "owner", None) is browser:
                    discard_driver(driver)
            raise
        if previous_id != browser.id:
            if Chromium._BROWSERS.get(previous_id) is browser:
                Chromium._BROWSERS.pop(previous_id, None)
            previous_driver = BrowserDriver.BROWSERS.get(previous_id)
            if previous_driver is not None and previous_driver.owner is browser:
                discard_driver(previous_driver)
            Chromium._BROWSERS[browser.id] = browser

    init_driver._neobot_restart_fix = True
    BrowserDriver.__init__ = init_driver
    Chromium.__init__ = init_browser
