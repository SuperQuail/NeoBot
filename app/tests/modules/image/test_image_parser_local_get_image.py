from __future__ import annotations

from neobot_adapter.model.response import BaseResponse
from neobot_app.image.parser import _read_image_ref, _response_data


def test_response_data_accepts_dict_and_pydantic_response() -> None:
    assert _response_data({"data": {"file": "a.png"}}) == {"file": "a.png"}

    response = BaseResponse(status="ok", retcode=0, data={"file": "b.png"})
    assert _response_data(response) == {"file": "b.png"}


async def test_read_image_ref_accepts_local_path(tmp_path) -> None:
    image_path = tmp_path / "tiny.png"
    image_path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    )

    assert await _read_image_ref(str(image_path)) == image_path.read_bytes()
