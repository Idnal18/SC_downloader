import requests, os, sys
from bs4 import BeautifulSoup

from Src.Util.headers import get_headers
from Src.Util.console import console, msg
from Src.Util.os import sanitize_filename
from Src.Lib.FFmpeg.my_m3u8 import download_m3u8
from Src.Lib.Scraper.vixcloud import get_video_info


def get_token(id_tv, domain, session):
    session.get(f"https://{domain}/it/watch/{id_tv}")
    return requests.utils.unquote(session.cookies.get('XSRF-TOKEN', ''))

def get_info_tv(id_film, title_name, site_version, domain, session):
    xsrf = requests.utils.unquote(session.cookies.get('XSRF-TOKEN', ''))
    req = session.get(f"https://{domain}/it/titles/{id_film}-{title_name}", headers={
        'X-Inertia': 'true',
        'X-Inertia-Version': site_version,
        'X-XSRF-TOKEN': xsrf,
        'User-Agent': get_headers()
    })
    if req.ok:
        return req.json()['props']['title']['seasons_count']
    console.log(f"[red]Error: {req.status_code}")
    sys.exit(0)

def get_info_season(tv_id, tv_name, domain, version, token, n_stagione, session):
    xsrf = requests.utils.unquote(session.cookies.get('XSRF-TOKEN', ''))
    req = session.get(f'https://{domain}/it/titles/{tv_id}-{tv_name}/season-{n_stagione}', headers={
        'authority': f'{domain}', 'referer': f'https://{domain}/it/titles/{tv_id}-{tv_name}',
        'user-agent': get_headers(), 'x-inertia': 'true', 'x-inertia-version': version, 'x-xsrf-token': xsrf,
    })
    if req.ok:
        return [{'id': ep['id'], 'n': ep['number'], 'name': ep['name']} for ep in req.json()['props']['loadedSeason']['episodes']]
    console.log(f"[red]Error: {req.status_code}")
    sys.exit(0)

def get_embed_url(tv_id, ep_id, domain, session):
    xsrf = requests.utils.unquote(session.cookies.get('XSRF-TOKEN', ''))
    req = session.get(f'https://{domain}/it/iframe/{tv_id}', params={'episode_id': ep_id, 'next_episode': '1'}, headers={
        'referer': f'https://{domain}/it/watch/{tv_id}?e={ep_id}',
        'user-agent': get_headers(),
        'x-xsrf-token': xsrf,
    })
    if req.ok:
        return BeautifulSoup(req.text, "lxml").find("iframe").get("src")
    console.log(f"[red]Error: {req.status_code}")
    sys.exit(0)


# [func \ main]
def dw_single_ep(tv_id, eps, index_ep_select, domain, token, tv_display_name, season_select, session):
    ep = eps[index_ep_select]
    console.print(f"[green]Download ep: [blue]{ep['n']} [green]=> [purple]{ep['name']}")

    embed_url = get_embed_url(tv_id, ep['id'], domain, session)
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

    clean_name = sanitize_filename(tv_display_name)
    season_dir_name = f"Season {int(season_select):02d}"
    ep_filename = f"{clean_name} S{int(season_select):02d}E{int(ep['n']):02d}"
    ep_dir = os.path.join("videos", clean_name, season_dir_name)
    os.makedirs(ep_dir, exist_ok=True)
    mkv_path = os.path.join(ep_dir, ep_filename + ".mkv")

    download_m3u8(
        m3u8_index=info['video_url'],
        m3u8_audio=info['audio_url'],
        key=key_hex,
        output_filename=mkv_path
    )

def main_dw_tv(tv_id, tv_slug, tv_display_name, version, domain, session):
    token = get_token(tv_id, domain, session)

    num_season_find = get_info_tv(tv_id, tv_slug, version, domain, session)
    console.print("\n[green]Insert season [red]number [yellow]or [red](*) [green]to download all seasons [yellow]or [red][1-2] [green]for a range of season")
    console.print(f"\n[blue]Season find: [red]{num_season_find}")
    season_select = str(msg.ask("\n[green]Insert season number: "))

    if "[" in season_select:
        start, end = map(int, season_select[1:-1].split('-'))
        for n_season in range(start, end + 1):
            eps = get_info_season(tv_id, tv_slug, domain, version, token, n_season, session)
            for ep in eps:
                dw_single_ep(tv_id, eps, int(ep['n'])-1, domain, token, tv_display_name, n_season, session)
                print("\n")

    elif season_select != "*":
        season_select = int(season_select)
        if 1 <= season_select <= num_season_find:
            eps = get_info_season(tv_id, tv_slug, domain, version, token, season_select, session)

            for ep in eps:
                console.print(f"[green]Ep: [blue]{ep['n']} [green]=> [purple]{ep['name']}")
            index_ep_select = str(msg.ask("\n[green]Insert ep [red]number [yellow]or [red](*) [green]to download all ep [yellow]or [red][1-2] [green]for a range of ep: "))

            if "[" in index_ep_select:
                start, end = map(int, index_ep_select[1:-1].split('-'))
                for n in range(start, end + 1):
                    dw_single_ep(tv_id, eps, n-1, domain, token, tv_display_name, season_select, session)

            elif index_ep_select != "*":
                if 1 <= int(index_ep_select) <= len(eps):
                    dw_single_ep(tv_id, eps, int(index_ep_select)-1, domain, token, tv_display_name, season_select, session)
                else:
                    console.print("[red]Wrong index for ep")

            else:
                for ep in eps:
                    dw_single_ep(tv_id, eps, int(ep['n'])-1, domain, token, tv_display_name, season_select, session)
                    print("\n")
        else:
            console.print("[red]Wrong index for season")

    else:
        for n_season in range(1, num_season_find+1):
            eps = get_info_season(tv_id, tv_slug, domain, version, token, n_season, session)
            for ep in eps:
                dw_single_ep(tv_id, eps, int(ep['n'])-1, domain, token, tv_display_name, n_season, session)
                print("\n")
