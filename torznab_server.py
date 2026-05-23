#!/usr/bin/env python3
"""
Torznab-compatible HTTP server that exposes Telegram channels as a searchable indexer.
Implements the Torznab/Newznab API so Sonarr, Radarr, and Prowlarr can search Telegram.

Add as a custom Torznab indexer in Prowlarr or directly in Sonarr/Radarr:
  URL: http://<host>:<port>/api
  API key: whatever you set in [Torznab] api_key

Workflow:
  1. Sonarr searches -> our server searches Telegram channels via iter_messages()
  2. Sonarr grabs a result -> our /download endpoint triggers the Telegram download
  3. File downloads to download_path (same as the reaction-based flow)
  4. Sonarr imports it via DownloadedEpisodesScan (already wired up)

Note: The NZB stub returned on grab will fail in SABnzbd/NZBGet — that is expected.
The actual file arrives via Telegram. Sonarr imports it through the watched folder scan.
"""

import asyncio
import logging
from datetime import timezone
from pathlib import Path
import xml.etree.ElementTree as ET

from aiohttp import web
from telethon.tl.types import MessageMediaDocument

VIDEO_EXTENSIONS = frozenset({'.mkv', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v'})
TORZNAB_NS = 'http://torznab.com/schemas/2015/feed'

CAPS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<caps>
  <server version="1.0" title="Telegram Indexer" strapline="Telegram channels as Torznab indexer"/>
  <limits max="100" default="50"/>
  <registration available="no" open="no"/>
  <searching>
    <search available="yes" supportedParams="q"/>
    <tv-search available="yes" supportedParams="q,season,ep"/>
    <movie-search available="yes" supportedParams="q"/>
    <music-search available="no" supportedParams="q"/>
    <audio-search available="no" supportedParams="q"/>
    <book-search available="no" supportedParams="q"/>
  </searching>
  <categories>
    <category id="5000" name="TV">
      <subcat id="5040" name="TV/HD"/>
      <subcat id="5030" name="TV/SD"/>
    </category>
    <category id="2000" name="Movies">
      <subcat id="2040" name="Movies/HD"/>
      <subcat id="2030" name="Movies/SD"/>
    </category>
  </categories>
</caps>"""


def _filename_from_message(message):
    if not message.media or not isinstance(message.media, MessageMediaDocument):
        return None
    for attr in message.media.document.attributes:
        if hasattr(attr, 'file_name'):
            return attr.file_name
    ext = message.media.document.mime_type.split('/')[-1]
    return f'telegram_{message.id}.{ext}'


def _is_video_message(message):
    fname = _filename_from_message(message)
    return fname is not None and Path(fname).suffix.lower() in VIDEO_EXTENSIONS


def _file_size(message):
    if message.media and isinstance(message.media, MessageMediaDocument):
        return message.media.document.size
    return 0


def _rss_date(dt):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime('%a, %d %b %Y %H:%M:%S %z')


def _stub_nzb(filename):
    """Minimal valid NZB returned when Sonarr grabs a result.

    The download client (SABnzbd/NZBGet) will fail on this — that is by design.
    The actual file arrives independently via the Telegram download triggered on grab.
    """
    safe = filename.replace('&', '&amp;').replace('<', '&lt;').replace('"', '&quot;')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE nzb PUBLIC "-//newzBin//DTD NZB 1.1//EN"'
        ' "http://www.newzbin.com/DTD/nzb/nzb-1.1.dtd">\n'
        '<nzb xmlns="http://www.newzbin.com/DTD/2003/nzb">\n'
        f'  <head><meta type="title">{safe}</meta></head>\n'
        f'  <file poster="telegram" date="0" subject="{safe}">\n'
        '    <groups><group>alt.binaries.telegram</group></groups>\n'
        '    <segments/>\n'
        '  </file>\n'
        '</nzb>'
    )


class TorznabServer:
    def __init__(self, downloader):
        self.downloader = downloader
        cfg = downloader.config

        self.host = cfg.get('Torznab', 'host', fallback='0.0.0.0')
        self.port = cfg.getint('Torznab', 'port', fallback=9117)
        self.api_key = cfg.get('Torznab', 'api_key', fallback='')
        self.base_url = cfg.get('Torznab', 'base_url', fallback='http://localhost:9117').rstrip('/')

        raw_chats = cfg.get('Torznab', 'search_chats', fallback='').strip()
        if raw_chats:
            self.search_chats = [c.strip() for c in raw_chats.split(',') if c.strip()]
        else:
            self.search_chats = list(downloader.monitored_chats)

        self.logger = logging.getLogger('TorznabServer')

        self.app = web.Application()
        self.app.router.add_get('/api', self._handle_api)
        self.app.router.add_get('/download', self._handle_download)

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _authorized(self, request):
        return not self.api_key or request.query.get('apikey') == self.api_key

    # ------------------------------------------------------------------
    # /api
    # ------------------------------------------------------------------

    async def _handle_api(self, request):
        if not self._authorized(request):
            return web.Response(status=401, text='Unauthorized')

        t = request.query.get('t', '')

        if t == 'caps':
            return web.Response(text=CAPS_XML, content_type='application/xml')

        if t in ('search', 'tvsearch', 'movie'):
            xml = await self._search_xml(request.query)
            return web.Response(text=xml, content_type='application/xml')

        return web.Response(
            status=400,
            content_type='application/xml',
            text='<?xml version="1.0"?><error code="202" description="No such function"/>',
        )

    async def _search_xml(self, params):
        q = params.get('q', '').strip()
        season = params.get('season', '').strip()
        ep = params.get('ep', '').strip()
        limit = min(int(params.get('limit', '50')), 100)

        # Build the Telegram search string from Torznab params
        if q and season and ep:
            try:
                query = f'{q} S{int(season):02d}E{int(ep):02d}'
            except ValueError:
                query = q
        elif q and season:
            try:
                query = f'{q} S{int(season):02d}'
            except ValueError:
                query = q
        else:
            query = q

        self.logger.info(f"Torznab search: '{query}'")
        results = await self._search_channels(query, limit)
        return self._build_rss(results, query)

    # ------------------------------------------------------------------
    # Telegram search
    # ------------------------------------------------------------------

    async def _search_channels(self, query, limit):
        client = self.downloader.client
        results = []

        if not self.search_chats:
            self.logger.warning('No search_chats configured — cannot search')
            return results

        per_chat = max(10, limit // len(self.search_chats))

        for chat_ref in self.search_chats:
            try:
                entity = await client.get_entity(chat_ref)
                chat_title = getattr(entity, 'title', str(chat_ref))
                chat_id = str(entity.id)
                ref = getattr(entity, 'username', None) or chat_id

                count = 0
                async for msg in client.iter_messages(entity, search=query, limit=per_chat):
                    if _is_video_message(msg):
                        results.append({
                            'title': _filename_from_message(msg),
                            'guid': f'tg-{chat_id}-{msg.id}',
                            'date': msg.date,
                            'size': _file_size(msg),
                            'chat_id': chat_id,
                            'chat_ref': ref,
                            'chat_title': chat_title,
                            'msg_id': msg.id,
                        })
                        count += 1

                self.logger.info(f"  '{chat_title}': {count} hits")

            except Exception as e:
                self.logger.error(f"Search failed for {chat_ref}: {e}")

        results.sort(key=lambda r: r['date'], reverse=True)
        return results[:limit]

    # ------------------------------------------------------------------
    # RSS / Torznab XML builder
    # ------------------------------------------------------------------

    def _download_url(self, r):
        url = (
            f"{self.base_url}/download"
            f"?chat_id={r['chat_id']}"
            f"&msg_id={r['msg_id']}"
            f"&chat_ref={r['chat_ref']}"
        )
        if self.api_key:
            url += f'&apikey={self.api_key}'
        return url

    def _build_rss(self, results, query):
        rss = ET.Element('rss', {
            'version': '2.0',
            'xmlns:atom': 'http://www.w3.org/2005/Atom',
            'xmlns:torznab': TORZNAB_NS,
        })
        ch = ET.SubElement(rss, 'channel')
        ET.SubElement(ch, 'title').text = 'Telegram Indexer'
        ET.SubElement(ch, 'description').text = f'Results for: {query}'
        ET.SubElement(ch, 'link').text = self.base_url

        for r in results:
            url = self._download_url(r)
            item = ET.SubElement(ch, 'item')
            ET.SubElement(item, 'title').text = r['title']
            ET.SubElement(item, 'guid').text = r['guid']
            ET.SubElement(item, 'link').text = url
            ET.SubElement(item, 'pubDate').text = _rss_date(r['date'])
            ET.SubElement(item, 'size').text = str(r['size'])
            ET.SubElement(item, 'description').text = f"Telegram: {r['chat_title']}"
            ET.SubElement(item, 'enclosure', {
                'url': url,
                'length': str(r['size']),
                'type': 'application/x-nzb',
            })
            ET.SubElement(item, f'{{{TORZNAB_NS}}}attr', {'name': 'category', 'value': '5040'})
            ET.SubElement(item, f'{{{TORZNAB_NS}}}attr', {'name': 'size', 'value': str(r['size'])})

        return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(rss, encoding='unicode')

    # ------------------------------------------------------------------
    # /download  (grab endpoint)
    # ------------------------------------------------------------------

    async def _handle_download(self, request):
        if not self._authorized(request):
            return web.Response(status=401, text='Unauthorized')

        chat_id = request.query.get('chat_id')
        chat_ref = request.query.get('chat_ref')
        msg_id = request.query.get('msg_id')

        if not msg_id or not (chat_id or chat_ref):
            return web.Response(status=400, text='Missing chat_id/chat_ref or msg_id')

        try:
            client = self.downloader.client
            lookup = chat_ref if chat_ref else int(chat_id)
            entity = await client.get_entity(lookup)
            chat_title = getattr(entity, 'title', str(lookup))
            message = await client.get_messages(entity, ids=int(msg_id))

            if not message:
                return web.Response(status=404, text='Message not found')

            filename = _filename_from_message(message) or f'telegram_{msg_id}.mkv'
            self.logger.info(f"Grab: '{filename}' from '{chat_title}'")

            asyncio.create_task(self.downloader.download_media(message, chat_title))

            return web.Response(
                text=_stub_nzb(filename),
                content_type='application/x-nzb',
                headers={'Content-Disposition': f'attachment; filename="{filename}.nzb"'},
            )

        except Exception as e:
            self.logger.error(f"Grab failed: {e}", exc_info=True)
            return web.Response(status=500, text=str(e))

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    async def start(self):
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        self.logger.info(f"Torznab server: http://{self.host}:{self.port}/api")
        if self.api_key:
            self.logger.info('Torznab API key: configured')
        if self.search_chats:
            self.logger.info(f"Torznab search chats: {self.search_chats}")
        else:
            self.logger.warning('Torznab: no search_chats — searches will return empty results')
