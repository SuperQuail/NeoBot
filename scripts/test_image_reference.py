r"""参考图生图实测脚本（密钥只从环境变量读取，不入库）。

用法（PowerShell）：
    $env:IMAGE_API_BASE="https://sub.sailapi.top/v1"
    $env:IMAGE_API_KEY="sk-..."
    $env:IMAGE_API_MODEL="gpt-image-2.5-flare"
    python scripts/test_image_reference.py "D:\path\reference.png"

可选环境变量：
    IMAGE_API_MODE=auto|edits|generations（默认 auto）
    IMAGE_REFERENCE_PARAM=image|images|image_url|image_urls|input_image（generations 模式用）
    IMAGE_PROMPT=...（默认「把参考图中的角色放到海滩日落场景里，保持角色外观特征」）
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path

from neobot_chat import ModelPricing, ModelSettings, RegisteredModel, register_model
from neobot_storage import create_engine, make_uow_factory
from neobot_storage.models import Base

from neobot_app.drawing.config import DrawServiceConfig
from neobot_app.drawing.service import CreatorImageService

MODEL_KEY = "reference-test-model"


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"缺少环境变量 {name}")
    return value


async def main() -> int:
    base_url = _require("IMAGE_API_BASE")
    api_key = _require("IMAGE_API_KEY")
    model_name = _require("IMAGE_API_MODEL")
    reference = Path(sys.argv[1] if len(sys.argv) > 1 else "").expanduser()
    if not reference.is_file():
        sys.exit(f"参考图不存在: {reference}")
    prompt = os.environ.get("IMAGE_PROMPT") or "把参考图中的角色放到海滩日落场景里，保持角色外观特征"

    settings = ModelSettings(
        timeout_seconds=float(os.environ.get("IMAGE_API_TIMEOUT", "300")),
        image_api=os.environ.get("IMAGE_API_MODE", "auto"),
        image_reference_param=os.environ.get("IMAGE_REFERENCE_PARAM", "image"),
    )
    register_model(
        RegisteredModel(
            name=MODEL_KEY,
            description="参考图测试模型",
            provider_name="SailAPI",
            model_name=model_name,
            base_url=base_url,
            api_key=api_key,
            pricing=ModelPricing(),
            settings=settings,
            model_type="image",
        )
    )

    work_dir = Path(__file__).resolve().parent.parent / "dist" / "reference_test"
    work_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite+aiosqlite:///{(work_dir / 'ref.sqlite3').as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    service = CreatorImageService(
        uow_factory=make_uow_factory(engine),
        adapter=None,
        config=DrawServiceConfig(gallery_capacity=10, gallery_page_size=50),
        data_dir=work_dir,
        model_names=[MODEL_KEY],
    )
    try:
        target = service._tmp_dir / f"reference{reference.suffix or '.png'}"
        shutil.copy(reference, target)
        print(f"模式={settings.image_api} 字段={settings.image_reference_param} 模型={model_name}")
        record = await service.generate_image(
            prompt=prompt,
            references=[f"file:{target}"],
            image_size=os.environ.get("IMAGE_API_SIZE", "1024x1024"),
        )
        # 结果落在 tmp 目录，close() 会清理，先复制到固定路径
        keep = work_dir / "reference_result.png"
        shutil.copy(record.file_path, keep)
        print(f"成功: {keep} {record.original_width}x{record.original_height}")
        return 0
    except Exception as exc:  # noqa: BLE001 - 排查脚本需要完整原因
        print(f"失败: {type(exc).__name__}: {exc}")
        return 1
    finally:
        await service.close()
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
