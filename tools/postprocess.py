#!/usr/bin/env python3
"""Clean up a wget mirror of www.kanban.it for static hosting.

- strips query-string suffixes wget baked into asset filenames
  (e.g. jquery.js@ver=1.12.4 -> jquery.js, style.css@ver=3.13.css -> style.css)
- removes WordPress head cruft that needs a live backend (feeds, oEmbed, xmlrpc, emoji)
- removes Google Analytics and the GDPR Cookie Compliance banner with its assets
- rewrites links to the original domain (http or https, which wget doesn't always
  convert) into relative ones when the target exists in the mirror, and turns the rest into plain text
- fixes ?p=NN shortlinks and malformed relative links (e.g. "it/supermarket" written inside /it/)
- makes the WordPress 404 page (fetched by build.sh) usable as GitHub Pages' 404.html
- moves the Privacy link from the main menu to the footer
- replaces the root page with a redirect to /it/, like the original site
"""
import html
import json
import os
import re
import shutil
import sys

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "docs")
DOMAIN_RE = r"https?:(?:\\?/){2}(?:www\.)?kanban\.it"
HOME = "it/"
PRIVACY = HOME + "privacy-policy/"

# name.ext@query[.html|.css] -> name.ext
ASSET_SUFFIX_RE = re.compile(
    r"(\.(?:js|css|woff2?|ttf|eot|svg|png|jpe?g|gif))@[^\"'\s)#<>]*?(?:\.html|\.css)?(?=[\"'\s)#<>])"
)
# fonts served as text/html get ".html" appended by wget --adjust-extension
FONT_HTML_RE = re.compile(r"(\.(?:woff2?|ttf|eot|otf))\.html(?=$|[\"'\s)#?<>])")
HEAD_CRUFT = [
    r'<link rel=["\'](?:pingback|EditURI|wlwmanifest|https://api\.w\.org/|shortlink|profile)["\'][^>]*>\s*',
    r'<link rel=["\']alternate["\'] type=["\'](?:application/rss\+xml|application/json\+oembed|text/xml\+oembed)["\'][^>]*>\s*',
    r'<link rel=["\']dns-prefetch["\'] href=["\'](?:https?:)?//s\.w\.org/?["\'][^>]*>\s*',
    r'<meta name=["\']generator["\'][^>]*>\s*',
    r'<script type=["\']text/javascript["\']>\s*window\._wpemojiSettings.*?</script>\s*',
    r'<style type=["\']text/css["\']>\s*img\.wp-smiley.*?</style>\s*',
]
TRACKING = [
    r'<!-- Custom Scripts -->\s*<script>\s*\(function\(i,s,o,g,r,a,m\)\{i\[\'GoogleAnalyticsObject\'\].*?</script>\s*',
]
# GDPR Cookie Compliance plugin: banner, settings modal, CSS and JS (the static site sets no cookies)
COOKIE_BANNER = [
    r'<link rel=["\']stylesheet["\'] id=["\']moove_gdpr_frontend-css["\'][^>]*>\s*',
    r'<style id=["\']moove_gdpr_frontend-inline-css["\'].*?</style>\s*',
    r'\s*<!--copyscapeskip-->.*?<!--/copyscapeskip-->',
    r'<script type=["\']text/javascript["\']>\s*/\* <!\[CDATA\[ \*/\s*var moove_frontend_gdpr_scripts.*?</script>\s*',
    r'<script type=["\']text/javascript["\'] src=["\'][^"\']*gdpr-cookie-compliance/[^"\']*["\']>\s*</script>\s*',
    r'<script type=["\']text/javascript["\']>\s*var gdpr_consent__strict.*?</script>\s*',
]
COOKIE_PLUGIN_DIR = "wp-content/plugins/gdpr-cookie-compliance"
ASSET_EXT = (".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf", ".woff", ".woff2", ".ttf", ".eot")

with open(os.path.join(os.path.dirname(__file__), "shortlinks.json")) as fh:
    SHORTLINKS = json.load(fh)
# pages wget saved twice from malformed links: "foo.html" next to "foo/index.html",
# and "it/it/foo.html" from a relative "it/foo" written inside /it/
DUPLICATES = {}


def find_duplicates():
    for dirpath, _, files in os.walk(ROOT):
        for f in files:
            if not f.endswith(".html"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, f), ROOT)
            page = rel[:-5]
            if page.startswith(HOME + HOME):
                page = page[len(HOME):]
            if os.path.isfile(os.path.join(ROOT, page, "index.html")):
                DUPLICATES[rel] = page + "/"


def clean_name(name):
    name = FONT_HTML_RE.sub(r"\1", name)
    m = re.match(r"(.+?\.(?:js|css|woff2?|ttf|eot|svg|png|jpe?g|gif))@.*$", name)
    return m.group(1) if m else name


def rename_assets():
    for dirpath, _, files in os.walk(ROOT):
        for f in files:
            new = clean_name(f)
            if new != f:
                src, dst = os.path.join(dirpath, f), os.path.join(dirpath, new)
                if os.path.exists(dst):
                    os.remove(src)
                else:
                    os.rename(src, dst)


def relpath_to_root(path):
    rel = os.path.relpath(ROOT, os.path.dirname(path))
    return "" if rel == "." else rel + "/"


