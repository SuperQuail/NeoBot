"""Focused test: try different payload formats with longer timeouts."""
import asyncio
import base64
import httpx
import json
import time

BASE_URL = "https://api.gptgod.online/v1"
API_KEY = "sk-1vTm97YWvmUdTfyHgvBgDMkOtcPVDHormgNtaT6W8Ywsn8wO"
MODEL_NAME = "gpt-image-2"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


async def try_payload(client: httpx.AsyncClient, label: str, payload: dict, timeout: float = 120.0):
    print(f"\n=== {label} ===")
    print(f"Payload: {json.dumps(payload)}")
    t0 = time.monotonic()
    try:
        r = await client.post("/images/generations", json=payload, timeout=httpx.Timeout(timeout, connect=10.0))
        elapsed = time.monotonic() - t0
        print(f"Status: {r.status_code} ({elapsed:.1f}s)")
        print(f"Content-Type: {r.headers.get('content-type', '?')}")
        if r.status_code >= 400:
            print(f"Error: {r.text[:800]}")
        else:
            data = r.json()
            if "data" in data and isinstance(data["data"], list) and data["data"]:
                item = data["data"][0]
                if "b64_json" in item:
                    b64 = item["b64_json"]
                    img = base64.b64decode(b64)
                    print(f"SUCCESS: b64_json {len(b64)} chars -> {len(img)} bytes")
                    out = f"scripts/test_{label.replace(' ', '_').replace('/', '_')[:40]}.png"
                    with open(out, "wb") as f:
                        f.write(img)
                    print(f"Saved: {out}")
                elif "url" in item:
                    print(f"SUCCESS: url={item['url'][:120]}")
                else:
                    print(f"Unknown item: {json.dumps(item, ensure_ascii=False)[:300]}")
            else:
                print(f"Response: {json.dumps(data, ensure_ascii=False)[:500]}")
    except httpx.TimeoutException as e:
        elapsed = time.monotonic() - t0
        print(f"TIMEOUT after {elapsed:.1f}s: {e}")
    except Exception as e:
        elapsed = time.monotonic() - t0
        print(f"ERROR after {elapsed:.1f}s: {type(e).__name__}: {e}")


async def main():
    timeout = httpx.Timeout(180.0, connect=10.0)
    async with httpx.AsyncClient(
        base_url=BASE_URL.rstrip("/"),
        headers=HEADERS,
        timeout=timeout,
    ) as client:

        # Test 1: App's exact payload, longer timeout
        await try_payload(client, "App payload (image_size)", {
            "model": MODEL_NAME,
            "prompt": "A simple red circle on white background, minimalist",
            "image_size": "512x512",
        }, timeout=120.0)

        # Test 2: OpenAI standard format (size)
        await try_payload(client, "OpenAI format (size)", {
            "model": MODEL_NAME,
            "prompt": "A simple blue square on white background, minimalist",
            "size": "512x512",
        }, timeout=120.0)

        # Test 3: Both fields
        await try_payload(client, "Both image_size + size", {
            "model": MODEL_NAME,
            "prompt": "A simple green triangle on white background, minimalist",
            "image_size": "512x512",
            "size": "512x512",
        }, timeout=120.0)

        # Test 4: Minimal
        await try_payload(client, "Minimal no size", {
            "model": MODEL_NAME,
            "prompt": "A yellow star on white background, minimalist",
        }, timeout=120.0)

        # Test 5: Check if chat completions endpoint works for image
        await try_payload(client, "Chat completions", {
            "model": MODEL_NAME,
            "messages": [{"role": "user", "content": "Generate an image of a red circle"}],
        }, timeout=120.0)


asyncio.run(main())
