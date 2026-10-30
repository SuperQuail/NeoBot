# __PLUGIN_NAME__

这个工程已经包含可配置的 `/ping`、自动配置表单、完整的思索说明书和离线命令测试。普通插件不需要 Node。

## 第一次跑通

以下命令在当前插件目录执行，假设它与 NeoBot 源码目录同级。目录不同，只需把命令中的 `../NeoBot` 改成实际路径。需要 Python 3.13 或 3.14、uv，以及包含插件 SDK 的 NeoBot 开发仓库；仅复制这个工程不会自动安装 SDK。

```text
NeoBot/
__PLUGIN_NAME__/       ← 当前目录
```

先同步宿主与测试依赖，再运行完整验收：

```sh
uv sync --project ../NeoBot --all-packages --locked
uv run --project ../NeoBot --no-sync python -m neobot_modloader.sdk export .
uv run --project ../NeoBot --no-sync python ../NeoBot/scripts/plugin_ci.py . --output-dir ../__PLUGIN_NAME___acceptance
```

成功标志：命令退出码为 0，报告中的 `ok` 为 `true`，报告目录中有 `report.json`、`pytest.xml` 和 `plugin.zip`。离线测试会实际调用 SDK 注册后的命令，验证回复采用自定义配置；外部 QQ 连接尚未验证。

接着打开隔离面板，直接查看自己的插件：

```sh
uv run --project ../NeoBot --no-sync python ../NeoBot/scripts/plugin_demo.py --sample . --port 19981
```

打开终端显示的地址，用终端显示的演示密码登录。在“插件”中选择 `__PLUGIN_NAME__`，查看“配置表单”和“使用说明”。演示用合成数据，不读取真实配置，不连接 QQ 或付费模型。这个面板没有聊天发送入口；离线命令行为由前面的测试验证。结束时在终端按 Ctrl+C。

## 安装到真实机器人

把当前工程目录放进你部署的 NeoBot 的 `plugins.dir` 目录（默认 `plugins/`），然后重启 NeoBot。到插件管理确认插件正在运行，在配置表单填写回复内容，保存并查看通知中的生效结果。

在机器人私聊发送 `/help`，确认存在本插件的命令，再发送 `/ping`，应收到保存的回复文字。重名时实际名称可能是 `/__PLUGIN_NAME____ping`，以 `/help` 或插件详情为准；群聊使用宿主命令还需要 @机器人。

配置写在宿主 `plugins_data/__PLUGIN_NAME__/config.toml`，不写进插件源码目录。不要把整个 NeoBot 仓库或真实数据目录放进插件包。

## 从这里继续改

| 要做什么 | 修改位置 |
| --- | --- |
| 添加配置 | `__init__.py` 的 `Config`，提供类型、中文标题、说明与约束 |
| 改命令行为 | `ping` 或新增命令；显式填写 `permission` 和 `description` |
| 改使用说明 | `plugin.guide(...)`；编写规则与目标清单见 [GUIDE.md](GUIDE.md) |
| 加业务验证 | `tests/test_plugin.py`；验证真实处理链，外部服务用合成端口 |
| 交给 AI 开发 | 先让它阅读 [AGENTS.md](AGENTS.md)，再填写下方需求 |

修改声明后重新运行 `export`，检查 `plugin.contract.json` 差异，再运行完整验收。契约由工具生成，不手写。

```text
请先阅读 AGENTS.md，再在当前插件中实现：
需求：……
触发命令与输入：……
期望回复或配置效果：……
权限与失败时的表现：……
请同步说明书与业务测试，导出契约并执行验收；报告实际结果和未验证项。
```

## 出错后怎么继续

| 现象 | 下一步 |
| --- | --- |
| 找不到 `neobot_modloader`、Pydantic 或 pytest | 确认使用上面的 `uv run --project ../NeoBot --no-sync`，先完成 `uv sync` |
| 初始化提示目标已存在 | 选择新目录；已有工程直接修改，不重复初始化覆盖 |
| 静态契约已过期 | 重新执行 `export .`，核对差异后再验收 |
| 教程目标失效 | 按报错字段和 GUIDE.md 更新目标，删除配置字段时同步教程 |
| 验收失败 | 打开报告中的 `errors` 和失败阶段的 `.log`，修正后重跑，不跳过失败测试 |
| `/ping` 无回复 | 确认真实机器人已连接、插件已启用，再从 `/help` 核对实际命令名 |
| 保存后回复未变化 | 查看全局通知是否要求重载或重启；确认修改的是实际运行实例 |

完整 API 和页面接入见 NeoBot 的 `docs/07-插件开发.md`、`docs/04-功能文档/插件SDK与工程验收.md`、`docs/04-功能文档/插件设置界面.md`。
