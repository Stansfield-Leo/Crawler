#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Recursively download PPT/PPTX/PPS/PPSX/PDF files from course websites.
Designed for Moodle, standard course pages, and most JavaScript-driven pages.

Use this script only for teaching materials that you are authorized to access
and save. Do not use it to bypass access controls.
"""

import argparse
import csv
import hashlib
import io
import re
import time
import urllib.parse
import zipfile
from collections import deque
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

TARGET_EXTS = {".ppt", ".pptx", ".pps", ".ppsx", ".pdf"}
MIME_EXT = {
    "application/pdf": ".pdf",
    "application/vnd.ms-powerpoint": ".ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.openxmlformats-officedocument.presentationml.slideshow": ".ppsx",
}
RESOURCE_WORDS = (
    "ppt", "pptx", "powerpoint", "slide", "slides", "presentation",
    "lecture", "week", "module", "course", "resource", "download",
    "handout", "courseware", "lecture notes", "teaching materials",
)
RESOURCE_PATTERNS = (
    "/mod/resource/", "/mod/folder/", "/pluginfile.php/",  # Moodle
    "/download/", "forcedownload=1", "download=1", "download=true",
)
INVALID_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')
SPACE = re.compile(r"\s+")


def clean_name(text, fallback, limit=200):
    text = urllib.parse.unquote(text or "")
    text = INVALID_NAME.sub("_", SPACE.sub(" ", text).strip(" ."))
    return text[:limit].rstrip(" .") or fallback


def normalize_url(url, base=""):
    if base:
        url = urllib.parse.urljoin(base, url)
    url = url.strip()
    if not url:
        return ""
    p = urllib.parse.urlsplit(url)
    if p.scheme.lower() not in {"http", "https"}:
        return ""
    return urllib.parse.urlunsplit(
        (p.scheme.lower(), p.netloc.lower(), p.path or "/", p.query, "")
    )


def host(url):
    return (urllib.parse.urlsplit(url).hostname or "").lower()


def domain_match(hostname, domain):
    domain = domain.lower().strip().lstrip(".")
    return hostname == domain or hostname.endswith("." + domain)


def canonical_url(url):
    """Compare page URLs after removing fragments and sorting query parameters."""
    url = normalize_url(url)
    if not url:
        return ""
    p = urllib.parse.urlsplit(url)
    query = urllib.parse.urlencode(
        sorted(urllib.parse.parse_qsl(p.query, keep_blank_values=True)),
        doseq=True,
    )
    return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, query, ""))


def looks_like_auth_page(url):
    """Identify common university single sign-on pages."""
    h = host(url)
    path = urllib.parse.urlsplit(url).path.lower()
    auth_hosts = (
        "login.microsoftonline.com",
        "login.live.com",
        "idp.ucl.ac.uk",
        "shib.ucl.ac.uk",
    )
    return (
        any(domain_match(h, item) for item in auth_hosts)
        or "saml" in path
        or "oauth" in path
        or "authorize" in path
    )


def suffix(url):
    path = urllib.parse.unquote(urllib.parse.urlsplit(url).path)
    return Path(path).suffix.lower()


def page_like(url):
    ext = suffix(url)
    return not ext or ext in {".html", ".htm", ".php", ".asp", ".aspx", ".jsp"}


def resource_like(url, text="", download_attr=""):
    if suffix(url) in TARGET_EXTS:
        return True
    value = f"{url} {text} {download_attr}".lower()
    return (
        any(x in value for x in RESOURCE_PATTERNS)
        or any(x in value for x in RESOURCE_WORDS)
    )


def disposition_filename(header):
    if not header:
        return ""
    m = re.search(r"filename\*\s*=\s*(?:UTF-8''|utf-8'')([^;]+)", header, re.I)
    if m:
        return urllib.parse.unquote(m.group(1).strip().strip('"'))
    m = re.search(r'filename\s*=\s*"([^"]+)"', header, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r"filename\s*=\s*([^;]+)", header, re.I)
    return m.group(1).strip().strip('"') if m else ""


def sniff_extension(data):
    if data.startswith(b"%PDF-"):
        return ".pdf"
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                if "ppt/presentation.xml" in set(zf.namelist()):
                    return ".pptx"
        except zipfile.BadZipFile:
            pass
    return ""


class Saver:
    FIELDS = [
        "filename", "saved_path", "size_bytes", "sha256",
        "source_title", "source_page", "download_url", "final_url",
        "content_type", "http_status",
    ]

    def __init__(self, output):
        self.output = Path(output).resolve()
        self.files_dir = self.output / "files"
        self.manifest = self.output / "download_manifest.csv"
        self.output.mkdir(parents=True, exist_ok=True)
        self.hashes = set()
        self.saved = 0
        self.duplicates = 0

        if self.manifest.exists():
            try:
                with self.manifest.open("r", encoding="utf-8-sig", newline="") as f:
                    for row in csv.DictReader(f):
                        if row.get("sha256"):
                            self.hashes.add(row["sha256"])
            except OSError:
                pass

    def save(self, data, filename, title, source_page, download_url,
             final_url, content_type, status):
        digest = hashlib.sha256(data).hexdigest()
        if digest in self.hashes:
            self.duplicates += 1
            print(f"[Duplicate] {filename}")
            return

        folder = self.files_dir / clean_name(title, "Unsorted", 100)
        folder.mkdir(parents=True, exist_ok=True)
        filename = clean_name(filename, f"slides_{digest[:10]}", 220)
        path = folder / filename
        if path.exists():
            path = folder / f"{path.stem}_{digest[:8]}{path.suffix}"
        path.write_bytes(data)

        row = {
            "filename": path.name,
            "saved_path": str(path.relative_to(self.output)),
            "size_bytes": len(data),
            "sha256": digest,
            "source_title": title,
            "source_page": source_page,
            "download_url": download_url,
            "final_url": final_url,
            "content_type": content_type,
            "http_status": status,
        }
        new_file = not self.manifest.exists() or self.manifest.stat().st_size == 0
        with self.manifest.open("a", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.FIELDS)
            if new_file:
                writer.writeheader()
            writer.writerow(row)

        self.hashes.add(digest)
        self.saved += 1
        print(f"[Downloaded] {row['saved_path']} ({len(data) / 1024 / 1024:.2f} MB)")


class Crawler:
    def __init__(self, args, context):
        self.args = args
        self.context = context
        self.saver = Saver(args.output)
        self.max_bytes = int(args.max_file_mb * 1024 * 1024)
        self.starts = []
        for value in args.start_url:
            value = normalize_url(value)
            if value and value not in self.starts:
                self.starts.append(value)
        if not self.starts:
            raise ValueError("No valid --start-url was provided.")

        self.start_hosts = {host(x) for x in self.starts}
        self.allowed_domains = self.start_hosts | {
            x.lower().strip() for x in args.allow_domain
        }
        self.queue = deque((url, 0) for url in self.starts)
        self.visited = set()
        self.probed = set()
        self.errors = 0

    def page_allowed(self, url):
        if self.args.follow_all_domains:
            return True
        return any(domain_match(host(url), d) for d in self.allowed_domains)

    @staticmethod
    def extract_links(page):
        js = """
        els => els.map(a => ({
          href: a.href || a.getAttribute('href') || '',
          text: (a.innerText || a.textContent || a.getAttribute('aria-label') || '').trim(),
          download: a.getAttribute('download') || ''
        }))
        """
        result, seen = [], set()
        for frame in page.frames:
            try:
                rows = frame.locator("a[href], area[href]").evaluate_all(js)
            except Exception:
                continue
            for row in rows:
                url = normalize_url(row.get("href", ""), frame.url or page.url)
                key = (url, row.get("text", ""))
                if url and key not in seen:
                    seen.add(key)
                    result.append((url, row.get("text", ""), row.get("download", "")))
        return result

    def scroll_page(self, page):
        last_height = -1
        for _ in range(5):
            try:
                height = page.evaluate("() => document.documentElement.scrollHeight")
                if height == last_height:
                    break
                last_height = height
                page.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight)")
                page.wait_for_timeout(500)
            except Exception:
                break
        try:
            page.evaluate("() => window.scrollTo(0, 0)")
        except Exception:
            pass

    def try_download(self, url, title, source_page):
        if url in self.probed:
            return "skip"
        self.probed.add(url)

        try:
            response = self.context.request.get(
                url,
                timeout=self.args.timeout * 1000,
                fail_on_status_code=False,
            )
        except Exception as exc:
            self.errors += 1
            print(f"[Resource error] {url}\n                 {exc}")
            return "error"

        try:
            status = response.status
            final_url = normalize_url(response.url) or response.url
            headers = {k.lower(): v for k, v in response.headers.items()}
            content_type = headers.get("content-type", "").split(";", 1)[0].lower()

            if status >= 400:
                return "skip"
            if content_type in {"text/html", "application/xhtml+xml"}:
                return "html"

            filename = disposition_filename(headers.get("content-disposition", ""))
            candidates = [
                Path(filename).suffix.lower() if filename else "",
                MIME_EXT.get(content_type, ""),
                suffix(final_url),
            ]
            ext = next((x for x in candidates if x in TARGET_EXTS), "")

            length = headers.get("content-length", "")
            if length.isdigit() and int(length) > self.max_bytes:
                print(f"[Skipped] File exceeds {self.args.max_file_mb:g} MB: {url}")
                return "skip"

            binary = content_type in {
                "application/octet-stream", "application/download", "binary/octet-stream"
            }
            attachment = "attachment" in headers.get("content-disposition", "").lower()
            if not ext and not (binary or attachment):
                return "skip"

            data = response.body()
            if len(data) > self.max_bytes:
                return "skip"
            if not ext:
                ext = sniff_extension(data)
            if not ext:
                return "skip"

            if not filename:
                filename = Path(
                    urllib.parse.unquote(urllib.parse.urlsplit(final_url).path)
                ).name
            filename = clean_name(
                filename,
                f"slides_{hashlib.sha1(url.encode()).hexdigest()[:10]}{ext}",
            )
            if Path(filename).suffix.lower() != ext:
                filename += ext

            self.saver.save(
                data, filename, title, source_page, url,
                final_url, content_type, status,
            )
            return "downloaded"
        finally:
            try:
                response.dispose()
            except Exception:
                pass

    def enqueue(self, url, text, download_attr, depth):
        if depth >= self.args.max_depth or not page_like(url):
            return
        if not self.page_allowed(url):
            return

        same_course_site = any(domain_match(host(url), d) for d in self.start_hosts)
        if same_course_site or resource_like(url, text, download_attr):
            self.queue.append((url, depth + 1))

    def navigate(self, page, url):
        """Handle repeated redirects between Moodle and Microsoft sign-in pages."""
        # After the first login, the browser is usually already on the start page.
        if canonical_url(page.url) == canonical_url(url):
            try:
                page.wait_for_load_state("domcontentloaded", timeout=8000)
            except Exception:
                pass
            return True

        for attempt in range(1, 4):
            try:
                page.goto(
                    url,
                    wait_until="commit",
                    timeout=self.args.timeout * 1000,
                )
                try:
                    page.wait_for_load_state(
                        "domcontentloaded",
                        timeout=self.args.timeout * 1000,
                    )
                except PlaywrightTimeoutError:
                    print("[Warning] DOM loading timed out; checking the current page.")

                # Allow time for SSO redirects to complete.
                page.wait_for_timeout(1200)
                current = normalize_url(page.url)

                if looks_like_auth_page(current):
                    if self.args.headless:
                        self.errors += 1
                        print(f"[Login required] Redirected to: {current}")
                        return False
                    print("[Login required] A university sign-in page was detected.")
                    print("Complete sign-in in the browser. After the course page reappears, return to the terminal and press Enter.")
                    input()
                    page.wait_for_timeout(1500)
                    continue

                return True

            except PlaywrightTimeoutError:
                print(f"[Warning] Page loading timed out (attempt {attempt}/3); checking the current page.")
                if not looks_like_auth_page(page.url):
                    return True
            except Exception as exc:
                message = str(exc)
                if "interrupted by another navigation" in message.lower():
                    # Microsoft SSO may continue redirecting before goto returns.
                    page.wait_for_timeout(1800)
                    current = normalize_url(page.url)
                    if looks_like_auth_page(current):
                        if self.args.headless:
                            self.errors += 1
                            print(f"[Login required] Redirected to: {current}")
                            return False
                        print("[Login redirect] The page is redirecting to Microsoft/UCL sign-in.")
                        print("Complete sign-in and wait until the course page is fully visible, then return to the terminal and press Enter.")
                        input()
                        page.wait_for_timeout(1500)
                        continue
                    if host(current) == host(url):
                        return True
                if attempt == 3:
                    self.errors += 1
                    print(f"[Page error] {exc}")
                    return False
                page.wait_for_timeout(1200)

        self.errors += 1
        print(f"[Page error] Could not open reliably: {url}")
        return False

    def process_page(self, page, url, depth):
        print(f"\n[Page {len(self.visited)}/{self.args.max_pages}] depth={depth} {url}")
        if not self.navigate(page, url):
            return

        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        self.scroll_page(page)

        source_page = normalize_url(page.url) or url
        title = clean_name(page.title(), "Unsorted", 120)
        links = self.extract_links(page)
        print(f"[Title] {title}")
        print(f"[Links found] {len(links)}")

        for link_url, text, download_attr in links:
            if link_url in self.visited:
                continue

            same_course_site = any(
                domain_match(host(link_url), d) for d in self.start_hosts
            )
            if resource_like(link_url, text, download_attr):
                if same_course_site or not self.args.no_external_files:
                    result = self.try_download(link_url, title, source_page)
                    if result == "downloaded":
                        continue

            self.enqueue(link_url, text, download_attr, depth)

        time.sleep(max(0, self.args.delay))

    def run(self, page):
        while self.queue and len(self.visited) < self.args.max_pages:
            url, depth = self.queue.popleft()
            url = normalize_url(url)
            if not url or url in self.visited or not self.page_allowed(url):
                continue
            self.visited.add(url)
            self.process_page(page, url, depth)

        print("\n" + "=" * 68)
        print("Crawl completed")
        print(f"Pages visited: {len(self.visited)}")
        print(f"Resources checked: {len(self.probed)}")
        print(f"Files downloaded: {self.saver.saved}")
        print(f"Duplicate files: {self.saver.duplicates}")
        print(f"Errors: {self.errors}")
        print(f"Output directory: {self.saver.output}")
        print(f"Manifest: {self.saver.manifest}")
        print("=" * 68)


def main():
    parser = argparse.ArgumentParser(
        description="Recursively download PPT/PPTX/PPS/PPSX/PDF files from course websites.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--start-url", action="append", required=True,
                        help="Start URL. Repeat this option for multiple websites.")
    parser.add_argument("--output", default="master_slides")
    parser.add_argument("--profile-dir", default=".course_crawler_profile")
    parser.add_argument("--login", action="store_true",
                        help="Open the browser and wait for manual university sign-in before crawling.")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--allow-domain", action="append", default=[],
                        help="Additional domain that the crawler may enter recursively, such as a university SharePoint domain.")
    parser.add_argument("--follow-all-domains", action="store_true")
    parser.add_argument("--no-external-files", action="store_true",
                        help="Do not inspect external files linked directly from course pages.")
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument("--max-pages", type=int, default=1000)
    parser.add_argument("--max-file-mb", type=float, default=500)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()

    if args.login and args.headless:
        parser.error("--login and --headless cannot be used together.")

    profile = Path(args.profile_dir).resolve()
    profile.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            headless=args.headless,
            accept_downloads=True,
            viewport={"width": 1440, "height": 1000},
        )
        try:
            crawler = Crawler(args, context)
            page = context.pages[0] if context.pages else context.new_page()

            if args.login:
                # For multiple websites, sign in once per unique domain.
                login_urls = {}
                for start_url in crawler.starts:
                    login_urls.setdefault(host(start_url), start_url)

                for index, (login_host, login_url) in enumerate(login_urls.items(), 1):
                    try:
                        page.goto(
                            login_url,
                            wait_until="commit",
                            timeout=args.timeout * 1000,
                        )
                    except Exception:
                        # Allow the browser to continue during repeated SSO redirects.
                        pass

                    print(
                        f"\n[{index}/{len(login_urls)}] Complete sign-in for {login_host} in the browser."
                    )
                    print("Wait until the course page is fully visible, then return to the terminal and press Enter.")
                    input()

                    # Sign-in may finish in a new tab; prefer a page on the target domain.
                    matching_pages = [
                        p for p in context.pages
                        if domain_match(host(p.url), login_host)
                    ]
                    if matching_pages:
                        page = matching_pages[-1]
                    elif context.pages:
                        page = context.pages[-1]

                    try:
                        page.wait_for_load_state("domcontentloaded", timeout=10000)
                    except Exception:
                        pass
                    page.wait_for_timeout(1500)

                    while looks_like_auth_page(page.url):
                        print(f"[Login incomplete] The current page is still: {page.url}")
                        print("Continue signing in. Press Enter after the course page is visible.")
                        input()
                        matching_pages = [
                            p for p in context.pages
                            if domain_match(host(p.url), login_host)
                        ]
                        if matching_pages:
                            page = matching_pages[-1]
                        elif context.pages:
                            page = context.pages[-1]
                        page.wait_for_timeout(1200)

                    # Reopen the requested course if sign-in ends on the Moodle home page or another page.
                    if canonical_url(page.url) != canonical_url(login_url):
                        try:
                            page.goto(
                                login_url,
                                wait_until="commit",
                                timeout=args.timeout * 1000,
                            )
                            try:
                                page.wait_for_load_state(
                                    "domcontentloaded",
                                    timeout=args.timeout * 1000,
                                )
                            except Exception:
                                pass
                        except Exception:
                            # Crawler.navigate will handle any remaining redirects.
                            pass

                    print(f"[Login confirmed] Current page: {page.url}")

            crawler.run(page)
        finally:
            context.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")