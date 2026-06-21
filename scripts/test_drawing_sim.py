"""
Drawing system simulation test — isolates the image generation API call.

Tests the GPTGOD /images/generations endpoint with the exact payload
format used by CreatorImageService.generate_image().
"""
import asyncio
import base64
import httpx
import json
import sys

# ── Config from app/.env and app/data/config.toml ──
BASE_URL = "https://api.gptgod.online/v1"
API_KEY = "sk-1vTm97YWvmUdTfyHgvBgDMkOtcPVDHormgNtaT6W8Ywsn8wO"
MODEL_NAME = "gpt-image-2"  # from config.toml [models.creator_image_model]
DEFAULT_IMAGE_SIZE = "512x512"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


async def test_connection(client: httpx.AsyncClient) -> None:
    """Test basic API connectivity."""
    print("=" * 60)
    print("TEST 1: Basic connectivity — GET /v1/models")
    print("=" * 60)
    try:
        r = await client.get("/models")
        print(f"  Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            # Check if image models exist
            if isinstance(data, dict) and "data" in data:
                model_ids = [m.get("id", "?") for m in data["data"]]
                img_models = [m for m in model_ids if "image" in m.lower() or "dall" in m.lower() or "flux" in m.lower()]
                print(f"  Total models: {len(model_ids)}")
                print(f"  Image-related models: {img_models if img_models else 'NONE FOUND'}")
                # Check if our specific model exists
                if MODEL_NAME in model_ids:
                    print(f"  Model '{MODEL_NAME}' EXISTS in model list")
                else:
                    print(f"  Model '{MODEL_NAME}' NOT in model list! Available models (first 20): {model_ids[:20]}")
            else:
                print(f"  Unexpected response format: {json.dumps(data, ensure_ascii=False)[:300]}")
        else:
            print(f"  Response body: {r.text[:300]}")
    except Exception as e:
        print(f"  ERROR: {e}")


async def test_image_generation(
    client: httpx.AsyncClient,
    label: str,
    payload: dict,
) -> None:
    """Test /images/generations with a given payload."""
    print(f"\n{'=' * 60}")
    print(f"TEST: {label}")
    print(f"  Payload: {json.dumps(payload, ensure_ascii=False)}")
    print(f"{'=' * 60}")
    try:
        r = await client.post("/images/generations", json=payload)
        print(f"  Status: {r.status_code}")
        print(f"  Headers: {dict(r.headers)}")

        if r.status_code >= 400:
            print(f"  ERROR BODY: {r.text[:800]}")
            return

        data = r.json()
        print(f"  Response keys: {list(data.keys())}")
        if "data" in data:
            items = data["data"]
            if isinstance(items, list) and items:
                first = items[0]
                print(f"  First item keys: {list(first.keys())}")
                if "b64_json" in first:
                    b64 = first["b64_json"]
                    print(f"  b64_json length: {len(b64)} chars")
                    img_bytes = base64.b64decode(b64)
                    print(f"  Decoded image bytes: {len(img_bytes)} bytes")
                    print(f"  Image header: {img_bytes[:16].hex()}")
                    # Save test output
                    out_path = "scripts/test_output.png"
                    with open(out_path, "wb") as f:
                        f.write(img_bytes)
                    print(f"  Saved to: {out_path}")
                elif "url" in first:
                    print(f"  Image URL: {first['url'][:100]}")
                else:
                    print(f"  First item data: {json.dumps(first, ensure_ascii=False)[:500]}")
            else:
                print(f"  data field is not a non-empty list: {items}")
        else:
            print(f"  Full response: {json.dumps(data, ensure_ascii=False)[:800]}")
    except httpx.HTTPStatusError as e:
        print(f"  HTTP ERROR: {e.response.status_code}")
        print(f"  Response body: {e.response.text[:800]}")
    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")


async def main():
    timeout = httpx.Timeout(300.0, connect=10.0)
    async with httpx.AsyncClient(
        base_url=BASE_URL.rstrip("/"),
        headers=HEADERS,
        timeout=timeout,
    ) as client:

        # ── Test 1: connection & model list ──
        await test_connection(client)

        # ── Test 2: exact app payload format ──
        app_payload = {
            "model": MODEL_NAME,
            "prompt": "A simple red circle on white background, minimal, clean",
            "image_size": DEFAULT_IMAGE_SIZE,
        }
        await test_image_generation(client, "Exact app payload (image_size)", app_payload)

        # ── Test 3: OpenAI standard format (size instead of image_size) ──
        openai_payload = {
            "model": MODEL_NAME,
            "prompt": "A simple blue square on white background",
            "size": DEFAULT_IMAGE_SIZE,
        }
        await test_image_generation(client, "OpenAI format (size instead of image_size)", openai_payload)

        # ── Test 4: Both fields ──
        both_payload = {
            "model": MODEL_NAME,
            "prompt": "A simple green triangle on white background",
            "image_size": DEFAULT_IMAGE_SIZE,
            "size": DEFAULT_IMAGE_SIZE,
        }
        await test_image_generation(client, "Both image_size + size", both_payload)

        # ── Test 5: Minimal payload ──
        minimal_payload = {
            "model": MODEL_NAME,
            "prompt": "A yellow star on white background",
        }
        await test_image_generation(client, "Minimal (no size field)", minimal_payload)

        # ── Test 6: n=1 parameter ──
        n_payload = {
            "model": MODEL_NAME,
            "prompt": "A purple heart on white background",
            "size": DEFAULT_IMAGE_SIZE,
            "n": 1,
        }
        await test_image_generation(client, "With n=1", n_payload)

        # ── Test 7: response_format b64_json ──
        b64_payload = {
            "model": MODEL_NAME,
            "prompt": "An orange circle on white background",
            "size": DEFAULT_IMAGE_SIZE,
            "response_format": "b64_json",
        }
        await test_image_generation(client, "With response_format=b64_json", b64_payload)


if __name__ == "__main__":
    asyncio.run(main())
