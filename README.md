# Signal Reader

Self-hosted RSS reading room with cached article text, source filters, search, persistent read/unread state, article images and podcast audio when supplied. No AI or API key required.

## Start

```bash
unzip signal-reader.zip
cd signal-reader
docker compose up -d --build
# Open http://YOUR-SERVER-IP:8090
```

The first collection starts automatically. Allow several minutes: up to 30 recent entries per source are fetched sequentially with timeouts. UPDATE starts a background collection; repeated clicks never overlap it. The UI checks status every five seconds and refreshes the list when collection finishes, preserving open articles until you collapse them.

Scheduled collection runs at 00:00, 06:00, 12:00 and 18:00 UTC. Startup and manual updates are additional runs. Only one container/worker should use this database. Missed runs while stopped are replaced by startup collection.

## Sources and content

Edit feeds.json to add/remove trusted HTTP(S) RSS/Atom feeds. Changes apply on the next update. The bundled catalog contains 28 feeds grouped into US, World, Florida, Tech & security, Science, and Networking. See the catalog below. Publisher availability can change. Feed health at the bottom shows source errors independently.

Trafilatura extracts publicly accessible article text. Extraction is best effort, not a guarantee of complete text. Feed content/excerpts remain available if the page blocks access. No paywall bypass or transcript generation. Original links and source attribution remain visible. Third-party HTML is converted to text and rendered as text, not executable markup. Images/audio load directly from their original sites and are not stored offline. Their availability depends on the publisher and browser mixed-content restrictions.

Articles are deduplicated by normalized URL (tracking parameters removed). Existing articles are retained indefinitely and are not re-extracted automatically. Different URLs for syndicated stories remain separate. No automatic deletion. Search covers cached title and body. Pagination loads 50 stories at a time. Read state is shared by all users of this instance.

## HAProxy

Use a dedicated hostname; route its root to the reader. Example to merge into your existing configuration (replace host/IP):

```haproxy
# In your existing HTTPS frontend:
acl reader_host hdr(host) -i reader.example.com
use_backend signal_reader if reader_host

backend signal_reader
    option httpchk GET /healthz
    server reader 192.168.0.209:8090 check
```

TLS can terminate at HAProxy. No WebSocket configuration needed. This build expects the URL root, not a /reader subpath. Standard HTTP polling works behind HAProxy. Place any Internet-facing authentication at the proxy; the application itself is a trusted-LAN, shared reader with no accounts. Anyone who can reach it can read cached content and trigger updates. Feeds are configured only by editing the server-side file; only add trusted feeds.

## Operations

```bash
docker compose logs -f reader
docker compose restart reader
docker compose down
# Data remains in reader-data. Do not use down -v unless deleting the cache.
```

For a consistent backup, stop the service and back up the Docker volume, then start it again. For SELinux bind-mount denials, change the feeds mount to :ro,Z. Port 8090 can be changed in compose.yaml.

## Local verification

```bash
pip install -r requirements.txt pytest
pytest -q
```

Tests mock publisher HTTP responses to verify ingestion, fallback, deduplication, scheduling boundaries, API operations and persistence without depending on live publishers.

## Layout and preferences

Articles appear as full-width summary rows. Click a summary to expand the cached article inline. Click the summary or article body again to collapse it. Multiple articles can remain open. Links and audio controls work normally without collapsing the article; selecting text also avoids collapse. There is no Mark unread button or click instruction. Collapsing pauses audio. Keyboard users can expand/collapse with the headline button.

Preferences / Sources opens the appearance controls and source checkboxes. Dark is the default, with Light, Sepia, and Match device available. Adjust text size, font, spacing, reading width, compact headlines, images, and automatic read marking. Article headers show estimated reading time.

Category buttons, search, source selection, and unread filtering apply to the entire cache before pagination. Source checkboxes control which cached stories appear in this browser; all configured feeds are still collected by the server. Preferences and source choices persist per browser using localStorage. Read state remains shared. Reset defaults resets both appearance and source choices.

Custom feeds without a category, and cached sources removed from feeds.json, appear under Other. Add a category field to each custom entry to group it. Source names should be unique and stable because cached articles identify their source by name.

## Upgrade

Replace the application files in your existing compose directory, keeping its directory/project name and existing volume. Merge feeds.json first if you customized it; include the new category fields and sources you want.

```bash
# Run in the existing signal-reader directory after replacing its files.
docker compose up -d --build
# Hard-refresh the browser to load the new scripts and styles.
```

The database schema and Docker volume are unchanged. No cache migration is needed. Do not use docker compose down -v. The first collection of the expanded catalog can take a while because article extraction is sequential; subsequent runs skip cached URLs.

## Bundled sources

- **US:** NPR US News, PBS NewsHour, CBS US News, The Guardian US, ABC News, NBC News.
- **World:** BBC News, NPR World, BBC World, The Guardian World, Al Jazeera, France 24, Deutsche Welle, ABC Australia.
- **Florida:** WUSF, WMFE, WFTV, ClickOrlando.
- **Tech & security:** Ars Technica, BleepingComputer, Krebs on Security, The Register.
- **Science:** NASA, ScienceDaily, Quanta, Phys.org.
- **Networking:** Packet Pushers, Cloudflare.

The 13 added feeds returned parseable RSS/Atom with entries during this update. CBC was omitted after timeouts. NHK was omitted because a working English feed was not verified.

## Verification of this update

Five backend tests passed, including category/exclusion filtering and compatibility with uncategorized cached sources. JavaScript DOM checks passed for expansion, body-click collapse, reopening, read marking, source exclusions, category filtering, and preference persistence. JavaScript syntax checks passed. Browser rendering could not be verified because the Chromium download failed; Docker is unavailable in the editing environment, so the image build was not run.
