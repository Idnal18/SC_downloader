# 10.12.23

# Class import
from Src.Util.headers import get_headers
from Src.Util.console import console

# General import
import requests, sys, json
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def domain_version():
    console.print("[green]Get rules ...")
    req_repo = None
    try:
        with open('data.json', 'r') as file:
            req_repo = json.load(file)
    except FileNotFoundError:
        req_repo = {"domain": ""}
    domain = req_repo['domain']

    while True:
        if not domain:
            domain = input("Insert full domain (e.g. streamingcommunityz.pizza): ")
            req_repo['domain'] = domain
            with open('data.json', 'w') as file:
                json.dump(req_repo, file)
        console.print(f"[blue]Test domain [white]=> [red]{domain}")
        site_url = f"https://{domain}"
        try:
            session = requests.Session()

            # Retry transient failures (dead keep-alive connections after long
            # idle periods between downloads, rate limits, transient 5xx)
            retry_strategy = Retry(
                total=3,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["GET", "POST"]
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            session.mount("https://", adapter)
            session.mount("http://", adapter)

            site_request = session.get(site_url, headers={'user-agent': get_headers()})
            soup = BeautifulSoup(site_request.text, "lxml")
            version = json.loads(soup.find("div", {"id": "app"}).get("data-page"))['version']
            console.print(f"[blue]Rules [white]=> [red]{domain}")
            return domain, version, session

        except Exception as e:
            console.log("[red]Cant get version, problem with domain. Try again.")
            domain = None
            continue

def search(title_search, domain, version, session):

    xsrf = requests.utils.unquote(session.cookies.get('XSRF-TOKEN', ''))
    headers = {
        'user-agent': get_headers(),
        'X-Inertia': 'true',
        'X-Inertia-Version': version,
        'X-XSRF-TOKEN': xsrf,
        'Accept': 'application/json, text/plain, */*',
        'Referer': f'https://{domain}',
    }

    req = session.get(f"https://{domain}/it/search?q={title_search}", headers=headers)

    if req.ok:
        results = []
        for title in req.json()['data']:
            release_date = title.get('last_air_date')
            year = release_date.split('-')[0] if release_date else None
            results.append({
                'name': title['name'],
                'type': title['type'],
                'id': title['id'],
                'slug': title['slug'],
                'year': year
            })
        return results[0:21]
    else:
        console.log(f"[red]Error: {req.status_code}")
        sys.exit(0)

def display_search_results(db_title):
    for i, title in enumerate(db_title):
        year = f" ({title['year']})" if title.get('year') else ""
        console.print(f"[yellow]{i} [white]-> [green]{title['name']}{year} [white]- [cyan]{title['type']}")

def parse_index_selection(index_select, max_len):
    index_select = index_select.strip()
    if index_select.isnumeric():
        n = int(index_select)
        return [n] if 0 <= n <= max_len - 1 else []
    if "[" in index_select:
        inner = index_select.strip("[]")
        if "-" in inner:
            start, end = map(int, inner.split('-'))
            result = list(range(start, end + 1))
        elif "," in inner:
            result = list(map(int, inner.split(',')))
        else:
            return []
        if any(n < 0 or n > max_len - 1 for n in result):
            return []
        return result
    return []
