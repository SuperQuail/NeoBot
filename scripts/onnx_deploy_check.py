"""onnx/torch 部署环境诊断与自动修复脚本。

用途:在 NeoBot 部署环境(Stand/服务器/虚拟机)上诊断 onnxruntime
与 PyTorch(ultralytics) DLL 加载失败问题,并自动尝试多种修复路径,
尽可能让视觉检测跑起来。

运行方式(在 Stand 目录):
    uv run python scripts/onnx_deploy_check.py
    或: .venv\\Scripts\\python.exe scripts\\onnx_deploy_check.py

可选参数:
    --try-versions  自动回退尝试多个 onnxruntime 版本(默认开启)
    --install-redist 自动联网下载并安装 VC++ 运行库(需管理员,默认仅提示);
                    下载/安装失败时提示手动下载

DLL 数据包说明:
    VC++ 运行库不再随发布包内置,`--install-redist` 会从微软官方
    (https://aka.ms/vs/17/release/vc_redist.x64.exe)在线下载最新版安装。
    WinError 1114(初始化例程失败)最常见根因是运行库版本过旧(如 14.31=2019 版),
    安装最新版即可覆盖解决;无网环境请手动下载后以管理员运行。
"""

from __future__ import annotations

import ctypes
import os
import platform
import subprocess
import sys
from pathlib import Path

VC_REDIST_URL = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
VERSIONS_TO_TRY = ["1.28.0", "1.24.3", "1.20.1", "1.16.3"]

# 需要检查的 VC++ 运行库(onnxruntime / torch 共同依赖)
VC_DLLS = [
    "vcruntime140.dll",
    "vcruntime140_1.dll",
    "msvcp140.dll",
    "msvcp140_1.dll",
    "msvcp140_2.dll",
    "msvcp140_atomic_wait.dll",
]

# 建议最低版本:VC++ 2015-2022 redist(x64)最新版通常 ≥ 14.40。
# 旧版本(如 14.31 = 2019 版)常导致 DLL 初始化例程失败(WinError 1114)。
VC_MIN_VERSION = (14, 40, 0, 0)


def _parse_version(text: str) -> tuple[int, ...] | None:
    try:
        parts = tuple(int(p) for p in text.split("."))
        return parts if parts else None
    except (TypeError, ValueError):
        return None


def _file_version(path: str) -> str:
    """用 WinAPI 读取文件版本(Path.VersionInfo 不存在,需 ctypes)。"""
    import struct

    try:
        size = ctypes.windll.version.GetFileVersionInfoSizeW(path, None)
        if not size:
            return ""
        buf = ctypes.create_string_buffer(size)
        if not ctypes.windll.version.GetFileVersionInfoW(path, 0, size, buf):
            return ""
        ver_ptr = ctypes.c_void_p()
        ver_size = ctypes.c_uint()
        if not ctypes.windll.version.VerQueryValueW(
            buf, "\\", ctypes.byref(ver_ptr), ctypes.byref(ver_size)
        ):
            return ""
        data = ctypes.string_at(ver_ptr, ver_size.value)
        if len(data) < 16:
            return ""
        ms, ls = struct.unpack_from("<II", data, 8)  # VS_FIXEDFILEINFO 偏移
        return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
    except Exception:
        return ""


def _banner(title: str) -> None:
    print("\n" + "=" * 68)
    print(f" {title}")
    print("=" * 68)