def local_target(site_path):
    """Map a site path ("/it/contatti/", "/wp-content/x.css") to the mirror path, or None."""
    p = html.unescape(site_path).split("#")[0].split("?")[0].lstrip("/")
    if p in ("", HOME.rstrip("/")):
        return HOME
    if p.endswith("/") or not os.path.splitext(p)[1]:
        p = p.rstrip("/") + "/"
        if os.path.isfile(os.path.join(ROOT, p, "index.html")):
            return p
        # WordPress serves pages without the /it/ prefix too (it redirects them)
        if os.path.isfile(os.path.join(ROOT, HOME, p, "index.html")):
            return HOME + p
        return None
    return p if os.path.isfile(os.path.join(ROOT, p)) else None


def fix_text(path, text):
    text = ASSET_SUFFIX_RE.sub(r"\1", text)
    text = FONT_HTML_RE.sub(r"\1", text)
    if not path.endswith(".html"):
        return text
    for pat in HEAD_CRUFT + TRACKING + COOKIE_BANNER:
        text = re.sub(pat, "", text, flags=re.S | re.I)
    rel_path = os.path.relpath(path, ROOT)
    # 404.html is served at any URL, so it needs root-relative links
    prefix = "/" if rel_path == "404.html" else relpath_to_root(path)

    # ?p=NN shortlinks (saved by wget as index.html@p=NN.html) -> real page
    text = re.sub(
        r'(["\'])(?:\.\./)*index\.html@p=(\d+)\.html(?=["\'#])',
        lambda m: m.group(1) + prefix + SHORTLINKS.get(m.group(2), HOME),
        text,
    )

    # absolute links to the original domain -> relative, when the target is in the mirror
    def abs_to_rel(m):
        target = local_target(m.group(3) or "/")
        if target is None:
            return m.group(0)
        anchor = m.group(3).split("#", 1)[1] if m.group(3) and "#" in m.group(3) else ""
        return m.group(1) + m.group(2) + prefix + target + ("#" + anchor if anchor else "")
    text = re.sub(r'((?:href|src)=)(["\'])' + DOMAIN_RE + r'(/[^"\']*)?(?=["\'])', abs_to_rel, text)

    # remaining links to pages of the original domain that don't exist here -> plain text
    text = re.sub(
        r'<a\s[^>]*href=["\']' + DOMAIN_RE + r'/[^"\']*["\'][^>]*>(.*?)</a>',
        lambda m: m.group(1),
        text,
        flags=re.S,
    )

    # relative links: duplicates, the root page, and "foo/index.html" -> directory form
    def fix_relative(m):
        link = m.group(2)
        if re.match(r"^(?:[a-z]+:|//|#|/)", link):
            return m.group(0)
        frag = "#" + link.split("#", 1)[1] if "#" in link else ""
        resolved = os.path.normpath(os.path.join(os.path.dirname(rel_path), link.split("#")[0]))
        resolved = "" if resolved == "." else resolved
        if resolved in DUPLICATES:
            return m.group(1) + prefix + DUPLICATES[resolved] + frag
        if resolved in ("", "index.html"):
            return m.group(1) + prefix + HOME + frag
        if resolved.startswith(HOME + HOME):
            fixed = local_target(resolved[len(HOME):])
            if fixed:
                return m.group(1) + prefix + fixed + frag
        if link.split("#")[0].endswith("index.html"):
            return m.group(1) + (link.split("#")[0][: -len("index.html")] or "./") + frag
        return m.group(0)
    text = re.sub(r'(href=["\'])([^"\']*)(?=["\'])', fix_relative, text)

    # Privacy: out of the main menu, into the footer next to the copyright
    text = re.sub(r'<li id="menu-item-\d+"[^>]*><a href="[^"]*privacy-policy/">Privacy</a></li>\s*', "", text)
    if not re.search(r'>Privacy</a>\s*</div><!-- end of \.copyright -->', text):
        text = re.sub(
            r'(</a>\s*)(</div><!-- end of \.copyright -->)',
            lambda m: m.group(1) + f' | <a href="{prefix}{PRIVACY}">Privacy</a>\n\t\t' + m.group(2),
            text,
            count=1,
        )
    return text


def main():
    rename_assets()
    find_duplicates()
    for dirpath, _, files in os.walk(ROOT):
        for f in files:
            if not f.endswith((".html", ".css", ".js")):
                continue
            p = os.path.join(dirpath, f)
            with open(p, encoding="utf-8", errors="surrogateescape") as fh:
                text = fh.read()
            new = fix_text(p, text)
            if new != text:
                with open(p, "w", encoding="utf-8", errors="surrogateescape") as fh:
                    fh.write(new)
    for f in os.listdir(ROOT):
        if re.fullmatch(r"index\.html@p=\d+\.html", f):
            os.remove(os.path.join(ROOT, f))
    for dup in DUPLICATES:
        os.remove(os.path.join(ROOT, dup))
    shutil.rmtree(os.path.join(ROOT, HOME, HOME), ignore_errors=True)
    shutil.rmtree(os.path.join(ROOT, COOKIE_PLUGIN_DIR), ignore_errors=True)
    # the original site redirects / to /it/
    with open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(
            '<!DOCTYPE html>\n<html lang="it">\n<head>\n<meta charset="utf-8">\n'
            '<title>Kanban</title>\n'
            f'<link rel="canonical" href="https://www.kanban.it/{HOME}">\n'
            f'<meta http-equiv="refresh" content="0; url={HOME}">\n'
            '</head>\n<body>\n'
            f'<p><a href="{HOME}">Kanban</a></p>\n'
            '</body>\n</html>\n'
        )
    # GitHub Pages: don't run Jekyll, serve files as-is
    open(os.path.join(ROOT, ".nojekyll"), "w").close()


if __name__ == "__main__":
    main()
