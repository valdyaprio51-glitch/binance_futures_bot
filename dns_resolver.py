"""
dns_resolver.py
Bypass DNS poisoning / pemblokiran ISP lokal (seperti TrustPositif / Kominfo di Indonesia)
secara otomatis menggunakan DNS-over-HTTPS (DoH) via Cloudflare & Google untuk domain Binance.
"""

import socket
import urllib.request
import json
import logging

logger = logging.getLogger("BinanceFuturesBot")

_orig_getaddrinfo = socket.getaddrinfo
_dns_cache = {}

DOH_PROVIDERS = [
    "https://cloudflare-dns.com/dns-query?name={host}&type=A",
    "https://dns.google/resolve?name={host}&type=A",
]


def resolve_doh(host: str):
    """Mencari IP asli host menggunakan DNS-over-HTTPS (DoH)."""
    if host in _dns_cache:
        return _dns_cache[host]

    for provider_template in DOH_PROVIDERS:
        url = provider_template.format(host=host)
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/dns-json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=4) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    answers = data.get("Answer", [])
                    ips = [
                        ans["data"]
                        for ans in answers
                        if ans.get("type") == 1  # Record Type A
                    ]
                    if ips:
                        _dns_cache[host] = ips
                        return ips
        except Exception:
            continue

    return None


def custom_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    """Pengganti socket.getaddrinfo untuk mem-bypass DNS sinkhole jika query terkait binance."""
    if isinstance(host, str) and ("binance" in host.lower()):
        ips = resolve_doh(host)
        if ips:
            res = []
            for ip in ips:
                try:
                    res.extend(_orig_getaddrinfo(ip, port, family, type, proto, flags))
                except Exception:
                    pass
            if res:
                return res

    return _orig_getaddrinfo(host, port, family, type, proto, flags)


def enable_doh_patch():
    """Mengaktifkan patch DNS resolver otomatis."""
    socket.getaddrinfo = custom_getaddrinfo