def check_system_info() -> None:
    _banner("1. 系统信息")
    print(f"  OS        : {platform.system()} {platform.release()} ({platform.version()})")
    print(f"  Arch      : {platform.machine()} / {platform.architecture()[0]}")
    print(f"  Python    : {platform.python_version()} ({sys.executable})")
    try:
        import onnxruntime  # noqa: F401
    except Exception as exc:
        print(f"  onnxruntime: 当前无法导入 ({type(exc).__name__})")
    else:
        print(f"  onnxruntime: {onnxruntime.__version__} OK")
    try:
        import torch  # noqa: F401
        import ultralytics  # noqa: F401
    except Exception as exc:
        print(f"  torch/ultralytics: 当前无法导入 ({type(exc).__name__})")
    else:
        print(f"  torch: {torch.__version__} / ultralytics: {ultralytics.__version__} OK")
    # 虚拟化判断
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_Processor).Name + ' | ' + "
                "(Get-CimInstance Win32_ComputerSystem).Model + ' | Hypervisor: ' + "
                "((Get-CimInstance Win32_ComputerSystem).HypervisorPresent)",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        cpu_line = result.stdout.strip()
        if cpu_line:
            print(f"  CPU       : {cpu_line}")
            if "General Purpose Processor" in cpu_line or "Hypervisor: True" in cpu_line:
                print("  ↳ 检测到虚拟化环境:若 DLL 初始化失败,可能为虚拟机未透传 CPU 指令集(SSE/AVX)")
    except Exception as exc:
        print(f"  CPU       : 无法读取 ({exc})")


def check_vc_redist() -> tuple[list[str], list[str]]:
    """返回 (缺失 DLL 列表, 版本过旧 DLL 列表)。"""
    _banner("2. VC++ 运行库检查")
    missing: list[str] = []
    outdated: list[str] = []
    for dll in VC_DLLS:
        system_path = Path(r"C:\Windows\System32") / dll
        exists = system_path.exists()
        version = ""
        flag = ""
        if exists:
            version = _file_version(str(system_path))
            if version:
                parsed = _parse_version(version)
                if parsed is not None and parsed < VC_MIN_VERSION:
                    outdated.append(dll)
                    flag = "  ← 版本较旧,建议更新"
        marker = "OK " if exists else "MISS"
        print(f"  [{marker}] {dll:32s} {version}{flag}")
        if not exists:
            missing.append(dll)
    if missing:
        print(f"\n  缺失 {len(missing)} 个运行库文件 → 需要安装 VC++ 2015-2022 Redistributable (x64)")
        print(f"  下载: {VC_REDIST_URL}")
    elif outdated:
        print(f"\n  存在 {len(outdated)} 个较旧版本(建议版本 ≥ 14.40): "
              f"{', '.join(outdated)}")
        print("  旧版本运行库是 WinError 1114(初始化例程失败)的常见根因")
        print(f"  建议安装最新 VC++ 2015-2022 redist: {VC_REDIST_URL}")
    else:
        print("\n  VC++ 运行库版本齐全且较新")
    return missing, outdated


def diagnose_load_error() -> tuple[int | None, Path | None]:
    """用 ctypes 直接加载 onnxruntime C 扩展,捕获精确错误码。

    错误码判定:
      126 (0x7E)  模块找不到 — 缺依赖 DLL
      127 (0x7F)  过程找不到 — 运行库版本过旧/缺失函数
      1114(0x45C) 初始化例程失败 — 运行库版本旧/CPU 指令集/安全软件
    """
    _banner("3. onnxruntime C 扩展加载诊断")
    site_packages = Path(sys.prefix) / "Lib" / "site-packages"
    pyd_candidates = list((site_packages / "onnxruntime" / "capi").glob("onnxruntime_pybind11_state*.pyd"))
    if not pyd_candidates:
        print("  未找到 onnxruntime_pybind11_state.pyd(onnxruntime 未安装?)")
        return None, None
    pyd = pyd_candidates[0]
    print(f"  目标: {pyd}")
    print(f"  大小: {pyd.stat().st_size / 1024 / 1024:.1f} MB")
    ctypes.WinDLL  # noqa: B018 - 确保 ctypes.windll 可用
    try:
        ctypes.WinDLL(str(pyd), winmode=0)
    except OSError as exc:
        code = exc.winerror
        print(f"  加载失败, Windows 错误码: {code} (0x{code:08X})" if code else f"  加载失败: {exc}")
        if code == 126:
            print("  → 判定: 缺少依赖 DLL(最常见: VC++ 运行库缺失/损坏)")
        elif code == 127:
            print("  → 判定: 缺少运行库函数(VC++ 版本过旧,需 2015-2022 redist)")
        elif code == 1114:
            print("  → 判定: DLL 初始化例程失败(运行库版本过旧 / CPU 指令集不支持 / 安全软件拦截)")
        return code, pyd
    else:
        print("  直接加载成功!")
        return 0, pyd


