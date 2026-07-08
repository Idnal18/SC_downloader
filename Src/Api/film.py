import requests, os, sys
from bs4 import BeautifulSoup

from Src.Util.headers import get_headers
from Src.Util.console import console
from Src.Util.os import sanitize_filename
from Src.Lib.FFmpeg.my_m3u8 import download_m3u8
from Src.Lib.Scraper.vixcloud import get_video_info


def get_embed_url(id_title, domain, session):
    req = session.get(f"https://{domain}/it/iframe/{id_title}", headers={"User-agent": get_headers()})
    if req.ok:
        return BeautifulSoup(req.text, "lxml").find("iframe").get("src")
    console.log(f"[red]Error: {req.status_code}")
    sys.exit(0)


def main_dw_film(id_film, title_name, year, domain, session):
    embed_url = get_embed_url(id_film, domain, session)
    console.print("[cyan]Opening browser to fetch stream info...")
    info = get_video_info(embed_url)

    if not info['video_url']:
        console.log("[red]Could not find video stream")
        sys.exit(0)

    console.print(f"[blue]Quality => [green]{info.get('resolution')}p")
    console.print(f"[blue]Video URL found => [green]{info['video_url'][:60]}...")

    key_hex = None
    if info['key_url']:
        r = requests.get(info['key_url'], headers={'referer': embed_url})
        if r.ok:
            key_hex = "".join(["{:02x}".format(c) for c in r.content])

    clean_name = sanitize_filename(title_name)
    movie_folder_name = f"{clean_name} ({year})" if year else clean_name
    movie_dir = os.path.join("videos", movie_folder_name)
    os.makedirs(movie_dir, exist_ok=True)
    mkv_path = os.path.join(movie_dir, movie_folder_name + ".mkv")

    download_m3u8(
        m3u8_index=info['video_url'],
        m3u8_audio=info['audio_url'],
        key=key_hex,
        output_filename=mkv_path
    )
