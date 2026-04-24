from __future__ import annotations

from neobot_app.willing.models import BaseWillingManager, WillingContext, WillingDecision


def clamp_probability(value: float) -> float:
    return max(0.0, min(1.0, value))


class QuailWillingManager(BaseWillingManager):
    name = "Quail"

    def evaluate(self, context: WillingContext) -> WillingDecision:
        reasons: list[str] = [f"base={context.base_probability:.3f}"]

        if not context.is_allowed:
            reasons.append(f"blocked={context.block_reason}")
            return WillingDecision(
                manager_name=self.name,
                probability=0.0,
                should_reply=False,
                reasons=tuple(reasons),
            )

        blocked = self._is_runtime_blocked(context)
        if blocked:
            reasons.append("blocked=runtime_blacklist")
            return WillingDecision(
                manager_name=self.name,
                probability=0.0,
                should_reply=False,
                reasons=tuple(reasons),
            )

        if context.at_guaranteed_reply and context.mentioned_bot:
            reasons.append("at_guaranteed_reply=1.000")
            return WillingDecision(
                manager_name=self.name,
                probability=1.0,
                should_reply=True,
                reasons=tuple(reasons),
            )

        probability = context.base_probability
        probability *= context.config_global_coefficient
        reasons.append(f"config_global_coeff={context.config_global_coefficient:.3f}")
        probability *= context.conversation_coefficient
        reasons.append(f"conversation_coeff={context.conversation_coefficient:.3f}")

        if context.runtime_config is not None:
            runtime = context.runtime_config
            probability *= runtime.global_coefficient
            reasons.append(f"runtime_global_coeff={runtime.global_coefficient:.3f}")
            runtime_conv_coeff = runtime.conversation_coefficients.get(
                context.conversation_id, 1.0
            )
            probability *= runtime_conv_coeff
            if runtime_conv_coeff != 1.0:
                reasons.append(f"runtime_conv_coeff={runtime_conv_coeff:.3f}")

        if context.is_direct_message:
            probability += 0.12
            reasons.append("direct_message_bonus=0.120")

        if context.mentioned_bot:
            probability += 0.30
            reasons.append("mentioned_bot_bonus=0.300")

        if context.called_bot_name:
            probability += 0.20
            reasons.append("called_bot_name_bonus=0.200")

        if context.replied_to_message:
            probability += 0.15
            reasons.append("reply_segment_bonus=0.150")

        if context.has_question:
            probability += 0.10
            reasons.append("question_bonus=0.100")

        if context.matched_keywords:
            keyword_bonus = min(0.08 * len(context.matched_keywords), 0.24)
            probability += keyword_bonus
            reasons.append(f"keywords_bonus={keyword_bonus:.3f}")

        observed_count = len(context.observed_messages_text)
        if observed_count > 0:
            window_bonus = min(0.02 * observed_count, 0.10)
            probability += window_bonus
            reasons.append(f"observe_window_bonus={window_bonus:.3f}")

        if context.text.strip() == "":
            probability -= 0.08
            reasons.append("empty_text_penalty=-0.080")

        probability = clamp_probability(probability)
        reasons.append(f"final={probability:.3f}")
        return WillingDecision(
            manager_name=self.name,
            probability=probability,
            should_reply=probability >= context.reply_threshold,
            reasons=tuple(reasons),
        )

    @staticmethod
    def _is_runtime_blocked(context: WillingContext) -> bool:
        if context.runtime_config is None:
            return False
        return context.conversation_id in context.runtime_config.blacklisted_conversations
