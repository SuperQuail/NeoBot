"""init 子命令：资源索引重建、推理引擎与 VC++ 运行库自检（由 cli.py 拆分）。"""

from __future__ import annotations

import argparse

from typing import Any

from neobot_app.config.loader.manager import ConfigLoadError


def _init_scanned_zero(reports: list) -> bool:
    """init 输出中是否没有任何模型被扫描到(用于提示放模型)。"""
    for entry in reports:
        report = entry.get("report")
        if report is None:
            continue
        if getattr(report, "scanned", 0) > 0:
            return False
    return True


def _uv_python_install_cmd(package: str) -> list[str]:
    """生成安装命令:部署环境均为 uv 管理(venv 内无 pip),优先 uv,回退 python -m pip。"""
    import shutil
    import sys

    if shutil.which("uv"):
        return ["uv", "pip", "install", "--python", sys.executable, package]
    return [sys.executable, "-m", "pip", "install", package]


def _install_ultralytics() -> bool:
    """在当前 Python 环境安装 ultralytics(PyTorch 备选推理栈)。"""
    import subprocess

    cmd = _uv_python_install_cmd("ultralytics")
    print(f"执行: {' '.join(cmd)}")
    print("(下载约 200MB+,视网络状况可能需要数分钟)")
    try:
        result = subprocess.run(cmd)
        return result.returncode == 0
    except OSError as exc:
        print(f"安装失败: {exc}")
        return False


