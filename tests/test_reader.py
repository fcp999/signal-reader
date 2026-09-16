import asyncio, time
import pytest
from fastapi.testclient import TestClient
import app

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(app,'DATA',tmp_path)
    monkeypatch.setenv('AUTO_UPDATE','0')
    app.state.update(running=False,last_update=None,next_update=None,sources=[],error=None)
    app.job=None
    with TestClient(app.app) as c: yield c

def test_ingest_fallback_dedupe_and_read(client,monkeypatch):
    async def fetch(c,url):
        if url.endswith('/rss/') or 'feed' in url or url.endswith('/index') or url.endswith('.xml'):
            return b'<rss version="2.0"><channel><title>Test</title><item><title>Story</title><link>https://example.com/story?utm_source=test</link><description>&lt;p&gt;Fallback text&lt;/p&gt;</description></item></channel></rss>'
        raise ValueError('Publisher unavailable')
    monkeypatch.setattr(app,'fetch',fetch)
    asyncio.run(app.refresh())
    asyncio.run(app.refresh())
    d=client.get('/api/articles').json()
    assert d['total']==1
    a=client.get('/api/articles/1').json()
    assert a['body']=='Fallback text' and a['mode']=='Excerpt'
    assert a['url']=='https://example.com/story'
    assert client.post('/api/update').status_code==403
    assert client.post('/api/articles/1/read',headers={'X-Reader-Request':'1'}).status_code==200
    assert client.get('/api/articles?unread=true').json()['total']==0
    assert client.get('/api/articles?q=Fallback').json()['total']==1
    app.init()
    assert client.get('/api/articles/1').json()['is_read']==1
    assert client.get('/healthz').status_code==200
    assert client.get('/').status_code==200

def test_safe_text_and_urls():
    assert app.plain('<script>alert(1)</script><p>Text</p>')=='Text'
    assert not app.safe_url('javascript:alert(1)')
    assert not app.safe_url('file:///etc/passwd')

def test_update_does_not_overlap(client,monkeypatch):
    async def slow(): await asyncio.sleep(60)
    monkeypatch.setattr(app,'refresh',slow)
    headers={'X-Reader-Request':'1'}
    assert client.post('/api/update',headers=headers).json()['started']
    assert not client.post('/api/update',headers=headers).json()['started']
    s=client.get('/api/status').json()
    assert s['next_update'] % 21600 == 0

def test_extracted_article_and_media(client,monkeypatch):
    async def fetch(c,url):
        if url=='https://example.com/article': return b'<html><head><meta property="og:image" content="/photo.jpg"></head><body><p>Article</p></body></html>'
        return b'<rss version="2.0"><channel><title>Test</title><item><title>Full story</title><link>https://example.com/article</link><description>Short</description><enclosure url="https://example.com/audio.mp3" type="audio/mpeg" length="123"/></item></channel></rss>'
    monkeypatch.setattr(app,'fetch',fetch)
    monkeypatch.setattr(app.trafilatura,'extract',lambda *a,**k:'Extracted paragraph. '*40)
    asyncio.run(app.refresh())
    a=client.get('/api/articles/1').json()
    assert a['mode']=='Extracted article'
    assert a['image']=='https://example.com/photo.jpg'
    assert a['audio']=='https://example.com/audio.mp3'

def test_source_category_filters_and_legacy_catalog(client):
    with app.db() as c:
        for source in ['NASA', 'Packet Pushers', 'Custom old feed']:
            c.execute('INSERT INTO articles(url,source,title,body,published) VALUES(?,?,?,?,?)',('https://example.com/'+source,source,'A story','Content',time.time()))
    assert client.get('/api/articles?category=Science').json()['total']==1
    assert client.get('/api/articles?category=Unknown').json()['total']==0
    assert client.get('/api/articles',params={'excluded':'["NASA", "Packet Pushers"]'}).json()['total']==1
    assert client.get('/api/articles',params={'excluded':'["NASA"]','category':'Science'}).json()['total']==0
    assert client.get('/api/articles',params={'excluded':'{}'}).status_code==400
    catalog=client.get('/api/feeds').json()
    assert {'name':'Custom old feed','category':'Other'} in catalog
