# GUARD Recovery

Upload all files to the root of your GitHub repository.

Railway variables: DISCORD_BOT_TOKEN, GUILD_ID, DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, SESSION_SECRET, DASHBOARD_URL, BACKUP_DIR=/data/backups, SETTINGS_FILE=/data/guard_settings.json.

**Important:** Mount a Railway persistent volume at `/data` before enabling backups. Backups in the container's ephemeral filesystem disappear on redeploy. For disaster recovery also copy the backups to a separate secure location.

Commands:
- `/backup_create`: save roles/channels structure (overwrites previous snapshot)
- `/backup_status`: check snapshot
- `/recovery_preview`: count missing roles/channels
- `/recovery_full confirm:CONFIRM`: server owner only; recreate missing roles/channels

An automatic backup runs every 6 hours. It skips snapshots when an object in the previous snapshot has been deleted, to avoid overwriting the last known good snapshot during an attack. Manual backup overwrites the existing snapshot: use only when server is healthy.

Limitations: Cannot recover message history, original IDs, deleted member accounts, all server settings or every Discord channel type. Restored channel permissions referencing deleted roles are remapped when possible. Existing channels/roles are not modified. Restored roles and channels have new IDs. New roles may need manual position adjustments.

Ensure the bot has Manage Roles, Manage Channels, View Audit Log and relevant permissions, with a sufficiently high role. Never commit tokens or secrets to GitHub.
