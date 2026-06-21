"""Quick connectivity test for GPTGOD drawing API."""
import asyncio
import httpx
import json

BASE_URL = "https://api.gptgod.online/v1"
API_KEY = "sk-1vTm97YWvmUdTfyHgvBgDMkOtcPVDHormgNtaT6W8Ywsn8wO"
MODEL_NAME = "gpt-image-2"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


async def main():
    timeout = httpx.Timeout(30.0, connect=10.0)
    async with httpx.AsyncClient(
        base_url=BASE_URL.rstrip("/"),
        headers=HEADERS,
        timeout=timeout,
    ) as client:

        # ── Test 1: List models ──
        print("=== Test 1: GET /models ===")
        try:
            r = await client.get("/models")
            print(f"Status: {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, dict) and "data" in data:
                    model_ids = [m.get("id", "?") for m in data["data"]]
                    print(f"Total models: {len(model_ids)}")
                    img_models = [m for m in model_ids if any(k in m.lower() for k in ("image", "dall", "flux", "sd", "stable", "midjourney"))]
                    print(f"Image-related models: {img_models if img_models else 'NONE'}")
                    if MODEL_NAME in model_ids:
                        print(f"'{MODEL_NAME}' EXISTS in model list.")
                    else:
                        print(f"'{MODEL_NAME}' NOT FOUND. First 30 models:")
                        for m in model_ids[:30]:
                            print(f"  - {m}")
            else:
                print(f"Error body: {r.text[:500]}")
        except Exception as e:
            print(f"ERROR: {type(e).__name__}: {e}")

        # ── Test 2: Quick image generation with exact app payload ──
        print("\n=== Test 2: POST /images/generations (app payload) ===")
        app_payload = {
            "model": MODEL_NAME,
            "prompt": "A red circle on white background",
            "image_size": "512x512",
        }
        print(f"Payload: {json.dumps(app_payload)}")
        try:
            r = await client.post("/images/generations", json=app_payload)
            print(f"Status: {r.status_code}")
            print(f"Response headers: content-type={r.headers.get('content-type', '?')}")
            if r.status_code >= 400:
                print(f"Error body: {r.text[:800]}")
            else:
                data = r.json()
                print(f"Response keys: {list(data.keys())}")
                if "data" in data and isinstance(data["data"], list) and data["data"]:
                    item = data["data"][0]
                    print(f"Item keys: {list(item.keys())}")
                    if "b64_json" in item:
                        print(f"b64_json: {len(item['b64_json'])} chars — SUCCESS")
                    elif "url" in item:
                        print(f"url: {item['url'][:120]} — SUCCESS")
                    else:
                        print(f"Item preview: {json.dumps(item, ensure_ascii=False)[:300]}")
                else:
                    print(f"Full response: {json.dumps(data, ensure_ascii=False)[:500]}")
        except Exception as e:
            print(f"ERROR: {type(e).__name__}: {e}")


asyncio.run(main())
