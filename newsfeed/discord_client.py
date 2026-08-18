"""Discord REST client.

Deliberately REST-only. Reading which items a human picked does not need a
gateway connection, so there is no always-on bot to keep alive — two scheduled
GitHub Actions runs are enough:

    19:00  run_review.py   posts the day's list, seeds number reactions
    21:00  run_publish.py  reads the reactions, renders and uploads the cards

Posting reuses the existing Autopilot webhook when DISCORD_WEBHOOK_URL is set,
so no new posting credential is needed. Reactions are the part a webhook cannot
do — reading who reacted requires an authenticated token — so a bot handles
seeding and reading them.

    DISCORD_WEBHOOK_URL   optional. Reuses the Autopilot webhook for posting.
    DISCORD_BOT_TOKEN     required. Seeds and reads reactions.
    DISCORD_BOT_USER_ID   required. Filters out the bot's own seed reactions.
    DISCORD_CHANNEL_ID    optional when a webhook is used — it is read back
                          from the webhook's own response.

Bot permissions: Add Reactions, Read Message History
(plus Send Messages and Attach Files if no webhook is configured).
"""

from __future__ import annotations

import json
import mimetypes
import os
import time
import urllib.parse
from pathlib import Path

import requests

API = "https://discord.com/api/v10"
UA = "REVO-newsfeed (https://bey0nd.online, 1.0)"


class DiscordError(RuntimeError):
    pass


