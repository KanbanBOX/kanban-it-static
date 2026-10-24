#!/usr/bin/env bash
# Rebuild the static mirror of www.kanban.it into ./docs
set -euo pipefail
cd "$(dirname "$0")/.."

BASE=https://www.kanban.it
OUT=docs
URLS=$(mktemp)
trap 'rm -f "$URLS"' EXIT

# once the domain points to GitHub Pages, the WordPress origin must be reached through /etc/hosts
if ! curl -fsSL -o /dev/null "$BASE/wp-json/"; then
  echo "WordPress non raggiungibile su $BASE (il DNS punta a GitHub Pages?)." >&2
  echo "Aggiungi temporaneamente a /etc/hosts:  3.123.199.162 www.kanban.it" >&2
  exit 1
fi

# the REST API returns page links without the /it/ prefix the site actually uses
pages_json=$(curl -fsSL "$BASE/wp-json/wp/v2/pages/?per_page=100&_fields=id,link")

# seed: the home page and every page
echo "$BASE/it/" > "$URLS"
python3 -c '
import json, sys
for x in json.loads(sys.argv[1]):
    print(x["link"].replace("https://www.kanban.it/", "https://www.kanban.it/it/", 1))
' "$pages_json" >> "$URLS"

# post id -> path, used to rewrite ?p=NN shortlinks in the menu
python3 -c '
import json, re, sys
d = {str(x["id"]): "it/" + re.sub(r"^https?://www\.kanban\.it/", "", x["link"]) for x in json.loads(sys.argv[1])}
json.dump(d, open("tools/shortlinks.json", "w"), indent=1, sort_keys=True)
' "$pages_json"

rm -rf "$OUT"
# wget exits 8 when some extracted URL returns an error; that's expected
wget --mirror --page-requisites --convert-links --adjust-extension --restrict-file-names=windows \
  --no-host-directories --domains=www.kanban.it,kanban.it \
  -e robots=off --wait=0.2 --no-verbose \
  --reject-regex='(xmlrpc\.php|wp-json|/feed/|wp-login|replytocom|/comments/|wlwmanifest|wp-admin|%7B|%5C)' \
  -i "$URLS" -P "$OUT" || [ $? -eq 8 ]

# WordPress' own "not found" page, served by GitHub Pages for any missing URL
curl -sS -o "$OUT/404.html" "$BASE/it/pagina-inesistente-404/"

# self-hosted assets that replace or complete the mirrored ones
[ -d static ] && cp -r static/. "$OUT/"
python3 tools/postprocess.py "$OUT"
[ -f CNAME ] && cp CNAME "$OUT/CNAME"
echo "Built $(find "$OUT" -name '*.html' | wc -l) pages in $OUT/"
