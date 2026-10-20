# GUARD SECURITY — Discord Bot + Web Dashboard

Single Railway service runs both discord.py bot and aiohttp dashboard on `$PORT`.

## Deploy
1. Upload all files in this folder to your GitHub repository (replace previous bot.py and requirements.txt).
2. In Railway service Settings, use Start Command `python bot.py` (Procfile also provides this).
3. In Railway > Variables, set:
   - `DISCORD_BOT_TOKEN` = bot token (never commit)
   - `GUILD_ID` = Discord server ID for quick slash command sync
   - `DISCORD_CLIENT_ID` = Discord application ID
   - `DISCORD_CLIENT_SECRET` = Discord Developer Portal > OAuth2 > Client Secret
   - `SESSION_SECRET` = random 32+ character string, keep secret
   - `DASHBOARD_URL` = public HTTPS Railway domain, no trailing slash
4. Railway > service > Settings > Networking > Generate Domain; copy the domain into DASHBOARD_URL and redeploy.
5. Discord Developer Portal > OAuth2 > Redirects > Add Redirect: `https://YOUR-DOMAIN.up.railway.app/callback` (must match DASHBOARD_URL + `/callback` exactly). Save changes.
6. Open your Railway domain; click **Login with Discord**. Only Discord server owners/admins with the bot in the server may configure it.
7. Discord Developer Portal > Bot: enable Server Members Intent and Message Content Intent; invite with bot + applications.commands scopes.

## Data persistence
Configuration is saved in `guard_settings.json`, which is ephemeral on default Railway deployments. For persistence, mount a Railway Volume at `/data` and set `SETTINGS_FILE=/data/guard_settings.json`. Use only one replica to avoid concurrent writes. Volume availability depends on your Railway plan.

## Security
- Discord OAuth2 authorization-code flow, random state and CSRF protection, signed HttpOnly Secure SameSite cookies.
- Admin guilds validated via Discord OAuth `guilds` scope. Membership is re-evaluated on login (sessions expire after one hour).
- HTTPS domain required for browser cookie and OAuth redirect.
- Never put secrets in GitHub or screenshots.

## Starter limitations
- Anti-Nuke monitors repeated channel/role deletion and attempts timeout; cannot restore deleted objects.
- Anti-Raid alerts on join bursts, does not automatically kick/ban.
- Lockdown doesn't preserve prior channel overwrites; don't use it without understanding consequences.
- Warning history is in-memory and lost on restart.
- Dashboard does not expose moderation actions, only settings.
- Existing bot uses 20 slash commands, including /dashboard which currently returns a static message. Open the public Railway domain to use the real web dashboard.

## Health
`/health` returns JSON for service checks.
