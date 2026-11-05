"""作者明确声明的业务失败应能指导用户，不回显未知异常。"""

import pytest

from neobot_modloader import ActionError, ActionInvocation, Plugin


async def test_declared_business_error_reaches_the_caller():
    plugin = Plugin("business_errors")

    @plugin.action("subscribe")
    async def subscribe(values, invocation):
        raise ActionError("group_unavailable", "机器人尚未加入该群，请重新选择接收群")

    with pytest.raises(ActionError) as error:
        await plugin.surface.invoke(plugin, "subscribe", {}, ActionInvocation("test", frozenset({"manage"})))
    assert error.value.code == "group_unavailable"
    assert error.value.message == "机器人尚未加入该群，请重新选择接收群"


async def test_unexpected_handler_error_remains_private():
    plugin = Plugin("business_errors")

    @plugin.action("subscribe")
    def subscribe(values, invocation):
        raise RuntimeError("synthetic-private-business-input")

    with pytest.raises(ActionError) as error:
        await plugin.surface.invoke(plugin, "subscribe", {}, ActionInvocation("test", frozenset({"manage"})))
    assert error.value.code == "action_failed"
    assert "synthetic-private-business-input" not in str(error.value.to_dict())
