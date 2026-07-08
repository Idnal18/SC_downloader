# 10.12.23

# Class import
from Src.Util.headers import get_headers
from Src.Util.console import console

# General import
import requests, sys, json
from bs4 import BeautifulSoup

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
