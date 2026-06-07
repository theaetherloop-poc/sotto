"""Print join URLs for the doctor and patient identities for a given room.

Usage:
    uv run python -m sotto.scripts.gen_tokens --room sotto-test
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from urllib.parse import quote_plus

from dotenv import load_dotenv
from livekit.api import AccessToken, VideoGrants

IDENTITIES = ("doctor", "patient")


def mint_token(api_key: str, api_secret: str, room: str, identity: str, ttl_minutes: int) -> str:
    grants = VideoGrants(room_join=True, room=room, can_publish=True, can_subscribe=True)
    return (
        AccessToken(api_key=api_key, api_secret=api_secret)
        .with_identity(identity)
        .with_name(identity.capitalize())
        .with_grants(grants)
        .with_ttl(dt.timedelta(minutes=ttl_minutes))
        .to_jwt()
    )


def main() -> int:
    load_dotenv(".env.local")
    load_dotenv()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--room", required=True, help="Room name to join (e.g. sotto-test)")
    parser.add_argument("--ttl", type=int, default=60, help="Token validity in minutes (default 60)")
    args = parser.parse_args()

    url = os.environ.get("LIVEKIT_URL")
    api_key = os.environ.get("LIVEKIT_API_KEY")
    api_secret = os.environ.get("LIVEKIT_API_SECRET")
    missing = [n for n, v in [("LIVEKIT_URL", url), ("LIVEKIT_API_KEY", api_key), ("LIVEKIT_API_SECRET", api_secret)] if not v]
    if missing:
        print(f"Missing env vars: {', '.join(missing)}. Run `lk app env -w .` first.", file=sys.stderr)
        return 1

    encoded_url = quote_plus(url)
    for identity in IDENTITIES:
        token = mint_token(api_key, api_secret, args.room, identity, args.ttl)
        join_url = f"https://meet.livekit.io/custom?liveKitUrl={encoded_url}&token={token}"
        print(f"\n{identity.upper()} ({identity}):\n{join_url}")
    print(f"\nRoom: {args.room}  |  Token valid for {args.ttl} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
