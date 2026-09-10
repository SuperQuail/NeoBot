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
```

The fallback route is always `models.vision_model`; no fallback model slot has
to be selected by hand. Existing configurations keep the text-only behavior
(`ModelRegistration.native_vision = false`).

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

Degradation is persistent for the provider instance. Two modes:

- **vision-capable fallback** (default when the fallback declares
  `native_vision=True`, i.e. `models.vision_model`): messages and tools pass
  through unchanged, so the fallback still sees the images; logs at **warning**
  level and `provider.native_vision` stays `True`;
- **text-only fallback** (`strip_images=True`): every fallback request replaces
  image blocks with visible text placeholders, adds a system notice stating the
  model did not see the images, removes `image_context__*` tools, and logs at
  **error** level.

Input messages are never mutated. The agent receives structured metadata:

```python
provider.native_vision  # active route capability (True with a vision fallback)
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
