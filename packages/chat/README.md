# neobot-chat

## Main-model native vision

Native image support is explicit and defaults off; merely selecting a model name
never enables it. Example application configuration:

```toml
[models.primary_chat_model]
provider = "DeepSeek"
model_name = "deepseek-v4-flash-vision-exp"
native_vision = true

[agent_model]
main_agent = 0
main_agent_vision_fallback = 1

[models.agent_model_1]
provider = "DeepSeek"
model_name = "deepseek-v4-flash"
native_vision = false
```

`main_agent_vision_fallback` is a model slot (0–3), must differ from `main_agent`,
and must reference a non-vision model with valid credentials. It is only used
when native vision is enabled on the routed main model. Existing configurations
keep the text-only behavior (`ModelRegistration.native_vision = false`).

`RegisteredModel.native_vision` is propagated to DeepSeek/OpenAI/Anthropic
providers. `build_main_provider` wraps the visual main provider in
`NativeVisionFallbackProvider`; its read-only `native_vision` and `model`
properties always describe the active route. A provider/configuration reload
creates a fresh instance and re-enables the configured visual route.

### Images and fallback

The shared message format uses user-role content arrays with text and
`{"type": "image_url", "image_url": {"url": "https://... or data:image/...;base64,..."}}`.
DeepSeek requires user-role images. OpenAI-compatible providers retain image
blocks, and Anthropic converts URL/base64 blocks to its native `image.source`
format, including images nested inside tool results. The chat layer does not
upload images through a Files API.

A visual request is retried on the configured text provider **only** for an
explicit HTTP 400/422 image-capability rejection (including content-array
incompatibility) or a typed local `NativeVisionUnsupportedError`. Invalid image
URLs/data, size limits, generic validation failures, authentication errors,
rate limits, transport failures, and server errors do not cause degradation.
Streaming can retry only before any output has been emitted.

Degradation is persistent for the provider instance and logs at **error** level.
Every subsequent fallback request replaces image blocks with visible text
placeholders and adds a system notice stating the model did not see the images.
Image-mounting tools (`image_context__*`) are removed from fallback requests.
Input messages are not mutated. The agent receives structured metadata:

```python
provider.native_vision  # False after fallback
provider.vision_degradation  # reason/from_model/to_model/notice, or None
response["extensions"]["native_vision_fallback"]  # same metadata on fallback responses
```

Agents should refresh their dynamically available tools after this signal and
use a separate image-parsing tool when visual evidence is still needed; they
must not claim the text-only model viewed omitted images. Configuration-time
failure to create the visual provider also selects the configured fallback with
an explicit error and the same metadata. An invalid or unavailable fallback
route is a startup configuration error, not an implicit model selection.

DeepSeek protocol reference: <https://api-docs.deepseek.com/zh-cn/guides/vision>.
