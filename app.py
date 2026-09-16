import asyncio, calendar, contextlib, json, os, sqlite3, time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, urljoin, parse_qsl, urlencode
from contextlib import asynccontextmanager
import httpx, feedparser, trafilatura
from lxml import html
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).parent
DATA = Path(os.getenv('DATA_DIR', '/data'))
INTERVAL = 21600
state = {'running': False, 'last_update': None, 'next_update': None, 'sources': [], 'error': None}
job = None

def db():
    c = sqlite3.connect(DATA / 'reader.sqlite', timeout=30)
    c.row_factory = sqlite3.Row
    return c

def init():
    DATA.mkdir(parents=True, exist_ok=True)
    with db() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.execute('CREATE TABLE IF NOT EXISTS articles (id INTEGER PRIMARY KEY, url TEXT UNIQUE, source TEXT, title TEXT, published REAL, body TEXT, mode TEXT, image TEXT, audio TEXT, is_read INTEGER DEFAULT 0)')
        c.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)')
        row = c.execute("SELECT value FROM meta WHERE key='status'").fetchone()
        if row:
            state.update(json.loads(row[0]))
            state['running'] = False

def safe_url(url):
    try:
        p = urlsplit(url)
        return url if p.scheme in ('http', 'https') and p.hostname and not p.username else ''
    except ValueError:
        return ''

def canonical(url):
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc.lower(), p.path, urlencode([(k,v) for k,v in parse_qsl(p.query) if not k.startswith('utm_') and k not in ('fbclid','gclid')]), ''))

def plain(value):
    try:
        doc = html.fromstring(value or '<p></p>')
        for n in doc.xpath('//script|//style'): n.drop_tree()
        return doc.text_content().strip()
    except Exception:
        return ''

async def fetch(client, url):
    if not safe_url(url): raise ValueError('Invalid HTTP URL')
    async with client.stream('GET', url) as r:
        r.raise_for_status()
        chunks, size = [], 0
        async for chunk in r.aiter_bytes():
            size += len(chunk)
            if size > 5_000_000: raise ValueError('Response exceeds 5 MB')
            chunks.append(chunk)
        return b''.join(chunks)

async def refresh():
    state['running'] = True
    state['error'] = None
    reports = []
    try:
        feeds = json.loads(Path(os.getenv('FEEDS_FILE', ROOT / 'feeds.json')).read_text())
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, max_redirects=5, headers={'User-Agent':'SignalReader/1.0 (personal RSS reader)'}) as client:
            for feed in feeds:
                report = {'name':feed['name'], 'added':0, 'error':None, 'excerpts':0}
                reports.append(report)
                state['sources'] = reports
                try:
                    parsed = feedparser.parse(await fetch(client, feed['url']))
                    if not parsed.version: raise ValueError('Response is not an RSS/Atom feed')
                    for entry in parsed.entries[:int(os.getenv('MAX_PER_FEED', '30'))]:
                        url = safe_url(entry.get('link',''))
                        if not url: continue
                        url = canonical(url)
                        with db() as c:
                            if c.execute('SELECT 1 FROM articles WHERE url=?',(url,)).fetchone(): continue
                        content = entry.get('content', [{}])[0].get('value','')
                        body = plain(content or entry.get('summary',''))
                        mode = 'Feed content' if content else 'Excerpt'
                        image = audio = ''
                        for enclosure in entry.get('enclosures',[]):
                            if enclosure.get('type','').startswith('audio/'):
                                audio = safe_url(enclosure.get('href',''))
                        try:
                            page = await fetch(client,url)
                            extracted = await asyncio.to_thread(trafilatura.extract, page, url=url, include_comments=False, include_tables=True)
                            if extracted and len(extracted) > max(200,len(body)):
                                body, mode = extracted, 'Extracted article'
                            doc = html.fromstring(page)
                            pics = doc.xpath('//meta[@property="og:image"]/@content')
                            if pics: image = safe_url(urljoin(url,pics[0]))
                        except Exception:
                            pass  # Preserve the feed text when the publisher blocks extraction.
                        if mode == 'Excerpt': report['excerpts'] += 1
                        stamp = entry.get('published_parsed') or entry.get('updated_parsed')
                        published = calendar.timegm(stamp) if stamp else time.time()
                        with db() as c:
                            c.execute('INSERT OR IGNORE INTO articles(url,source,title,published,body,mode,image,audio) VALUES(?,?,?,?,?,?,?,?)', (url,feed['name'],plain(entry.get('title','Untitled')),published,body or 'Article text unavailable. Open the original article.',mode,image,audio))
                        report['added'] += 1
                        await asyncio.sleep(.2)
                except Exception as e:
                    report['error'] = str(e)[:200]
        state['last_update'] = time.time()
    except Exception as e:
        state['error'] = str(e)[:200]
    finally:
        state['running'] = False
        state['sources'] = reports
        with db() as c:
            c.execute("INSERT OR REPLACE INTO meta VALUES('status',?)", (json.dumps(state),))

