import os
import secrets
import html
from urllib.parse import urlencode
from aiohttp import web, ClientSession
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

API = 'https://discord.com/api/v10'

async def start_dashboard(bot, settings, save_settings):
    client_id = os.getenv('DISCORD_CLIENT_ID', '')
    client_secret = os.getenv('DISCORD_CLIENT_SECRET', '')
    base = os.getenv('DASHBOARD_URL', '').rstrip('/')
    secret = os.getenv('SESSION_SECRET', '')
    if not secret or len(secret) < 32:
        raise RuntimeError('Set SESSION_SECRET to a random string of at least 32 characters')
    signer = URLSafeTimedSerializer(secret, salt='guard-session')
    app = web.Application(client_max_size=1024 * 20)

    def session(request):
        cookie = request.cookies.get('guard_session', '')
        try:
            return signer.loads(cookie, max_age=3600)
        except (BadSignature, SignatureExpired):
            return None

    def page(title, body, username=''):
        user = f'<span class="muted">{html.escape(username)}</span> · <a href="/logout">Logout</a>' if username else '<a href="/login">Login with Discord</a>'
        return web.Response(text=f'''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)} · GUARD</title><style>
        :root{{color-scheme:dark}}*{{box-sizing:border-box}}body{{background:#0b1020;color:#e9efff;font-family:system-ui,-apple-system,sans-serif;margin:0}}header{{padding:20px 5%;border-bottom:1px solid #27304a;display:flex;justify-content:space-between;gap:15px;flex-wrap:wrap}}a{{color:#a9c5ff}}main{{max-width:1020px;margin:35px auto;padding:0 20px}}h1{{font-size:30px}}h2{{font-size:20px}}.muted{{color:#a4b0c8}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:16px}}.card{{background:#151d33;border:1px solid #303d60;border-radius:15px;padding:22px;margin-bottom:16px}}.on{{color:#7ae2b2}}.off{{color:#ffad9f}}button,.btn{{background:#506ef0;color:white;border:0;padding:11px 16px;border-radius:9px;cursor:pointer;text-decoration:none;display:inline-block}}select,input{{background:#0d1529;color:white;border:1px solid #465473;padding:10px;border-radius:8px;max-width:100%}}form{{display:flex;gap:9px;align-items:center;flex-wrap:wrap;margin-top:12px}}small{{color:#a4b0c8}}.notice{{border-left:3px solid #e7ad65;padding:10px 14px;background:#30291f}}.tag{{padding:4px 10px;background:#243350;border-radius:8px}}
        </style></head><body><header><strong>🛡 GUARD SECURITY</strong><nav>{user}</nav></header><main>{body}</main></body></html>''', content_type='text/html')

    async def home(request):
        me = session(request)
        if not me:
            return page('Home','<h1>GUARD SECURITY</h1><p class="muted">Dashboard quản lý Anti-Nuke và Anti-Raid. Đăng nhập Discord để quản lý server bạn có quyền Administrator.</p><a class="btn" href="/login">Đăng nhập Discord</a>')
        cards = []
        for guild in bot.guilds:
            if str(guild.id) in me['guilds']:
                cards.append(f'<div class="card"><h2>{html.escape(guild.name)}</h2><p class="muted">Server ID: {guild.id}</p><a class="btn" href="/guild/{guild.id}">Quản lý</a></div>')
        return page('Servers','<h1>Chọn server</h1><div class="cards">'+(''.join(cards) or '<p>Không tìm thấy server mà bạn có quyền Administrator và bot đang tham gia.</p>')+'</div>',me['name'])

    async def login(request):
        if not client_id or not client_secret or not base:
            return page('Not configured','<h1>OAuth chưa cấu hình</h1><p>Thêm DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET và DASHBOARD_URL trên Railway.</p>')
        state = secrets.token_urlsafe(32)
        url = 'https://discord.com/oauth2/authorize?' + urlencode({'client_id':client_id,'redirect_uri':base+'/callback','response_type':'code','scope':'identify guilds','state':state})
        response = web.HTTPFound(url)
        response.set_cookie('oauth_state',state,max_age=600,httponly=True,secure=True,samesite='Lax')
        return response

    async def callback(request):
        code = request.query.get('code')
        state = request.query.get('state')
        if not code or not state or not secrets.compare_digest(state,request.cookies.get('oauth_state','')):
            raise web.HTTPForbidden(text='Invalid OAuth state')
        async with ClientSession() as client:
            async with client.post(API+'/oauth2/token',data={'client_id':client_id,'client_secret':client_secret,'grant_type':'authorization_code','code':code,'redirect_uri':base+'/callback'}) as resp:
                if resp.status != 200:
                    raise web.HTTPBadRequest(text='Discord OAuth token exchange failed')
                token = (await resp.json())['access_token']
            headers = {'Authorization':'Bearer '+token}
            async with client.get(API+'/users/@me',headers=headers) as resp:
                if resp.status != 200: raise web.HTTPBadRequest(text='Discord user lookup failed')
                user = await resp.json()
            async with client.get(API+'/users/@me/guilds',headers=headers) as resp:
                if resp.status != 200: raise web.HTTPBadRequest(text='Discord guild lookup failed')
                guilds = await resp.json()
        allowed = [str(g['id']) for g in guilds if g.get('owner') or int(g.get('permissions','0')) & 0x8]
        data = {'id':str(user['id']),'name':user['username'],'guilds':allowed,'csrf':secrets.token_urlsafe(24)}
        response = web.HTTPFound('/')
        response.set_cookie('guard_session',signer.dumps(data),max_age=3600,httponly=True,secure=True,samesite='Lax')
        response.del_cookie('oauth_state')
        return response

    def authorized(request):
        me = session(request)
        gid = request.match_info['gid']
        if not me: raise web.HTTPFound('/login')
        if gid not in me['guilds']: raise web.HTTPForbidden(text='Not a Discord administrator of this server')
        guild = bot.get_guild(int(gid))
        if not guild: raise web.HTTPNotFound(text='Bot not in server')
        return me,guild

    async def guild_page(request):
        me,guild = authorized(request)
        cfg = settings[guild.id]
        def card(label,key):
            val=cfg[key]
            return f'<div class="card"><h2>{label}</h2><p class="{ "on" if val else "off" }">{ "ON" if val else "OFF" }</p><form method="post" action="/guild/{guild.id}/toggle"><input type="hidden" name="csrf" value="{me["csrf"]}"><input type="hidden" name="key" value="{key}"><button name="enabled" value="{ "false" if val else "true" }">{ "Tắt" if val else "Bật" }</button></form></div>'
        options = ''.join(f'<option value="{c.id}" {"selected" if c.id==cfg["log"] else ""}>{html.escape(c.name)}</option>' for c in guild.text_channels)
        body = f'''<a href="/">← Servers</a><h1>{html.escape(guild.name)}</h1><p class="muted">Bot: {html.escape(str(bot.user)) if bot.user else "Starting"} · {guild.member_count} members</p><div class="cards">{card('Anti-Nuke','antinuke')}{card('Anti-Raid','antiraid')}</div>
        <div class="card"><h2>Security Logs</h2><form method="post" action="/guild/{guild.id}/logs"><input type="hidden" name="csrf" value="{me['csrf']}"><select name="channel">{options}</select><button>Lưu kênh log</button></form></div>
        <div class="card"><h2>Whitelist</h2><p class="muted">Trusted user IDs: {html.escape(', '.join(map(str,sorted(cfg['trusted']))) or 'None')}</p><form method="post" action="/guild/{guild.id}/whitelist"><input type="hidden" name="csrf" value="{me['csrf']}"><input name="user_id" placeholder="Discord User ID" required pattern="[0-9]{{15,22}}"><select name="action"><option value="add">Thêm</option><option value="remove">Xóa</option></select><button>Lưu</button></form></div>
        <p class="notice">Cấu hình lưu trong guard_settings.json. Railway cần gắn Volume để lưu qua lần deploy. Anti-Raid bản này chỉ cảnh báo; Anti-Nuke chưa khôi phục dữ liệu bị xóa.</p>'''
        return page(guild.name,body,me['name'])

    async def change(request):
        me,guild = authorized(request)
        data = await request.post()
        if not secrets.compare_digest(str(data.get('csrf','')),me['csrf']): raise web.HTTPForbidden(text='CSRF rejected')
        kind = request.match_info['kind']
        cfg = settings[guild.id]
        if kind == 'toggle':
            key = data.get('key')
            if key not in ('antinuke','antiraid'): raise web.HTTPBadRequest()
            cfg[key] = data.get('enabled') == 'true'
        elif kind == 'logs':
            try: channel_id=int(data.get('channel','0'))
            except ValueError: raise web.HTTPBadRequest()
            if not isinstance(guild.get_channel(channel_id),__import__('discord').TextChannel): raise web.HTTPBadRequest()
            cfg['log'] = channel_id
        elif kind == 'whitelist':
            try: uid=int(data.get('user_id','0'))
            except ValueError: raise web.HTTPBadRequest()
            if uid <= 0 or data.get('action') not in ('add','remove'): raise web.HTTPBadRequest()
            (cfg['trusted'].add if data['action']=='add' else cfg['trusted'].discard)(uid)
        else: raise web.HTTPNotFound()
        save_settings()
        raise web.HTTPSeeOther(f'/guild/{guild.id}')

    async def logout(request):
        response=web.HTTPFound('/')
        response.del_cookie('guard_session')
        return response

    async def health(request):
        return web.json_response({'status':'ok','discord_ready':bot.is_ready()})

    app.router.add_get('/',home)
    app.router.add_get('/login',login)
    app.router.add_get('/callback',callback)
    app.router.add_get('/logout',logout)
    app.router.add_get('/health',health)
    app.router.add_get('/guild/{gid}',guild_page)
    app.router.add_post('/guild/{gid}/{kind}',change)
    runner=web.AppRunner(app)
    await runner.setup()
    site=web.TCPSite(runner,'0.0.0.0',int(os.getenv('PORT','8080')))
    await site.start()
    print('Dashboard listening on port',os.getenv('PORT','8080'))
