"""Rellena image_url faltante en productos usando og:image de la página del producto."""
import re
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "db" / "prices.db"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
OG_RE = re.compile(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', re.I)
OG_RE2 = re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', re.I)


def fetch_og_image(url: str) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=10) as r:
            html = r.read(60_000).decode("utf-8", errors="ignore")
        m = OG_RE.search(html) or OG_RE2.search(html)
        return m.group(1).strip() if m else None
    except Exception:
        return None


def main():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, url FROM products WHERE image_url IS NULL OR image_url = ''")
    rows = c.fetchall()
    print(f"{len(rows)} productos sin imagen")

    updated = 0
    for i, (pid, name, url) in enumerate(rows, 1):
        img = fetch_og_image(url)
        if img:
            c.execute("UPDATE products SET image_url = ? WHERE id = ?", (img, pid))
            updated += 1
            print(f"  [{i}/{len(rows)}] OK  {name[:50]}")
        else:
            print(f"  [{i}/{len(rows)}] --  {name[:50]}")
        if i % 10 == 0:
            conn.commit()
        time.sleep(0.3)

    conn.commit()
    conn.close()
    print(f"\nActualizados: {updated}/{len(rows)}")


if __name__ == "__main__":
    main()
