import os
import json
from pathlib import Path
import time
import asyncio
from collections import defaultdict, deque
import discord
from discord import app_commands
from discord.ext import commands

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
if not TOKEN:
    raise RuntimeError("Set DISCORD_BOT_TOKEN in environment variables.")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
SETTINGS_FILE = Path(os.getenv("SETTINGS_FILE", "guard_settings.json"))
def default_settings():
    return {"antinuke": True, "antiraid": True, "log": None, "trusted": set(), "lockdown": False}
settings = defaultdict(default_settings)
def save_settings():
    data = {str(gid): {**cfg, "trusted": list(cfg["trusted"])} for gid, cfg in settings.items()}
    temp = SETTINGS_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temp.replace(SETTINGS_FILE)
def load_settings():
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            for gid, cfg in data.items():
                settings[int(gid)].update(cfg)
                settings[int(gid)]["trusted"] = set(map(int, cfg.get("trusted", [])))
        except (ValueError, OSError) as exc:
            print(f"Settings load warning: {exc}")
load_settings()
actions = defaultdict(deque)
joins = defaultdict(deque)

async def log(guild, message):
    channel_id = settings[guild.id]["log"]
    channel = guild.get_channel(channel_id) if channel_id else None
    if isinstance(channel, discord.TextChannel):
        try:
            await channel.send(message[:1900])
        except discord.HTTPException:
            pass

async def audit_actor(guild, action, target_id):
    try:
        async for entry in guild.audit_logs(limit=8, action=action):
            if entry.target and entry.target.id == target_id and (discord.utils.utcnow() - entry.created_at).total_seconds() < 20:
                return entry.user
    except (discord.Forbidden, discord.HTTPException):
        pass
    return None

async def check_nuke(guild, actor, kind):
    if not actor or actor.id == bot.user.id or actor.id == guild.owner_id or actor.id in settings[guild.id]["trusted"]:
        return
    key = (guild.id, actor.id, kind)
    now = time.monotonic()
    q = actions[key]
    q.append(now)
    while q and now - q[0] > 15:
        q.popleft()
    if len(q) >= 3:
        q.clear()
        member = guild.get_member(actor.id)
        if member and guild.me and member.top_role < guild.me.top_role:
            try:
                await member.timeout(discord.utils.utcnow() + __import__("datetime").timedelta(minutes=30), reason="Anti-Nuke: repeated destructive actions")
                await log(guild, f"🛡️ Anti-Nuke: timeout {member.mention} after repeated {kind}")
            except (discord.Forbidden, discord.HTTPException) as exc:
                await log(guild, f"⚠️ Could not timeout {member.mention}: {exc}")

@bot.event
async def on_guild_channel_delete(channel):
    if settings[channel.guild.id]["antinuke"]:
        await asyncio.sleep(1)
        actor = await audit_actor(channel.guild, discord.AuditLogAction.channel_delete, channel.id)
        await check_nuke(channel.guild, actor, "channel deletion")

@bot.event
async def on_guild_role_delete(role):
    if settings[role.guild.id]["antinuke"]:
        await asyncio.sleep(1)
        actor = await audit_actor(role.guild, discord.AuditLogAction.role_delete, role.id)
        await check_nuke(role.guild, actor, "role deletion")

@bot.event
async def on_member_join(member):
    cfg = settings[member.guild.id]
    if not cfg["antiraid"]:
        return
    q = joins[member.guild.id]
    now = time.monotonic()
    q.append(now)
    while q and now - q[0] > 20:
        q.popleft()
    if len(q) == 8:
        await log(member.guild, "🚨 Anti-Raid alert: 8 joins in 20 seconds. Review new members and enable verification.")

@bot.event
async def on_ready():
    print(f"Online as {bot.user} ({bot.user.id})")

@bot.event
async def setup_hook():
    from dashboard import start_dashboard
    await start_dashboard(bot, settings, save_settings)
    if GUILD_ID:
        guild = discord.Object(id=GUILD_ID)
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        print(f"Synced {len(synced)} guild slash commands to {GUILD_ID}")
    else:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} global slash commands (may take time to appear)")

def admin_only():
    return app_commands.checks.has_permissions(administrator=True)

@bot.tree.command(description="Check bot latency")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"🏓 Pong: {bot.latency*1000:.0f} ms", ephemeral=True)

@bot.tree.command(description="List available commands")
async def help(interaction: discord.Interaction):
    await interaction.response.send_message(
        "/ping, /help, /botinfo, /serverinfo, /setup, /dashboard, /antinuke, /antiraid, /security, /whitelist, /lockdown, /unlock, /ban, /kick, /timeout, /untimeout, /purge, /lock, /warn, /warnings",
        ephemeral=True)

@bot.tree.command(description="Bot information")
async def botinfo(interaction: discord.Interaction):
    await interaction.response.send_message(f"Guard Bot • discord.py {discord.__version__}", ephemeral=True)

@bot.tree.command(description="Server information")
async def serverinfo(interaction: discord.Interaction):
    g = interaction.guild
    await interaction.response.send_message(f"{g.name}: {g.member_count} members", ephemeral=True)

@bot.tree.command(description="Show setup status")
@admin_only()
async def setup(interaction: discord.Interaction):
    c = settings[interaction.guild_id]
    await interaction.response.send_message(f"Anti-Nuke: {c['antinuke']}; Anti-Raid: {c['antiraid']}; Log channel: {c['log']}", ephemeral=True)