def diagnose_torch() -> tuple[int | None, Path | None]:
    """诊断 PyTorch 备选栈:import + c10.dll 精确错误码(与 onnxruntime 同源)。"""
    _banner("3b. PyTorch 备选栈诊断")
    site_packages = Path(sys.prefix) / "Lib" / "site-packages"
    try:
        import torch  # noqa: F401
        import ultralytics  # noqa: F401
    except Exception as exc:
        print(f"  import 失败: {type(exc).__name__}: {str(exc)[:200]}")
    else:
        print(f"  torch {torch.__version__} / ultralytics {ultralytics.__version__} 导入成功!")
        return 0, None
    c10 = site_packages / "torch" / "lib" / "c10.dll"
    if not c10.exists():
        print(f"  c10.dll 不存在: {c10}(torch 未安装)")
        return None, None
    print(f"  目标: {c10}")
    try:
        ctypes.WinDLL(str(c10), winmode=0)
    except OSError as exc:
        code = exc.winerror
        print(f"  加载失败, Windows 错误码: {code} (0x{code:08X})" if code else f"  加载失败: {exc}")
        if code == 1114:
            print("  → 与 onnxruntime 相同的 1114: 属环境级问题(运行库/指令集),"
                  "不是 torch 包本身")
        return code, c10
    else:
        print("  c10.dll 直接加载成功(说明 import 失败在其他依赖)")
        return 0, c10


def try_import() -> str | None:
    """尝试 import onnxruntime,成功返回版本号。"""
    try:
        import onnxruntime

        return onnxruntime.__version__
    except Exception as exc:
        print(f"    import 失败: {type(exc).__name__}: {str(exc)[:120]}")
        return None


def auto_install_redist() -> bool:
    """联网下载并安装 VC++ redist(需管理员)。下载/安装失败时提示手动下载。"""
    _banner("4a. 尝试安装 VC++ 运行库")
    target = Path(os.environ.get("TEMP", ".")) / "vc_redist.x64.exe"
    try:
        import urllib.request

        print(f"  在线下载 {VC_REDIST_URL}")
        urllib.request.urlretrieve(VC_REDIST_URL, target)
        print(f"  已下载: {target} ({target.stat().st_size / 1024 / 1024:.1f} MB)")
    except Exception as exc:
        print(f"  下载失败: {exc}")
        print(f"  请手动下载并安装(以管理员运行): {VC_REDIST_URL}")
        return False
    installer = target
    try:
        result = subprocess.run(
            [str(installer), "/install", "/quiet", "/norestart"],
            capture_output=True,
            timeout=180,
        )
        print(f"  安装退出码: {result.returncode}(0=成功)")
        if result.returncode != 0:
            print(f"  安装失败。请手动下载并安装(以管理员运行): {VC_REDIST_URL}")
        return result.returncode == 0
    except Exception as exc:
        print(f"  安装失败: {exc}")
        print(f"  请手动下载并安装(以管理员运行): {VC_REDIST_URL}")
        return False