def start_refresh():
    global job
    if job and not job.done(): return False
    job = asyncio.create_task(refresh())
    state['running'] = True
    return True

async def scheduler():
    while True:
        state['next_update'] = (int(time.time()) // INTERVAL + 1) * INTERVAL
        await asyncio.sleep(max(1, state['next_update'] - time.time()))
        start_refresh()

@asynccontextmanager
async def lifespan(app):
    init()
    timer = asyncio.create_task(scheduler())
    if os.getenv('AUTO_UPDATE','1') == '1': start_refresh()
    yield
    timer.cancel()
    if job: job.cancel()
    for task in [timer, job]:
        if task:
            with contextlib.suppress(asyncio.CancelledError): await task

app = FastAPI(lifespan=lifespan)

@app.middleware('http')
async def headers(request: Request, call_next):
    if request.method == 'POST' and request.headers.get('x-reader-request') != '1':
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail':'Missing reader request header'}, status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' https: http:; media-src https: http:; style-src 'self'; script-src 'self'; frame-ancestors 'self'"
    return response

@app.get('/healthz')
def health(): return {'status':'ok'}

@app.get('/api/status')
def status(): return state

@app.post('/api/update', status_code=202)
async def update(): return {'started':start_refresh()}

def feed_catalog():
    feeds = json.loads(Path(os.getenv('FEEDS_FILE', ROOT / 'feeds.json')).read_text())
    catalog = {f['name']: {'name': f['name'], 'category': f.get('category', 'Other')} for f in feeds}
    with db() as c:
        for row in c.execute('SELECT DISTINCT source FROM articles'):
            catalog.setdefault(row[0], {'name': row[0], 'category': 'Other'})
    return list(catalog.values())

@app.get('/api/feeds')
def feeds():
    return feed_catalog()

@app.get('/api/articles')
def articles(source: str = '', q: str = '', unread: bool = False, offset: int = 0, category: str = '', excluded: str = '[]'):
    clauses, args = [], []
    try:
        excluded_names = json.loads(excluded)
        if not isinstance(excluded_names, list) or len(excluded_names) > 500 or any(not isinstance(n, str) for n in excluded_names):
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(400, 'Invalid excluded sources')
    if excluded_names:
        clauses.append('source NOT IN (' + ','.join('?' for _ in excluded_names) + ')')
        args.extend(excluded_names)
    if category:
        names = [f['name'] for f in feed_catalog() if f['category'] == category]
        if names:
            clauses.append('source IN (' + ','.join('?' for _ in names) + ')')
            args.extend(names)
        else:
            clauses.append('0')
    if source: clauses.append('source=?'); args.append(source)
    if q: clauses.append('(title LIKE ? OR body LIKE ?)'); args.extend(['%'+q+'%']*2)
    if unread: clauses.append('is_read=0')
    where = ' WHERE '+' AND '.join(clauses) if clauses else ''
    with db() as c:
        total = c.execute('SELECT count(*) FROM articles'+where,args).fetchone()[0]
        rows = c.execute('SELECT id,url,source,title,published,mode,is_read,substr(body,1,220) AS excerpt FROM articles'+where+' ORDER BY published DESC,id DESC LIMIT 50 OFFSET ?',args+[max(0,offset)]).fetchall()
        sources = [r[0] for r in c.execute('SELECT DISTINCT source FROM articles ORDER BY source')]
    return {'items':[dict(r) for r in rows], 'total':total, 'sources':sources}

@app.get('/api/articles/{article_id}')
def article(article_id: int):
    with db() as c: row = c.execute('SELECT * FROM articles WHERE id=?',(article_id,)).fetchone()
    if not row: raise HTTPException(404)
    return dict(row)

@app.post('/api/articles/{article_id}/read')
def read(article_id: int, value: bool = True):
    with db() as c: c.execute('UPDATE articles SET is_read=? WHERE id=?',(int(value),article_id))
    return {'ok':True}

@app.get('/')
def index(): return FileResponse(ROOT / 'static/index.html')

app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