@bot.tree.command(description="Dashboard availability")
async def dashboard(interaction: discord.Interaction):
    await interaction.response.send_message("Web dashboard is not installed in this starter version.", ephemeral=True)

@bot.tree.command(description="Toggle Anti-Nuke protection")
@admin_only()
@app_commands.describe(enabled="Enable or disable Anti-Nuke")
async def antinuke(interaction: discord.Interaction, enabled: bool):
    settings[interaction.guild_id]["antinuke"] = enabled
    save_settings()
    await interaction.response.send_message(f"Anti-Nuke: {'ON' if enabled else 'OFF'}", ephemeral=True)

@bot.tree.command(description="Toggle Anti-Raid join alerts")
@admin_only()
async def antiraid(interaction: discord.Interaction, enabled: bool):
    settings[interaction.guild_id]["antiraid"] = enabled
    save_settings()
    await interaction.response.send_message(f"Anti-Raid alerts: {'ON' if enabled else 'OFF'}", ephemeral=True)

@bot.tree.command(description="Configure security log channel")
@admin_only()
async def security(interaction: discord.Interaction, log_channel: discord.TextChannel):
    settings[interaction.guild_id]["log"] = log_channel.id
    save_settings()
    await interaction.response.send_message(f"Security logs → {log_channel.mention}", ephemeral=True)

@bot.tree.command(description="Add or remove a trusted user")
@admin_only()
async def whitelist(interaction: discord.Interaction, member: discord.Member, trusted: bool):
    trusted_ids = settings[interaction.guild_id]["trusted"]
    (trusted_ids.add if trusted else trusted_ids.discard)(member.id)
    save_settings()
    await interaction.response.send_message(f"{member.mention}: trusted={trusted}", ephemeral=True)

@bot.tree.command(description="Lock a text channel")
@admin_only()
async def lock(interaction: discord.Interaction, channel: discord.TextChannel):
    await channel.set_permissions(interaction.guild.default_role, send_messages=False, reason=f"Locked by {interaction.user}")
    await interaction.response.send_message(f"Locked {channel.mention}", ephemeral=True)

@bot.tree.command(description="Lock all text channels (careful)")
@admin_only()
async def lockdown(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    success = 0
    for channel in interaction.guild.text_channels:
        try:
            await channel.set_permissions(interaction.guild.default_role, send_messages=False, reason="Emergency lockdown")
            success += 1
        except (discord.Forbidden, discord.HTTPException):
            pass
    await interaction.followup.send(f"Locked {success} text channels. Existing overwrites are not backed up.", ephemeral=True)

@bot.tree.command(description="Unlock a text channel (reset @everyone send override)")
@admin_only()
async def unlock(interaction: discord.Interaction, channel: discord.TextChannel):
    await channel.set_permissions(interaction.guild.default_role, send_messages=None, reason=f"Unlocked by {interaction.user}")
    await interaction.response.send_message(f"Reset send permission for {channel.mention}", ephemeral=True)

@bot.tree.command(description="Ban a member")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "Moderator action"):
    await member.ban(reason=reason)
    await interaction.response.send_message(f"Banned {member}", ephemeral=True)

@bot.tree.command(description="Kick a member")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "Moderator action"):
    await member.kick(reason=reason)
    await interaction.response.send_message(f"Kicked {member}", ephemeral=True)

@bot.tree.command(description="Timeout a member for N minutes")
@app_commands.checks.has_permissions(moderate_members=True)
async def timeout(interaction: discord.Interaction, member: discord.Member, minutes: app_commands.Range[int, 1, 40320]):
    await member.timeout(discord.utils.utcnow() + __import__("datetime").timedelta(minutes=minutes))
    await interaction.response.send_message(f"Timed out {member} for {minutes} minutes", ephemeral=True)

@bot.tree.command(description="Remove timeout from member")
@app_commands.checks.has_permissions(moderate_members=True)
async def untimeout(interaction: discord.Interaction, member: discord.Member):
    await member.timeout(None)
    await interaction.response.send_message(f"Timeout removed: {member}", ephemeral=True)

@bot.tree.command(description="Delete recent messages")
@app_commands.checks.has_permissions(manage_messages=True)
async def purge(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
    await interaction.response.defer(ephemeral=True)
    count = len(await interaction.channel.purge(limit=amount))
    await interaction.followup.send(f"Deleted {count} messages", ephemeral=True)

@bot.tree.command(description="Warn a member (non-persistent)")
@app_commands.checks.has_permissions(moderate_members=True)
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str):
    key = (interaction.guild_id, member.id)
    warnings_db[key].append(reason)
    await interaction.response.send_message(f"Warned {member}: {reason}", ephemeral=True)

warnings_db = defaultdict(list)

@bot.tree.command(description="View member warnings (non-persistent)")
@app_commands.checks.has_permissions(moderate_members=True)
async def warnings(interaction: discord.Interaction, member: discord.Member):
    items = warnings_db[(interaction.guild_id, member.id)]
    await interaction.response.send_message("\n".join(items[-10:])[:1900] if items else "No warnings.", ephemeral=True)

@bot.tree.error
async def tree_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    message = f"Command failed: {error}"
    if interaction.response.is_done():
        await interaction.followup.send(message[:1900], ephemeral=True)
    else:
        await interaction.response.send_message(message[:1900], ephemeral=True)

bot.run(TOKEN)
