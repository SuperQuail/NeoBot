"""从初始表单到保存结果的合成演示，不读取运行配置或调用保存接口。"""

from neobot_modloader import Plugin


def register_config_form_guide(plugin: Plugin) -> None:
    text_values = {"user_agent": "NeoBot tutorial/1.0", "cookie": ""}
    interval_values = {**text_values, "poll_interval_seconds": 30}
    final_values = {**interval_values, "default_ai_reply_live": False}
    plugin.guide(
        "config-form-basics",
        title="从零填写配置",
        steps=[
            {
                "chapter": "打开初始表单",
                "target": "config",
                "form": "start",
                "text": "在插件管理选择 streaming_parser，再打开配置表单。初始表单带有安全默认值，文本与凭据可以留空；不是把每个字段都删空。本演示始终使用合成配置，不读取你的真实配置。",
                "example": {},
            },
            {
                "chapter": "填写文本",
                "target": "config.user_agent",
                "form": "edit",
                "text": "先填写一个文本字段。这里用 NeoBot tutorial/1.0 演示浏览器标识；实际不需要定制时可以留空。Cookie 是只写凭据，教程不会填写或展示真实值。",
                "example": text_values,
            },
            {
                "chapter": "填写检查间隔",
                "target": "config.poll_interval_seconds",
                "form": "edit",
                "text": "接着把检查间隔设为 30 秒。上一步的文本仍保留在同一张样例表单里；数字输入有范围限制，单位是秒。",
                "example": interval_values,
            },
            {
                "chapter": "选择默认行为",
                "target": "config.default_ai_reply_live",
                "form": "edit",
                "text": "关闭默认开播 AI 回复，表示新群默认只接收卡片，不额外请求 AI。这是全局默认，不会覆盖已经保存的群设置；其他默认值可以先保持不变。",
                "example": final_values,
            },
            {
                "chapter": "查看校验错误",
                "target": "config.poll_interval_seconds",
                "form": "validate",
                "text": "如果误填为 10 秒，校验会指出它小于最小值 15。此时不能继续保存；不要靠切到 TOML 绕开校验，真实保存仍会由服务端校验。",
                "example": {**final_values, "poll_interval_seconds": 10},
            },
            {
                "chapter": "修正后检查",
                "target": "config.poll_interval_seconds",
                "form": "edit",
                "text": "把检查间隔改回 30 秒。文本和开关保持之前的输入，只修正有问题的字段。",
                "example": final_values,
            },
            {
                "chapter": "确认配置有效",
                "target": "config",
                "form": "validate",
                "text": "核对全部字段及其单位，再检查样例校验结果。这里的校验仅用于演示，真实保存时还会进行服务端模型校验和版本冲突检查。",
                "example": final_values,
            },
            {
                "chapter": "保存配置",
                "target": "config",
                "form": "save",
                "text": "确认后使用底部保存并重载。舞台展示的是保存动作，不会向真实配置接口发送请求，也不会替你重启进程。",
                "example": final_values,
            },
            {
                "chapter": "确认保存与生效",
                "target": "config",
                "form": "saved",
                "text": "演示结束后返回真实配置表单再操作。保存成功不等于所有配置立即生效：该插件的全局配置需要重启 NeoBot，请查看全局通知中的实际结果；插件页面里的群设置和订阅操作则即时生效。",
                "example": final_values,
            },
        ],
    )
