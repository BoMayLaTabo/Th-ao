# Discord Guard Starter

This is a **starter**, not a full production anti-nuke system. Commands are registered on startup. Settings and warnings are in-memory only and reset after restart. Anti-Raid currently alerts but does not automatically kick or ban joiners. Anti-Nuke monitors repeated channel/role deletions and may timeout a detected actor, but cannot undo deletions. Lockdown does not preserve previous permission overwrites.

## Windows
1. Install Python 3.11–3.13 and open CMD in this folder.
2. `py -m pip install -r requirements.txt`
3. In Discord Developer Portal > Bot, enable **Server Members Intent** and **Message Content Intent**.
4. Set variables in CMD (do not paste token into chat):
   `set DISCORD_BOT_TOKEN=YOUR_TOKEN`
   `set GUILD_ID=YOUR_GUILD_ID`
5. `py bot.py`
6. In Discord, try `/ping`, `/help`, `/setup`.
7. Give the bot only permissions it needs and place its role above roles it moderates.

## Railway
Connect GitHub repo; add environment variables `DISCORD_BOT_TOKEN` and `GUILD_ID`; set start command `python bot.py`; check logs for `Online as` and `Synced ... guild slash commands`. Hosting costs and uptime depend on Railway plan.

## Important
- Never commit your bot token.
- Invite using OAuth2 scopes `bot` and `applications.commands`.
- Bot account is different from personal Discord Rich Presence.
- This version intentionally does not implement backups, restore, web dashboard, full anti-spam, or all advanced features.