class Discord:
    def __init__(self, token: str | None = None, channel_id: str | None = None,
                 webhook_url: str | None = None, dry_run: bool = False):
        self.token = token or os.environ.get("DISCORD_BOT_TOKEN", "")
        self.channel_id = channel_id or os.environ.get("DISCORD_CHANNEL_ID", "")
        self.webhook = webhook_url or os.environ.get("DISCORD_WEBHOOK_URL", "")
        self.dry_run = dry_run
        if dry_run:
            return
        if not self.token:
            raise DiscordError(
                "DISCORD_BOT_TOKEN が必要です（リアクションの読み取りに使います）"
            )
        if not (self.webhook or self.channel_id):
            raise DiscordError("DISCORD_WEBHOOK_URL か DISCORD_CHANNEL_ID のどちらかが必要です")

    # -- plumbing ----------------------------------------------------------
    def _headers(self) -> dict:
        return {"Authorization": f"Bot {self.token}", "User-Agent": UA}

    def _request(self, method: str, path: str, **kw) -> dict:
        url = f"{API}{path}"
        if self.dry_run:
            body = kw.get("json") or {k: "<binary>" for k in kw.get("files", {})}
            print(f"\n[dry-run] {method} {url}")
            print(json.dumps(body, ensure_ascii=False, indent=1)[:1500])
            return {"id": f"dry-{abs(hash(path)) % 10**18}"}

        for attempt in range(5):
            r = requests.request(method, url, headers=self._headers(), timeout=30, **kw)
            # Discord rate limits are normal operation, not an error condition.
            if r.status_code == 429:
                wait = float(r.json().get("retry_after", 1)) + 0.2
                time.sleep(wait)
                continue
            if r.status_code >= 400:
                raise DiscordError(f"{method} {path} -> {r.status_code} {r.text[:300]}")
            return r.json() if r.content else {}
        raise DiscordError(f"{method} {path}: レート制限で5回失敗しました")

    # -- messages ----------------------------------------------------------
    def _webhook_post(self, payload: dict, files: dict | None = None) -> dict:
        # ?wait=true makes Discord return the created message, which is the
        # only way to learn its id — and without the id there is nothing to
        # attach reactions to.
        url = f"{self.webhook}?wait=true"
        if self.dry_run:
            print(f"\n[dry-run] POST {url}")
            print(json.dumps(payload, ensure_ascii=False, indent=1)[:1200])
            return {"id": "dry-webhook", "channel_id": "dry-channel"}
        kw = {"files": files} if files else {"json": payload}
        for _ in range(5):
            r = requests.post(url, timeout=30, **kw)
            if r.status_code == 429:
                time.sleep(float(r.json().get("retry_after", 1)) + 0.2)
                continue
            if r.status_code >= 400:
                raise DiscordError(f"webhook -> {r.status_code} {r.text[:300]}")
            msg = r.json()
            # Learn the channel from the webhook so it need not be configured.
            self.channel_id = self.channel_id or msg.get("channel_id", "")
            return msg
        raise DiscordError("webhook: レート制限で5回失敗しました")

    def post(self, content: str, channel_id: str | None = None) -> dict:
        if self.webhook and not channel_id:
            return self._webhook_post({"content": content})
        cid = channel_id or self.channel_id
        return self._request("POST", f"/channels/{cid}/messages", json={"content": content})

    def post_with_files(self, content: str, paths: list[Path],
                        channel_id: str | None = None) -> dict:
        """Attach the rendered cards so they can be saved straight to a phone."""
        cid = channel_id or self.channel_id
        use_webhook = bool(self.webhook) and not channel_id
        payload = {
            "content": content,
            "attachments": [{"id": i, "filename": p.name} for i, p in enumerate(paths)],
        }

        if self.dry_run:
            dest = f"{self.webhook}?wait=true" if use_webhook else f"{API}/channels/{cid}/messages"
            print(f"\n[dry-run] POST {dest}  (multipart)")
            print(f"  添付 {len(paths)}件: {[p.name for p in paths]}")
            print("  " + content[:400].replace("\n", "\n  "))
            return {"id": "dry-files", "channel_id": cid or "dry-channel"}

        files = {"payload_json": (None, json.dumps(payload), "application/json")}
        handles = []
        try:
            for i, p in enumerate(paths):
                fh = open(p, "rb")
                handles.append(fh)
                mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
                files[f"files[{i}]"] = (p.name, fh, mime)
            if use_webhook:
                return self._webhook_post(payload, files=files)
            return self._request("POST", f"/channels/{cid}/messages", files=files)
        finally:
            for fh in handles:
                fh.close()

    # -- reactions ---------------------------------------------------------
    def add_reaction(self, message_id: str, emoji: str,
                     channel_id: str | None = None) -> None:
        cid = channel_id or self.channel_id
        e = urllib.parse.quote(emoji)
        self._request("PUT", f"/channels/{cid}/messages/{message_id}/reactions/{e}/@me")

    def reacted_users(self, message_id: str, emoji: str,
                      channel_id: str | None = None) -> list[dict]:
        cid = channel_id or self.channel_id
        e = urllib.parse.quote(emoji)
        res = self._request("GET", f"/channels/{cid}/messages/{message_id}/reactions/{e}?limit=25")
        return res if isinstance(res, list) else []

    def picked(self, message_id: str, emojis: list[str],
               bot_user_id: str | None = None,
               channel_id: str | None = None) -> list[str]:
        """Which emojis a human (not this bot) reacted with.

        The bot seeds every number so the human only has to tap, which means
        its own reactions must be filtered out or everything looks selected.
        """
        bot_id = bot_user_id or os.environ.get("DISCORD_BOT_USER_ID", "")
        out = []
        for e in emojis:
            users = self.reacted_users(message_id, e, channel_id)
            if any(u.get("id") != bot_id for u in users):
                out.append(e)
        return out

    def me(self) -> dict:
        return self._request("GET", "/users/@me")

    def doctor(self) -> None:
        """Check the credentials before trusting a scheduled run to them."""
        print("投稿経路:", "Webhook（Autopilot流用）" if self.webhook else "Bot")
        who = self.me()
        print(f"bot: {who.get('username')}#{who.get('discriminator')}  id={who.get('id')}")
        env_id = os.environ.get("DISCORD_BOT_USER_ID", "")
        if not env_id:
            print("  ! DISCORD_BOT_USER_ID が未設定です。"
                  "このままだと全項目が選択済みに見えます。")
            print(f"    上の id をそのまま設定してください: {who.get('id')}")
        elif env_id != who.get("id"):
            print(f"  ! DISCORD_BOT_USER_ID が一致しません（設定値 {env_id}）")
        else:
            print("  DISCORD_BOT_USER_ID: 一致")
        msg = self.post("REVO newsfeed: 接続確認")
        cid = msg.get("channel_id") or self.channel_id
        print(f"投稿OK message_id={msg.get('id')} channel_id={cid}")
        self.add_reaction(msg["id"], "1️⃣", channel_id=cid)
        print("リアクション付与OK — この投稿に手でリアクションしてから下を確認してください")
        print(f"  python -c \"from discord_client import Discord;"
              f" print(Discord().picked('{msg.get('id')}', ['1️⃣'], channel_id='{cid}'))\"")
