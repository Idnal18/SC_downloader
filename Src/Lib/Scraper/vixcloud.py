import re
from playwright.sync_api import sync_playwright


def _parse_master(master_content, prefer_audio_lang="ita"):
    """
    Parse a vixcloud master M3U8. Returns (video_url, audio_url).
    Picks the highest RESOLUTION video and the preferred audio language.
    """
    lines = master_content.splitlines()

    # Video: pick highest vertical resolution among EXT-X-STREAM-INF entries
    video_url = None
    best_res = -1
    for i, line in enumerate(lines):
        if line.startswith('#EXT-X-STREAM-INF'):
            m = re.search(r'RESOLUTION=\d+x(\d+)', line)
            res = int(m.group(1)) if m else 0
            if i + 1 < len(lines):
                url_line = lines[i + 1].strip()
                if url_line and not url_line.startswith('#') and res > best_res:
                    best_res = res
                    video_url = url_line

    # Audio: prefer requested language, fallback to first available
    audio_url = None
    audio_fallback = None
    for line in lines:
        if line.startswith('#EXT-X-MEDIA') and 'TYPE=AUDIO' in line:
            uri_m = re.search(r'URI="([^"]+)"', line)
            if not uri_m:
                continue
            uri = uri_m.group(1)
            if f'LANGUAGE="{prefer_audio_lang}"' in line or f'rendition={prefer_audio_lang}' in uri:
                audio_url = uri
            elif audio_fallback is None:
                audio_fallback = uri

    return video_url, (audio_url or audio_fallback), best_res


def get_video_info(embed_url: str, prefer_audio_lang: str = "ita") -> dict:
    """
    Open the vixcloud embed page with Playwright, intercept the master playlist
    (which lists every quality with a valid token) and the AES key request.
    Returns the best-quality video URL, preferred audio URL and the key URL.
    """
    results = {'video_url': None, 'audio_url': None, 'key_url': None, 'resolution': None}
    master_bodies = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()

        def on_response(resp):
            url = resp.url
            # The master playlist is the one WITHOUT type=video/audio/subtitle
            if 'vixcloud.co/playlist' in url and 'type=' not in url:
                try:
                    body = resp.text()
                    if '#EXT-X-STREAM-INF' in body:
                        master_bodies.append(body)
                except Exception:
                    pass

        def on_request(req):
            if 'enc.key' in req.url:
                results['key_url'] = req.url if req.url.startswith('http') else f'https://vixcloud.co{req.url}'

        page.on('response', on_response)
        page.on('request', on_request)

        page.goto(embed_url, wait_until='networkidle', timeout=30000)

        # Wait up to 8s for the master playlist to be fetched by the player
        for _ in range(8):
            if master_bodies:
                break
            page.wait_for_timeout(1000)

        browser.close()

    if master_bodies:
        video_url, audio_url, res = _parse_master(master_bodies[-1], prefer_audio_lang)
        results['video_url'] = video_url
        results['audio_url'] = audio_url
        results['resolution'] = res

    return results
