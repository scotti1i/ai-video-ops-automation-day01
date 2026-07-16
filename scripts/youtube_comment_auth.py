#!/usr/bin/env python3
"""为评论读取创建独立 OAuth token，不修改 uploader 的上传 token。"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

COMMENT_SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"


def main() -> None:
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("--uploader-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    client_secrets = args.uploader_dir / "client_secrets.json"
    if not client_secrets.is_file():
        raise SystemExit("缺少 uploader/client_secrets.json，无法发起评论授权。")

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(
        str(client_secrets),
        [COMMENT_SCOPE],
    )
    credentials = flow.run_local_server(port=0, prompt="consent")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(credentials.to_json(), encoding="utf-8")
    os.chmod(args.output, 0o600)
    print(f"评论读取授权已保存：{args.output}")


if __name__ == "__main__":
    main()
