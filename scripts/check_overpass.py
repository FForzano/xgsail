#!/usr/bin/env python3
"""Say why the nautical-POI layer is empty, from the box that is actually
failing.

    docker compose exec backend python scripts/check_overpass.py

Every symptom of this layer looks the same from the outside — a ticked box and
an empty map — and the causes are not things the application can tell apart
after the fact: DNS, blocked egress, a rate-limited server IP, an Overpass
instance that is down, and a runtime error Overpass reports as HTTP 200 all
end with ``fetched_at`` still NULL and no rows in ``osm_pois``. This resolves,
connects and queries each configured endpoint in turn and prints what came
back, so the answer is one command rather than a log-reading session.

Read-only and DB-free: it touches nothing but the network, so it is safe to
run against production while it is misbehaving.
"""

import argparse
import os
import socket
import ssl
import sys
import time
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import requests  # noqa: E402

from backend.services import osm_poi  # noqa: E402

# Somewhere with plenty of marinas: an endpoint that answers but returns
# nothing here is answering about the wrong thing.
DEFAULT_BBOX = (43.75, 9.75, 44.25, 10.25)


def _check_dns(host: str) -> bool:
    try:
        start = time.monotonic()
        addrs = {a[4][0] for a in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)}
    except OSError as exc:
        print(f"    DNS      FAIL  {exc}")
        print("             -> the container cannot resolve names; check its DNS "
              "config, not Overpass")
        return False
    print(f"    DNS      ok    {', '.join(sorted(addrs))} ({(time.monotonic() - start) * 1000:.0f} ms)")
    return True


def _check_tls(host: str) -> bool:
    try:
        start = time.monotonic()
        with socket.create_connection((host, 443), timeout=10) as sock:
            with ssl.create_default_context().wrap_socket(sock, server_hostname=host):
                pass
    except Exception as exc:
        print(f"    TLS      FAIL  {type(exc).__name__}: {exc}")
        print("             -> outbound HTTPS is blocked or intercepted; this is "
              "your network, not Overpass")
        return False
    print(f"    TLS      ok    ({(time.monotonic() - start) * 1000:.0f} ms)")
    return True


def _check_query(endpoint: str, bbox, timeout: float) -> bool:
    query = osm_poi.build_query(*bbox, timeout_s=int(timeout))
    start = time.monotonic()
    try:
        resp = requests.post(endpoint, data={"data": query}, timeout=timeout,
                             headers={"User-Agent": osm_poi.OVERPASS_USER_AGENT})
    except Exception as exc:
        print(f"    query    FAIL  {type(exc).__name__}: {exc}")
        return False
    elapsed = time.monotonic() - start

    if resp.status_code >= 400:
        print(f"    query    HTTP {resp.status_code} ({elapsed:.1f}s)")
        print(f"             body: {(resp.text or '<empty>')[:300]}")
        if resp.status_code == 429:
            print(f"             -> RATE LIMITED. Retry-After: "
                  f"{resp.headers.get('Retry-After', 'not sent')}. Every query now "
                  "leaves from this one server IP, so the whole instance shares "
                  "one quota.")
        elif resp.status_code in (503, 504):
            print("             -> the instance is overloaded or down; the mirror "
                  "below is the fallback")
        return False

    try:
        payload = resp.json()
    except ValueError:
        print(f"    query    200 but not JSON ({elapsed:.1f}s)")
        print(f"             body: {(resp.text or '<empty>')[:300]}")
        return False

    remark = payload.get("remark") or ""
    elements = payload.get("elements")
    if remark:
        print(f"    query    200 with remark ({elapsed:.1f}s): {remark[:200]}")
    if "error" in remark.lower():
        print("             -> a RUNTIME ERROR returned as 200. Overpass gave up "
              "on the query (timeout/out of memory), which is what a throttled or "
              "overloaded instance does. Storing this would blank the cell.")
        return False
    if elements is None:
        print(f"    query    200 but not an Overpass answer ({elapsed:.1f}s): "
              f"{str(payload)[:200]}")
        return False

    pois = osm_poi.parse_elements(payload)
    print(f"    query    ok    {len(elements)} elements -> {len(pois)} POIs ({elapsed:.1f}s)")
    if elements and not pois:
        print("             -> elements came back but none classified; the tag "
              "rules and the query have drifted apart")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bbox", help="south,west,north,east (default: Ligurian coast)")
    parser.add_argument("--timeout", type=float, default=osm_poi.FETCH_TIMEOUT_S)
    args = parser.parse_args()

    bbox = osm_poi.parse_bbox(args.bbox) if args.bbox else DEFAULT_BBOX

    print(f"User-Agent: {osm_poi.OVERPASS_USER_AGENT}")
    print(f"bbox:       {','.join(str(c) for c in bbox)}")
    blocked = osm_poi.breaker_blocked_for()
    if blocked:
        print(f"breaker:    paused for another {blocked:.0f}s "
              "(this process only; the script queries anyway)")
    print(f"endpoints:  {len(osm_poi.ENDPOINTS)} configured")
    # The DNS and TLS probes below use raw sockets, which ignore a configured
    # proxy; requests honours it. So a run that passes both and then fails the
    # query is pointing at the proxy, and the note keeps that from reading as
    # a contradiction.
    proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
    if proxy:
        print(f"proxy:      {proxy} (used for the query, bypassed by the DNS/TLS probes)")
    print()

    reachable = 0
    for endpoint in osm_poi.ENDPOINTS:
        print(f"  {endpoint}")
        host = urlparse(endpoint).hostname
        if _check_dns(host) and _check_tls(host) and _check_query(endpoint, bbox, args.timeout):
            reachable += 1
        print()

    if reachable:
        print(f"{reachable}/{len(osm_poi.ENDPOINTS)} endpoints answered with usable data.")
        print("The layer can fill its cells, so an empty map is downstream of here: "
              "the frontend's zoom gate (NEAR_DETAIL_MIN_ZOOM), or cells whose "
              f"retry window ({osm_poi.RETRY_AFTER_FAILURE_MIN} min) has not "
              "reopened since they last failed.")
        return 0

    print("No endpoint returned usable data — the diagnosis is above.")
    print("Cells stay uncovered (fetched_at NULL, no osm_pois rows) until one does.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
