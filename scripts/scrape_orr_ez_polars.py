#!/usr/bin/env python3
"""
Scrape ORR-EZ polar tables from regattaman.com cert pages and PATCH
each boat in the SailFrames catalog with its polar data.

Each cert page renders cells like:
  <span class="polarDat" title="10 kts - 110 = 514.35">514.35</span>
where the title is "<TWS> kts - <TWA-or-key> = <s_per_nm>". Cells
live inside one of two divs:
  id="polar_time_s"   — with spinnaker  (absent on boats without)
  id="polar_time_ns"  — without spinnaker

The polar values are SECONDS PER NAUTICAL MILE — the cert's native
unit. Frontend converts to knots with 3600 / s_per_nm.

Schema written to boat.polar:
  {
    "twa_values": [52, 60, 75, 90, 110, 120, 135, 150, 165],
    "tws_values": [4, 6, 8, 10, 12, 14, 16, 20, 24],
    "spin":   { "twa,tws": s_per_nm, ... },   // present only if cert had one
    "nospin": { "twa,tws": s_per_nm, ... },
    "opt_beat":  { "tws": {"angle": deg, "vmg": s_per_nm}, ... },
    "opt_run":   { "tws": {"angle": deg, "vmg": s_per_nm}, ... },
    "source_url": cert URL,
    "scraped_at": ISO timestamp
  }
"""

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

API_BASE = "https://rnngzx7flk.execute-api.us-east-1.amazonaws.com"

# Generic class polars — used when a boat has no boat-specific
# cert_url but is a known one-design class with a published ORR-EZ
# class cert. The scraper falls back to this lookup keyed by
# boat.type so e.g. all four J/80s in the CYC fleet inherit the same
# polar without each needing their own cert URL.
CLASS_CERT_URLS = {
    'J/80': 'https://www.regattaman.com/cert_form.php?sku=h-21-2026-2717-8760-0-327',
}

# Title attribute on every polar cell.
# Capture groups: 1=TWS  2=key (TWA digits, "Beat VMG", "Opt Beat Angle",
# "Run VMG", "OPT Run Angle")  3=value
_CELL_RE = re.compile(
    r'title="(\d+)\s*kts\s*-\s*([^"=]+?)\s*=\s*([\d.]+)"',
    re.IGNORECASE,
)


def _find_section(html, marker):
    """Return the substring of html that belongs to the marker'd div.
    The cert page renders these polars as div blocks identified by
    id="polar_time_s" / id="polar_time_ns". We slice from the marker
    to the next polar div (or end of doc) and parse cells from that
    slice, so the two polars don't bleed into each other."""
    idx = html.find(f'id="{marker}"')
    if idx == -1:
        return None
    # Look ahead — slice until the next polar div begins (whichever
    # one comes next) or to end-of-doc.
    next_s = html.find('id="polar_time_s"', idx + len(marker) + 5)
    next_ns = html.find('id="polar_time_ns"', idx + len(marker) + 5)
    end = min(p for p in (next_s, next_ns, len(html)) if p != -1)
    return html[idx:end]


def _parse_section(slice_html):
    """Parse polar cells out of one section. Returns:
       {twa,tws: s_per_nm}, {tws: {angle, vmg}}_beat, {tws: {angle, vmg}}_run."""
    grid = {}
    beat = {}
    run = {}
    if not slice_html:
        return grid, beat, run
    for tws_s, key, val_s in _CELL_RE.findall(slice_html):
        tws = int(tws_s)
        val = float(val_s)
        k = key.strip().lower()
        if k.isdigit():
            twa = int(k)
            grid[(twa, tws)] = val
        elif k == 'beat vmg':
            beat.setdefault(tws, {})['vmg'] = val
        elif k == 'opt beat angle':
            beat.setdefault(tws, {})['angle'] = val
        elif k == 'run vmg':
            run.setdefault(tws, {})['vmg'] = val
        elif k in ('opt run angle', 'OPT Run Angle'.lower()):
            run.setdefault(tws, {})['angle'] = val
    return grid, beat, run


