from __future__ import annotations

import random

from neobot_app.willing.models import BaseWillingManager, WillingContext, WillingDecision


def clamp_probability(value: float) -> float:
    return max(0.0, min(1.0, value))


class QuailWillingManager(BaseWillingManager):
    name = "Quail"

    def evaluate(self, context: WillingContext) -> WillingDecision:
        reasons: list[str] = []

        if not context.is_allowed:
            reasons.append(f"blocked: {context.block_reason}")
            return WillingDecision(
                manager_name=self.name,
                probability=0.0,
                should_reply=False,
                reasons=tuple(reasons),
            )

        blocked = self._is_runtime_blocked(context)
        if blocked:
            reasons.append("runtime_blacklist: blocked")
            return WillingDecision(
                manager_name=self.name,
                probability=0.0,
                should_reply=False,
                reasons=tuple(reasons),
            )

        # 私聊：百分百回复，不受任何系数影响
        if context.is_direct_message:
            reasons.append("private_chat_guaranteed")
            return WillingDecision(
                manager_name=self.name,
                probability=1.0,
                should_reply=True,
                reasons=tuple(reasons),
            )

        if context.at_guaranteed_reply and context.mentioned_bot:
            reasons.append("at_guaranteed_reply: mentioned_bot")
            return WillingDecision(
                manager_name=self.name,
                probability=1.0,
                should_reply=True,
                reasons=tuple(reasons),
            )

        # ── 基础概率：0.5 起点（正态分布均值）──
        probability = 0.5
        reasons.append("起始概率=0.500")

        # ── 仅保留问句加成 ──
        if context.has_question:
            probability += 0.15
            reasons.append("问句加成=+0.150")

        reasons.append(f"加成后={probability:.3f}")

        # ── 乘法系数 ──
        probability *= context.config_global_coefficient
        reasons.append(f"全局系数={context.config_global_coefficient:.3f}")
        probability *= context.conversation_coefficient
        reasons.append(f"会话系数={context.conversation_coefficient:.3f}")

        if context.runtime_config is not None:
            runtime = context.runtime_config
            probability *= runtime.global_coefficient
            reasons.append(f"运行时系数={runtime.global_coefficient:.3f}")
            runtime_conv_coeff = runtime.conversation_coefficients.get(
                context.conversation_id, 1.0
            )
            probability *= runtime_conv_coeff
            if runtime_conv_coeff != 1.0:
                reasons.append(f"运行时会话系数={runtime_conv_coeff:.3f}")
            runtime_user_coeff = runtime.user_global_coefficients.get(
                context.sender_id, 1.0
            )
            probability *= runtime_user_coeff
            if runtime_user_coeff != 1.0:
                reasons.append(f"运行时用户全局系数={runtime_user_coeff:.3f}")
            runtime_conv_user_coeff = runtime.conversation_user_coefficients.get(
                context.conversation_id, {}
            ).get(context.sender_id, 1.0)
            probability *= runtime_conv_user_coeff
            if runtime_conv_user_coeff != 1.0:
                reasons.append(f"运行时会话用户系数={runtime_conv_user_coeff:.3f}")

        if context.is_official_bot:
            probability *= context.official_bot_coefficient
            reasons.append(f"官方Bot系数={context.official_bot_coefficient:.3f}")

        probability = clamp_probability(probability)
        should_reply = random.random() < probability
        reasons.append(f"最终概率={probability:.3f}")
        return WillingDecision(
            manager_name=self.name,
            probability=probability,
            should_reply=should_reply,
            reasons=tuple(reasons),
        )

    @staticmethod
    def _is_runtime_blocked(context: WillingContext) -> bool:
        if context.runtime_config is None:
            return False
        return context.conversation_id in context.runtime_config.blacklisted_conversations
