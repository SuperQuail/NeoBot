# WillingManager

请把自定义回复意愿管理器放在运行时 `data/Willing/` 目录下。

配置文件中：

```toml
[willing]
manager_name = "Quail"
observe_window = 5
```

- `manager_name = "Quail"` 时，使用默认内置鹌鹑意愿生成器。
- 如果要使用自定义意愿管理器，把 `manager_name` 改成对应文件名。
- 例如放入 `data/Willing/MyManager.py`，配置里填写 `manager_name = "MyManager"`。

自定义管理器文件需要导出一个名为 `WillingManager` 的类，并提供 `evaluate(context)` 方法。

示例：

```python
from neobot_app.willing import BaseWillingManager, WillingDecision


class WillingManager(BaseWillingManager):
    name = "MyManager"

    def evaluate(self, context):
        probability = 0.9 if context.mentioned_bot else 0.2
        import random
        return WillingDecision(
            manager_name=self.name,
            probability=probability,
            should_reply=random.random() < probability,
            reasons=("custom_manager",),
        )
```

`context.observed_messages_text` 会提供“仔细观察窗口”内最后几条消息的文本结果，方便直接按窗口内容实现自己的逻辑。