def _ask_install_ultralytics() -> bool:
    """询问用户是否安装 ultralytics;非交互环境(EOF)默认不装。"""
    try:
        answer = input("是否现在安装 ultralytics(PyTorch 备选推理栈,约 200MB+)? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("(非交互环境,跳过安装)")
        return False
    return answer in ("y", "yes")


def _ensure_vision_engine(service: Any) -> None:
    """init 时的推理引擎检查:onnx 可用则无需 torch;不可用则按需安装。

    策略:
    1. onnxruntime 不可用且是 Windows:优先检测 VC++ 运行库(1114 最常见根因),
       询问用户在线下载安装,修好后重新探测 onnxruntime
    2. 仍不可用:询问安装 ultralytics(PyTorch 备选推理栈,.pt 模型)
    3. 安装尝试后无论成败都会重新探测:依赖已就绪(如已手动安装)也能正确识别;
       探测失败会给出具体导入错误,区分「未安装」与「已装但无法加载」。
    """
    if service.onnx_available:
        print("推理引擎: onnxruntime 可用(无需安装 PyTorch 备选栈)")
        print()
        return
    onnx_error = service.engine_error("onnx")
    print("推理引擎: onnxruntime 不可用")
    print(f"         {onnx_error or '未知原因'}")
    # cli 门面维护 VC++ 运行库修复（测试按 cli.* 打补丁），经门面调用保持同一实现与补丁语义。
    from neobot_app import cli

    if cli._ensure_vc_runtime_fixed():
        service.reset_availability()
        if service.onnx_available:
            print("推理引擎: 修复 VC++ 运行库后 onnxruntime 已可用")
            print()
            return
    if service.torch_available:
        print("         .onnx 无法运行;PyTorch(ultralytics) 已安装,.pt 模型可用")
        print("         (如需修复 onnxruntime 请检查 CPU 指令集透传与 VC++ 运行库)")
        print()
        return
    torch_error = service.engine_error("torch")
    print("         .onnx 模型无法运行,备选方案为 PyTorch 推理栈(.pt 模型)")
    if torch_error:
        print(f"         PyTorch 检测失败: {torch_error}")
        print("         提示: 包已安装但仍无法导入,多为 CPU 指令集未透传/运行库缺失,"
              "PyTorch 也可能无法运行")
        print("         可手动验证: 直接 import torch 查看具体报错")
    else:
        print("         未检测到 ultralytics(未安装)")
        if _ask_install_ultralytics():
            _install_ultralytics()
            service.reset_availability()
            if service.torch_available:
                print("就绪: PyTorch 备选推理栈已可用,放入 .pt 模型后重跑 neobot init")
            else:
                after_error = service.engine_error("torch")
                print(f"安装后仍不可用: {after_error or '未知原因'}")
                print("         可稍后手动执行: "
                      f"{' '.join(_uv_python_install_cmd('ultralytics'))}")
        else:
            print(f"        跳过安装。手动安装命令: "
                  f"{' '.join(_uv_python_install_cmd('ultralytics'))}")
            print("        安装后重新运行 neobot init 即可生效")
    print()


def cmd_init(args: argparse.Namespace) -> None:
    """重新扫描并建立所有可再生的资源索引(不启动 Bot)。"""
    from neobot_app.bootstrap._config import build_config
    from neobot_app.bootstrap._services import resolve_vision_detect_paths
    from neobot_app.core import DATA_DIR
    from neobot_app.indexer import IndexRunner, IndexTask
    from neobot_app.vision_detect.service import VisionDetectService

    print("neobot init — 扫描并建立资源索引…")
    print()
    config = None
    try:
        config = build_config()
    except ConfigLoadError as exc:
        print(f"配置加载失败：\n{exc}")
        print("已降级: 使用默认路径重建模型索引(视觉检测配置未读取)。")
        print()

    runner = IndexRunner()
    vision_cfg = getattr(getattr(config, "agent", None), "vision_detect", None) if config is not None else None
    if vision_cfg is not None and not vision_cfg.enabled:
        print("视觉检测配置未启用 (agent.vision_detect.enabled = false)，跳过")
        print()
    elif config is not None:
        models_dir, index_file = resolve_vision_detect_paths(config=config, data_dir=DATA_DIR)
        service = VisionDetectService(
            models_dir,
            index_file,
            default_conf=vision_cfg.default_conf,
            default_iou=vision_cfg.default_iou,
            imgsz=vision_cfg.imgsz,
            auto_refresh=vision_cfg.auto_refresh,
        )
        _ensure_vision_engine(service)
        runner.register(
            IndexTask(
                name="vision_detect",
                description="扫描模型目录(.onnx/.pt)并维护 models.toml 索引",
                scan=service.refresh,
            )
        )
    else:
        # 配置加载失败:降级为默认路径,仅重建模型索引
        from neobot_app.config.schemas.bot import VisionDetect as _DefaultVisionDetect

        defaults = _DefaultVisionDetect()
        models_dir = DATA_DIR / "vision_detect" / "models"
        index_file = DATA_DIR / "vision_detect" / "models.toml"
        service = VisionDetectService(
            models_dir,
            index_file,
            default_conf=defaults.default_conf,
            default_iou=defaults.default_iou,
            imgsz=defaults.imgsz,
            auto_refresh=defaults.auto_refresh,
        )
        _ensure_vision_engine(service)
        runner.register(
            IndexTask(
                name="vision_detect",
                description="扫描模型目录(.onnx/.pt)并维护 models.toml 索引(默认路径)",
                scan=service.refresh,
            )
        )

    print(runner.describe())
    print()
    reports = runner.run_sync(force=args.force)
    for entry in reports:
        if entry.get("skipped"):
            print(f"[{entry['task']}] 跳过(异步任务,请通过 bot 启动时执行)")
            continue
        if entry.get("error"):
            print(f"[{entry['task']}] 扫描失败: {entry['error']}")
            continue
        report = entry["report"]
        print(f"── {entry['task']}: {entry['description']} ──")
        summary = getattr(report, "summary", None)
        print(summary() if callable(summary) else str(report))
        print()
    if _init_scanned_zero(reports):
        print(f"未发现 .onnx / .pt 模型文件: 请将模型放入 {models_dir} 后重新运行 neobot init")
    else:
        print("完成。编辑模型索引(models.toml)填写模型描述后即可生效"
              "(无需重启;若关闭了自动刷新 auto_refresh 则需重启)。")
