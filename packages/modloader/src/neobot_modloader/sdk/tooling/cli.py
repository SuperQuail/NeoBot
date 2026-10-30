"""本地与 CI 共用的插件工具命令。"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import sys
from pathlib import Path

from .archive import build_package
from .models import ToolReport
from .project import export_contract, init_project
from .smoke import smoke_package
from .validation import check_project


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NeoBot 插件工程、静态契约、打包与安装验收工具")
    parser.add_argument("--json", action="store_true", help="输出机器可读报告")
    commands = parser.add_subparsers(dest="command", required=True)
    descriptions = {
        "init": "创建带配置、命令、说明书和测试的入门工程",
        "export": "导入作者代码，导出公开契约或检查差异",
        "check": "静态检查工程与契约，不执行插件入口",
        "build": "将已检查的工程打包为 ZIP",
        "smoke": "离线安装最终 ZIP 并检查生命周期",
        "upgrade": "停止宿主后迁移插件代码和数据",
    }
    for name, description in descriptions.items():
        command = commands.add_parser(name, help=description, description=description)
        command.add_argument("path", type=Path, help="插件工程目录；smoke/upgrade 使用最终 ZIP")
        command.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
        if name == "init":
            command.add_argument("--name", required=True, help="插件机器名，建议使用 hello_plugin 等简短名称")
            command.add_argument("--template", type=Path, help="独立模板仓库的本地目录")
        elif name == "export":
            command.add_argument("--check", action="store_true", help="导入代码并比较现有契约，不写入文件")
        elif name == "build":
            command.add_argument("--output", required=True, type=Path)
        elif name == "smoke":
            command.add_argument("--config", type=Path, help="可选的合成 TOML 配置样例")
            command.add_argument("--timeout", type=float, default=30.0)
        elif name == "upgrade":
            command.add_argument("--plugin-dir", type=Path, required=True)
            command.add_argument("--data-dir", type=Path, required=True)
            command.add_argument("--name", required=True)
            command.add_argument(
                "--builtin-dir",
                action="append",
                type=Path,
                default=[],
                help="官方前置插件目录，可重复指定；只启动目标的前置闭包",
            )
            command.add_argument("--timeout", type=float, default=30.0)
    return parser


def _run(arguments: argparse.Namespace) -> ToolReport:
    if arguments.command == "init":
        return init_project(arguments.path, arguments.name, template=arguments.template)
    if arguments.command == "export":
        return export_contract(arguments.path, check=arguments.check)
    if arguments.command == "check":
        return check_project(arguments.path)
    if arguments.command == "build":
        return build_package(arguments.path, arguments.output)
    if arguments.command == "upgrade":
        from .upgrade import upgrade_package

        return asyncio.run(
            upgrade_package(
                arguments.path,
                plugin_dir=arguments.plugin_dir,
                data_dir=arguments.data_dir,
                name=arguments.name,
                timeout=arguments.timeout,
                builtin_plugin_dirs=tuple(arguments.builtin_dir),
            )
        )
    return asyncio.run(smoke_package(arguments.path, config=arguments.config, timeout=arguments.timeout))


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    # 包中的 print 不得污染 JSON；stderr 仍可供作者查看导入或运行阶段日志。
    with contextlib.redirect_stdout(sys.stderr):
        report = _run(arguments)
    if arguments.json:
        print(json.dumps(report.to_dict(), ensure_ascii=True, allow_nan=False))
    else:
        print(f"{report.command}: {'通过' if report.ok else '失败'}")
        for error in report.errors:
            print(f"- {error}")
        if report.path:
            print(report.path)
        if report.sha256:
            print(f"sha256: {report.sha256}")
        if report.ok and report.command == "init":
            print("下一步：进入工程，按 README.md 同步宿主环境、验收并打开隔离面板。")
            print("交给开发助手前先阅读 AGENTS.md；修改教程时参考 GUIDE.md。")
    return 0 if report.ok else 1
