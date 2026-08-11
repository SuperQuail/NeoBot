"""cache/calculator 模块测试:字符级缓存命中计算与成本估算。"""

from neobot_app.cache import (
    CacheCalculator,
    serialize_messages,
    serialize_response_text,
)


def _msg(role: str, content: str) -> dict:
    return {"role": role, "content": content}


def _now_fn(clock: list[float]):
    return lambda: clock[0]


class TestSerialize:
    def test_serialize_messages_deterministic(self):
        messages = [
            _msg("system", "你是一位助手"),
            _msg("user", "你好"),
            _msg("assistant", "你好呀"),
        ]
        text = serialize_messages(messages)
        assert text == "<system>你是一位助手<user>你好<assistant>你好呀"
        assert serialize_messages(list(reversed(messages))) != text

    def test_serialize_tool_calls(self):
        messages = [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "demo__ping", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "name": "demo__ping", "content": "pong"},
        ]
        text = serialize_messages(messages)
        assert "calls:demo__ping({})" in text
        assert "<tool>pong" in text

    def test_serialize_response(self):
        """响应序列化必须与历史中同一消息的序列化完全一致(前缀可匹配)。"""
        response = {
            "content": "好的",
            "tool_calls": [
                {"function": {"name": "demo__ping", "arguments": '{"x":1}'}}
            ],
        }
        # 真实 provider 响应无 role 键:两侧按同一规则(无标签)序列化
        text = serialize_response_text(response)
        assert text == "<>好的"
        assert serialize_messages([response]) == text
        # 带 role 的响应:与历史中 assistant 消息格式一致
        resp_role = {"role": "assistant", "content": "好的"}
        assert serialize_response_text(resp_role) == "<assistant>好的"
        assert serialize_messages([resp_role]) == serialize_response_text(resp_role)
        # 纯 tool_calls 响应:与历史中 tool_calls 消息格式一致
        resp_calls = {
            "content": None,
            "tool_calls": [{"function": {"name": "demo__ping", "arguments": "{}"}}],
        }
        text2 = serialize_response_text(resp_calls)
        assert text2 == "<>calls:demo__ping({})"
        assert serialize_messages([resp_calls]) == text2

    def test_serialize_escapes_content_angle_brackets(self):
        """内容中的 '<' 必须转义,防止内容伪装角色标签造成假命中。"""
        a = serialize_messages([{"role": "user", "content": "hello<assistant>world"}])
        b = serialize_messages(
            [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "world"}]
        )
        assert a != b
        # 字面控制符也必须被转义:内容含 \x1c 时不与转义结果混淆(单射)
        c = serialize_messages(
            [{"role": "user", "content": "hello\x1c<assistant\x1c>world"}]
        )
        assert a != c


class TestRequestEndHit:
    """例一:多轮对话。第二轮能完整复用第一轮的缓存前缀单元。"""

    def test_second_round_hits_first_round(self):
        calc = CacheCalculator()
        req1 = serialize_messages(
            [{"role": "system", "content": "你是一位乐于助人的助手" * 3},
             {"role": "user", "content": "中国的首都是哪里？"}]
        )
        req2 = serialize_messages(
            [{"role": "system", "content": "你是一位乐于助人的助手" * 3},
             {"role": "user", "content": "中国的首都是哪里？"},
             {"role": "assistant", "content": "中国的首都是北京。"},
             {"role": "user", "content": "美国的首都是哪里？"}]
        )
        first = calc.record("m", req1, output_text="中国的首都是北京。")
        assert first.hit_chars == 0

        second = calc.record("m", req2, output_text="美国的首都是华盛顿。")
        assert second.hit_chars == len(req1), (second.hit_chars, len(req1))
        assert second.hit_unit == "request_end_user"
        assert second.miss_chars == len(req2) - len(req1)

    def test_providers_isolated(self):
        calc = CacheCalculator()
        req1 = serialize_messages([{"role": "user", "content": "A" * 100}])
        calc.record("provider_a", req1)
        req2 = serialize_messages([{"role": "user", "content": "A" * 100 + "B"}])
        hit = calc.hit_chars_for("provider_b", req2)
        assert hit == 0


class TestCommonPrefix:
    """例二:公共前缀落盘。A+B、A+C 后,A 落盘;A+D 命中 A。"""

    def _build(self):
        calc = CacheCalculator()
        base = "你是一位资深的财报分析师，请仔细分析以下内容。"
        # 正文控制在固定间隔(512字符)以下,避免 interval 单元干扰公共前缀验证
        doc = "这是一段很长的财报内容。" * 30
        req1 = serialize_messages([{"role": "system", "content": base},
                                   {"role": "user", "content": doc + "\n请总结一下关键信息。"}])
        req2 = serialize_messages([{"role": "system", "content": base},
                                   {"role": "user", "content": doc + "\n请分析一下盈利情况。"}])
        req3 = serialize_messages([{"role": "system", "content": base},
                                   {"role": "user", "content": doc + "\n请分析收入与支出占比。"}])
        return calc, req1, req2, req3

    def test_common_prefix_unit_disked_and_hit(self):
        calc, req1, req2, req3 = self._build()
        calc.record("m", req1)
        second = calc.record("m", req2)
        # 前两轮不能完整匹配对方(公共前缀 < 完整请求)
        assert second.hit_chars == 0
        summary = calc.summary("m")
        assert summary["units_by_source"].get("common_prefix", 0) == 1

        third = calc.record("m", req3)
        assert third.hit_chars >= 32
        assert third.hit_unit == "common_prefix"
        # 公共前缀单元就是系统消息+财报正文(不含提问尾巴)
        assert third.hit_chars < len(req3)


