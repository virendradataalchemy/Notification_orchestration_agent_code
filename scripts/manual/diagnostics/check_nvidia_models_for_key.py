import argparse
import json
import os
import sys
from urllib import error, request


MODELS_URL = "https://integrate.api.nvidia.com/v1/models"


def fetch_models(api_key: str) -> list[dict]:
    req = request.Request(MODELS_URL)
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Accept", "application/json")

    try:
        with request.urlopen(req, timeout=30) as response:
            body = response.read().decode("utf-8")
            payload = json.loads(body)
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"HTTP {exc.code} from NVIDIA API.\nResponse body:\n{body}"
        ) from exc
    except error.URLError as exc:
        raise RuntimeError(f"Network error while contacting NVIDIA API: {exc}") from exc

    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return payload["data"]

    raise RuntimeError(
        f"Unexpected response format from NVIDIA API: {type(payload).__name__}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List NVIDIA models available for an API key."
    )
    parser.add_argument(
        "--api-key",
        help="NVIDIA API key. If omitted, reads from NVIDIA_API_KEY env var.",
    )
    args = parser.parse_args()

    api_key = args.api_key or os.getenv("NVIDIA_API_KEY")
    if not api_key:
        print(
            "Error: provide --api-key or set NVIDIA_API_KEY environment variable.",
            file=sys.stderr,
        )
        return 1

    try:
        models = fetch_models(api_key)
    except RuntimeError as exc:
        print(f"Failed to fetch models: {exc}", file=sys.stderr)
        return 1

    if not models:
        print("No models returned for this API key.")
        return 0

    print(f"Accessible models: {len(models)}")
    for model in sorted(models, key=lambda m: m.get("id", "")):
        model_id = model.get("id", "<unknown-id>")
        model_type = model.get("type", "unknown")
        owned_by = model.get("owned_by", "unknown")
        print(f"- {model_id} (type: {model_type}, owned_by: {owned_by})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