def try_versions(venv_python: str) -> str | None:
    """依次安装并测试多个 onnxruntime 版本。"""
    _banner("4b. 回退尝试多个 onnxruntime 版本")
    for version in VERSIONS_TO_TRY:
        print(f"\n  尝试 onnxruntime=={version} ...")
        cmd = [
            "uv", "pip", "install", "--python", venv_python,
            "--index-url", "https://pypi.org/simple",
            "--force-reinstall", f"onnxruntime=={version}",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            tail = (result.stderr or result.stdout).strip().splitlines()
            print(f"    安装失败: {tail[-1][:150] if tail else result.returncode}")
            continue
        got = try_import()
        if got:
            print(f"    ✓ onnxruntime {got} 导入成功!")
            return got
    return None


def final_report(version: str | None, error_code: int | None, missing_dlls: list[str], outdated_dlls: list[str], torch_code: int | None) -> None:
    _banner("5. 结论")
    if version:
        print(f"  onnxruntime {version} 可用,视觉检测可以启用。")
        print("  运行 `neobot init` 验证模型索引即可。")
        return
    print("  onnxruntime 未能在此环境跑起来。按原因处理:")
    if error_code == 1114 and not outdated_dlls and not missing_dlls:
        print("  0) 先排除运行库问题(1114 最常见根因): 安装 VC++ 2015-2022 redist(x64)")
        print(f"     下载: {VC_REDIST_URL}(以管理员运行)")
        print("     或运行: python scripts/onnx_deploy_check.py --install-redist(需管理员,联网下载)")
    if missing_dlls:
        print(f"  1) 缺失 VC++ 运行库文件({len(missing_dlls)} 个):")
        print(f"     下载: {VC_REDIST_URL}(以管理员运行)")
        print("     或运行: python scripts/onnx_deploy_check.py --install-redist(需管理员,联网下载)")
    if error_code == 1114:
        if outdated_dlls:
            print(f"  1) VC++ 运行库版本较旧({len(outdated_dlls)} 个): 这是 1114 最常见的根因。")
            print(f"     下载安装最新版: {VC_REDIST_URL}(覆盖旧版,以管理员运行)")
            print("     或运行: python scripts/onnx_deploy_check.py --install-redist(需管理员,联网下载)")
            print("     装完后重启终端,重跑本脚本验证;大概率可修复")
        elif torch_code == 1114:
            print("  1) 运行库最新但 onnxruntime 与 torch 均 1114: 指向 CPU 指令集未透传。")
        print("  2) DLL 初始化失败(1114) 其他可能: 虚拟机/CPU 未透传 SSE/AVX 指令集。")
        print("     - 虚拟化平台(vSphere/KVM/VirtualBox)给 VM 开启 CPU 直通或 SSE/AVX 特性")
        print("     - 或在物理机上运行 NeoBot")
        print("     - 若确认不是 CPU: 重装 VC++ redist 后重启,并临时关闭杀毒软件重装依赖")
    if error_code == 126 or error_code == 127:
        print(f"  2) 运行库缺失/过旧(错误码 {error_code}): 安装 VC++ 2015-2022 redist 后重启终端重试")
    print("\n  3) 兜底: 视觉检测可禁用运行(bot 主功能不受影响),后续在合适机器上启用。")


def main() -> int:
    args = sys.argv[1:]
    try_versions_flag = "--no-try-versions" not in args
    install_redist = "--install-redist" in args

    check_system_info()
    missing_dlls, outdated_dlls = check_vc_redist()
    error_code, pyd = diagnose_load_error()
    torch_code, _ = diagnose_torch()
    if error_code == 0:
        version = try_import()
        final_report(version, None, [], [], torch_code)
        return 0

    if install_redist and (missing_dlls or outdated_dlls):
        auto_install_redist()
        missing_dlls, outdated_dlls = check_vc_redist()
        error_code, pyd = diagnose_load_error()
        torch_code, _ = diagnose_torch()
        if error_code == 0:
            final_report(try_import(), None, [], [], torch_code)
            return 0

    version = None
    if try_versions_flag:
        venv_python = sys.executable
        version = try_versions(venv_python)
        if version:
            final_report(version, None, [], [], torch_code)
            return 0

    final_report(None, error_code, missing_dlls, outdated_dlls, torch_code)
    if not install_redist:
        print("\n  提示: 可执行 `python scripts/onnx_deploy_check.py --install-redist`"
              f"联网下载并安装 VC++ 运行库(需管理员);或手动下载 {VC_REDIST_URL}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
