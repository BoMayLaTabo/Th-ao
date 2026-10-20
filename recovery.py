import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import discord

BACKUP_DIR = Path(os.getenv("BACKUP_DIR", "/data/backups"))
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
_locks = {}

def _path(gid):
    return BACKUP_DIR / f"guild_{gid}.json"

def _overwrite(channel):
    return {str(target.id): {"allow": ow.pair()[0].value, "deny": ow.pair()[1].value,
            "type": "role" if isinstance(target, discord.Role) else "member"}
            for target, ow in channel.overwrites.items()}

def snapshot(guild):
    roles = [{"id": r.id, "name": r.name, "permissions": r.permissions.value,
              "colour": r.colour.value, "hoist": r.hoist, "mentionable": r.mentionable,
              "position": r.position} for r in guild.roles if not r.is_default() and not r.managed]
    channels = []
    for ch in guild.channels:
        if not isinstance(ch, (discord.CategoryChannel, discord.TextChannel, discord.VoiceChannel)):
            continue
        data = {"id": ch.id, "name": ch.name, "position": ch.position,
                "category_id": ch.category_id if not isinstance(ch, discord.CategoryChannel) else None,
                "overwrites": _overwrite(ch), "type": "category" if isinstance(ch, discord.CategoryChannel) else ("text" if isinstance(ch, discord.TextChannel) else "voice")}
        if isinstance(ch, discord.TextChannel):
            data.update(topic=ch.topic, nsfw=ch.nsfw, slowmode_delay=ch.slowmode_delay)
        if isinstance(ch, discord.VoiceChannel):
            data.update(bitrate=ch.bitrate, user_limit=ch.user_limit)
        channels.append(data)
    return {"version": 1, "guild_id": guild.id, "guild_name": guild.name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "roles": roles, "channels": channels}

def create_backup(guild):
    data = snapshot(guild)
    target = _path(guild.id)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)
    return data

def load_backup(guild):
    p = _path(guild.id)
    if not p.exists():
        raise FileNotFoundError("Chưa có bản sao lưu cho server này.")
    data = json.loads(p.read_text(encoding="utf-8"))
    if data.get("guild_id") != guild.id or data.get("version") != 1:
        raise ValueError("Backup không hợp lệ hoặc không thuộc server này.")
    return data

def backup_status(guild):
    try:
        data = load_backup(guild)
    except FileNotFoundError:
        return "Chưa có backup. Dùng /backup_create ngay."
    return f"Backup: {data['created_at']} | {len(data['roles'])} roles | {len(data['channels'])} channels."

async def restore(guild, data):
    """Non-destructive: only recreate missing roles/channels; never delete existing objects."""
    lock = _locks.setdefault(guild.id, asyncio.Lock())
    async with lock:
        result = {"roles": 0, "channels": 0, "errors": []}
        role_map = {guild.default_role.id: guild.default_role}
        # Map original @everyone role ID (same as guild ID)
        role_map[guild.id] = guild.default_role
        for r in sorted(data["roles"], key=lambda x: x["position"]):
            role = guild.get_role(r["id"])
            if role is None:
                try:
                    role = await guild.create_role(name=r["name"],
                        permissions=discord.Permissions(r["permissions"]),
                        colour=discord.Colour(r["colour"]),
                        hoist=r["hoist"], mentionable=r["mentionable"],
                        reason="GUARD recovery from approved backup")
                    result["roles"] += 1
                except (discord.Forbidden, discord.HTTPException) as e:
                    result["errors"].append(f"Role {r['name']}: {e}")
                    continue
            role_map[r["id"]] = role

        def overwrites(item):
            output = {}
            for sid, o in item.get("overwrites", {}).items():
                if o["type"] == "role":
                    target = role_map.get(int(sid))
                else:
                    target = guild.get_member(int(sid))
                if target:
                    output[target] = discord.PermissionOverwrite.from_pair(
                        discord.Permissions(o["allow"]), discord.Permissions(o["deny"]))
            return output

        channel_map = {c.id: c for c in guild.channels}
        ordered = sorted(data["channels"], key=lambda x: (x["type"] != "category", x["position"]))
        for item in ordered:
            ch = guild.get_channel(item["id"])
            if ch is not None:
                channel_map[item["id"]] = ch
                continue
            parent = channel_map.get(item.get("category_id"))
            if not isinstance(parent, discord.CategoryChannel):
                parent = None
            try:
                opts = {"name": item["name"], "overwrites": overwrites(item),
                        "reason": "GUARD recovery from approved backup"}
                if item["type"] == "category":
                    ch = await guild.create_category(**opts)
                elif item["type"] == "text":
                    ch = await guild.create_text_channel(category=parent,
                        topic=item.get("topic"), nsfw=item.get("nsfw", False),
                        slowmode_delay=item.get("slowmode_delay", 0), **opts)
                else:
                    ch = await guild.create_voice_channel(category=parent,
                        bitrate=min(item.get("bitrate", 64000), guild.bitrate_limit),
                        user_limit=item.get("user_limit", 0), **opts)
                channel_map[item["id"]] = ch
                result["channels"] += 1
            except (discord.Forbidden, discord.HTTPException, TypeError, ValueError) as e:
                result["errors"].append(f"Channel {item['name']}: {e}")
        return result