def parse_polar_from_html(html):
    """Top-level entry. Returns the polar dict to store on the boat
    doc, or None if the page has no polar tables."""
    spin_slice = _find_section(html, 'polar_time_s')
    nospin_slice = _find_section(html, 'polar_time_ns')

    spin_grid, _, _ = _parse_section(spin_slice)
    nospin_grid, nospin_beat, nospin_run = _parse_section(nospin_slice)

    if not spin_grid and not nospin_grid:
        return None

    # Pull TWA + TWS axis values from whichever grid is bigger — both
    # use the same axes per ORR-EZ standard.
    base = spin_grid or nospin_grid
    twa_vals = sorted({twa for (twa, _tws) in base.keys()})
    tws_vals = sorted({tws for (_twa, tws) in base.keys()})

    def _grid_to_obj(g):
        if not g:
            return None
        return {f'{twa},{tws}': round(v, 2) for (twa, tws), v in g.items()}

    return {
        'twa_values': twa_vals,
        'tws_values': tws_vals,
        'spin':   _grid_to_obj(spin_grid),
        'nospin': _grid_to_obj(nospin_grid),
        'opt_beat': {str(t): v for t, v in nospin_beat.items()},
        'opt_run':  {str(t): v for t, v in nospin_run.items()},
    }


# ---- HTTP helpers ----

def fetch_cert_html(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'sailframes-polar-scraper/1.0 (+contact via github.com/sailframes/core)',
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode('utf-8', errors='replace')


def api(method, path, body=None):
    url = f'{API_BASE}{path}'
    data = json.dumps(body).encode() if body is not None else None
    headers = {'Content-Type': 'application/json'} if body is not None else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    print('Fetching boats catalog...')
    data = api('GET', '/api/boats')
    boats = data.get('boats', [])
    if only:
        boats = [b for b in boats if b.get('sail_number') == only or b.get('boat_id') == only or b.get('name') == only]
    print(f'  {len(boats)} candidates')

    # Cache fetched HTML by URL — generic class polars are shared
    # across every boat of that class, so we only fetch each unique
    # URL once even when several boats use it.
    html_cache = {}

    ok = 0
    skipped = 0
    failed = 0
    for b in boats:
        cert = b.get('cert_url')
        boat_type = b.get('type', '')
        generic = False
        if not cert and boat_type in CLASS_CERT_URLS:
            cert = CLASS_CERT_URLS[boat_type]
            generic = True
        if not cert:
            skipped += 1
            continue
        name = b.get('name', '?')
        try:
            if cert not in html_cache:
                html_cache[cert] = fetch_cert_html(cert)
            polar = parse_polar_from_html(html_cache[cert])
            if not polar:
                print(f'  ✗ {name:18s}: no polar tables in cert page')
                failed += 1
                continue
            polar['source_url'] = cert
            polar['scraped_at'] = datetime.now(timezone.utc) \
                .isoformat().replace('+00:00', 'Z')
            if generic:
                polar['class_generic'] = True
            api('PATCH', f'/api/boats/{b["boat_id"]}', {'polar': polar})
            spin_n = len(polar.get('spin') or {})
            ns_n = len(polar.get('nospin') or {})
            tag = ' [class generic]' if generic else ''
            print(f'  ✓ {name:18s}: spin={spin_n:>3d} nospin={ns_n:>3d}{tag}')
            ok += 1
        except urllib.error.HTTPError as e:
            print(f'  ✗ {name:18s}: HTTP {e.code} fetching cert')
            failed += 1
        except Exception as e:
            print(f'  ✗ {name:18s}: {e}')
            failed += 1

    print()
    print(f'Done: {ok} updated · {skipped} skipped (no cert URL) · {failed} failed')


if __name__ == '__main__':
    main()
