---
type: fix
scope: modloader
packages:
  python@neobot-modloader: patch
  python@neobot-app: patch
---

插件下载器原先只信系统证书库，而宿主其它请求走 httpx（只信 certifi），两套根证书不一致；Windows 证书库缺根证书时，安装/更新插件会报 `CERTIFICATE_VERIFY_FAILED`，其它功能却一切正常。现在下载器在系统证书库之外叠加 certifi 根证书，证书校验失败的报错也带上 `SSL_CERT_FILE` / 代理的设置提示；面板「检查更新」在全部检查都失败时不再显示「全部插件均为最新」，改为报告失败数量与首个错误。