class TestInterval:
    def test_interval_units_cover_long_input(self):
        calc = CacheCalculator()
        long_text = "长" * 3000
        req1 = serialize_messages([{"role": "user", "content": long_text + "第一问"}])
        req2 = serialize_messages([{"role": "user", "content": long_text + "第二问"}])
        calc.record("m", req1)
        summary = calc.summary("m")
        # 3000+ 字符 > 2*512 间隔 -> 至少 2 个 interval 单元
        assert summary["units_by_source"].get("interval", 0) >= 2

        hit = calc.hit_chars_for("m", req2)
        # 第二问与第一问共享长前缀,命中某个间隔单元(至少一个完整间隔)
        assert hit >= 512
        # 未命中提问尾巴差异部分
        assert hit < len(req2)

    def test_interval_units_on_long_output(self):
        calc = CacheCalculator()
        input_text = serialize_messages([{"role": "user", "content": "写一篇长文"}])
        output = "字" * 2000
        calc.record("m", input_text, output_text=output)
        summary = calc.summary("m")
        assert summary["units_by_source"].get("interval", 0) >= 2
        assert summary["units_by_source"].get("request_end_output", 0) == 1


class TestExpiry:
    def test_units_expire_after_retention(self):
        clock = [1000.0]
        calc = CacheCalculator(retention_seconds=1800, now_fn=_now_fn(clock))
        req1 = serialize_messages([{"role": "user", "content": "今天天气怎么样" * 10}])
        req2 = serialize_messages([{"role": "user", "content": "今天天气怎么样" * 10 + "明天呢"}])
        calc.record("m", req1)
        assert calc.hit_chars_for("m", req2) == len(req1)

        clock[0] += 1801
        assert calc.hit_chars_for("m", req2) == 0

    def test_expired_units_pruned_on_record(self):
        clock = [0.0]
        calc = CacheCalculator(retention_seconds=100, now_fn=_now_fn(clock))
        req1 = serialize_messages([{"role": "user", "content": "第一轮内容" * 20}])
        req2 = serialize_messages([{"role": "user", "content": "第二轮内容" * 20}])
        calc.record("m", req1)
        clock[0] = 200
        calc.record("m", req2)
        summary = calc.summary("m")
        # 过期单元已被清理
        assert all(
            u.expires_at > 200
            for u in calc._units["m"]
        )
        assert summary["units_by_source"].get("request_end_user", 0) == 1


class TestCostEstimate:
    def test_cost_math_with_price_difference(self):
        calc = CacheCalculator(price_difference=120)
        req1 = serialize_messages([{"role": "user", "content": "A" * 2400}])
        req2 = serialize_messages([{"role": "user", "content": "A" * 2400 + "B" * 100}])
        calc.record("m", req1)
        estimate = calc.estimate_cost("m", req2)
        assert estimate.hit_chars == len(req1)
        assert estimate.miss_chars == 100
        assert estimate.total_chars == len(req2)
        assert estimate.cost == 100 + len(req1) / 120
        assert estimate.cheaper_than_full_miss()

    def test_no_cache_means_not_cheaper(self):
        calc = CacheCalculator(price_difference=120)
        text = serialize_messages([{"role": "user", "content": "全新内容" * 30}])
        estimate = calc.estimate_cost("m", text)
        assert estimate.hit_chars == 0
        assert not estimate.cheaper_than_full_miss()
        assert estimate.cost == estimate.total_chars


class TestMemoryBounds:
    def test_units_trimmed_to_limit(self):
        calc = CacheCalculator()
        for i in range(30):
            text = serialize_messages([{"role": "user", "content": f"内容{i}:" + "字" * 200}])
            calc.record("m", text, output_text="回答" * 20)
        summary = calc.summary("m")
        from neobot_app.cache import MAX_UNITS_PER_PROVIDER

        assert summary["units"] <= MAX_UNITS_PER_PROVIDER


class TestDuplicateUnits:
    def test_same_request_does_not_duplicate_units(self):
        calc = CacheCalculator()
        req = serialize_messages([{"role": "user", "content": "重复请求" * 30}])
        calc.record("m", req)
        calc.record("m", req)
        summary = calc.summary("m")
        assert summary["units_by_source"].get("request_end_user", 0) == 1
