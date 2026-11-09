"""Private supervisor→API stdin handoff; no secrets in argv/env/log files."""
import json
import sys
import uvicorn
from fashion_api.core.config import WebConfig
from fashion_api.main import create_app


def main():
    try:
        line = sys.stdin.buffer.readline(16385)
        if len(line) > 16384:
            raise ValueError()
        payload = json.loads(line)
        app = create_app(WebConfig.model_validate(payload["config"]), bootstrap_secret=payload["secret"], instance_id=payload.get("instance_id"))
        del payload, line
    except Exception:
        print("Invalid private runtime handoff.", file=sys.stderr)
        return 2
    uvicorn.run(app, host="127.0.0.1", port=8000, workers=1, access_log=False,
                proxy_headers=False, server_header=False, log_level="critical")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
