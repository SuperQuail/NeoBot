"""发言日程显式声明实际使用的宿主服务。"""

from tests.modules.builtin_plugins.test_speaking_schedule_runtime import runtime as runtime


async def test_schedule_reports_real_host_policy(runtime):
    rt, policy, _commands = runtime
    result = await rt.set_enabled("speaking_schedule", True)
    assert result.ok, result.error
    snapshot = rt.control.get("speaking_schedule")
    slots = {slot["service"]: slot for slot in snapshot.services}
    assert slots["speaking_policy"]["kind"] == "required"
    assert slots["speaking_policy"]["status"] == "loaded"
    assert slots["speaking_policy"]["provider"] == "__host__"
    assert policy.has_policies


async def test_schedule_missing_policy_is_dependency_block(runtime):
    rt, _policy, _commands = runtime
    rt.host.services.unregister("speaking_policy")
    result = await rt.set_enabled("speaking_schedule", True)
    assert not result.ok
    assert "必需服务" in result.error
    snapshot = rt.control.get("speaking_schedule")
    assert snapshot.auto_disabled
    assert snapshot.dependency_status == "blocked"
    assert rt.control.config_consumer("speaking_schedule") is None
