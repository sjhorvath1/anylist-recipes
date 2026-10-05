#!/usr/bin/env python3
"""Build the recipe archive from recipes/*.html.

Run from the repo root (the publish workflow does this after writing a recipe):
  1. Adds the shared stylesheet and an "All recipes" link to any recipe page that lacks them.
  2. Writes recipes.json (one entry per recipe, used by the archive page).
  3. Writes index.html from site/index.template.html with that data embedded.

Standard library only; idempotent, so it is safe to run on every publish.
"""
import html
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECIPES = ROOT / "recipes"
TEMPLATE = ROOT / "site" / "index.template.html"

HEAD_MARK = 'data-site="style"'
NAV_MARK = 'data-site="nav"'
HEAD_SNIPPET = '<link rel="stylesheet" href="../site/recipe.css" data-site="style">\n'
NAV_SNIPPET = ('<nav class="site-nav" data-site="nav"><a href="../">&larr; All recipes</a></nav>\n')

FIELDS_SINGLE = {
    "name", "description", "recipeYield", "calories", "proteinContent", "fatContent",
    "carbohydrateContent", "fiberContent", "prepTime", "cookTime", "totalTime",
    "recipeCategory", "recipeCuisine", "keywords",
}


class RecipeParser(HTMLParser):
    """Collects schema.org microdata values (first occurrence of each single field, all ingredients)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.values = {}
        self.ingredients = []
        self.stack = []  # [tag, itemprop or None, text parts]
        self.title = None
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        prop = a.get("itemprop")
        if tag == "title":
            self._in_title = True
            self.title = ""
        if prop and "content" in a and (tag == "meta" or a["content"]):
            self._store(prop, a["content"])
            if tag == "meta":
                return
        if tag in ("meta", "link", "br", "img", "input", "hr"):
            return
        self.stack.append([tag, prop, []])

    def handle_startendtag(self, tag, attrs):
        a = dict(attrs)
        if a.get("itemprop") and "content" in a:
            self._store(a["itemprop"], a["content"])

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                closed = self.stack[i:]
                del self.stack[i:]
                for t, prop, parts in reversed(closed):
                    text = " ".join("".join(parts).split())
                    if prop and text:
                        self._store(prop, text)
                    if self.stack:  # text bubbles up to the parent
                        self.stack[-1][2].append(" " + "".join(parts) + " ")
                return

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self.stack:
            self.stack[-1][2].append(data)

    def _store(self, prop, value):
        value = " ".join(str(value).split())
        if prop == "recipeIngredient":
            self.ingredients.append(value)
        elif prop in FIELDS_SINGLE and prop not in self.values:
            self.values[prop] = value


def first_number(text):
    if not text:
        return None
    m = re.search(r"\d[\d,]*(?:\.\d+)?", text)
    return float(m.group(0).replace(",", "")) if m else None


def iso_minutes(text):
    """PT1H20M -> 80; '20 minutes' -> 20."""
    if not text:
        return None
    m = re.fullmatch(r"P(?:T)?(?:(\d+)H)?(?:(\d+)M)?", text.strip().upper())
    if m and (m.group(1) or m.group(2)):
        return int(m.group(1) or 0) * 60 + int(m.group(2) or 0)
    hours = re.search(r"(\d+)\s*h", text, re.I)
    mins = re.search(r"(\d+)\s*m", text, re.I)
    total = (int(hours.group(1)) * 60 if hours else 0) + (int(mins.group(1)) if mins else 0)
    return total or None


def added_date(path):
    try:
        out = subprocess.run(
            ["git", "log", "--diff-filter=A", "--format=%aI", "--", str(path.relative_to(ROOT))],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.split()
        if out:
            return out[-1][:10]
    except Exception:
        pass
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def ensure_site_chrome(path, text):
    changed = False
    if HEAD_MARK not in text and re.search(r"</head>", text, re.I):
        text = re.sub(r"</head>", HEAD_SNIPPET + "</head>", text, count=1, flags=re.I)
        changed = True
    if NAV_MARK not in text and re.search(r"<body[^>]*>", text, re.I):
        text = re.sub(r"(<body[^>]*>)", r"\1\n" + NAV_SNIPPET.replace("\\", "\\\\"), text, count=1, flags=re.I)
        changed = True
    if changed:
        path.write_text(text, encoding="utf-8")
    return text


def split_list(value):
    return [v.strip() for v in re.split(r"[,;]", value or "") if v.strip()]


def build_entry(path):
    text = path.read_text(encoding="utf-8")
    text = ensure_site_chrome(path, text)
    p = RecipeParser()
    p.feed(text)
    v = p.values
    slug = path.stem

    macros = {
        "calories": first_number(v.get("calories")),
        "protein": first_number(v.get("proteinContent")),
        "fiber": first_number(v.get("fiberContent")),
        "carbs": first_number(v.get("carbohydrateContent")),
        "fat": first_number(v.get("fatContent")),
    }
    # A few older pages list totals for the whole recipe; convert to per serving when the yield says how many.
    if re.search(r"entire recipe|whole recipe", v.get("calories", ""), re.I):
        servings = first_number(v.get("recipeYield"))
        macros = {k: (round(x / servings) if x is not None and servings else None) for k, x in macros.items()}
    macros = {k: (int(round(x)) if x is not None else None) for k, x in macros.items()}

    times = [iso_minutes(v.get(k)) for k in ("totalTime", "prepTime", "cookTime")]
    total = times[0] or (sum(t for t in times[1:] if t) or None)

    return {
        "slug": slug,
        "url": f"recipes/{slug}.html",
        "title": v.get("name") or (p.title or "").strip() or slug,
        "description": v.get("description", ""),
        "yield": v.get("recipeYield", ""),
        "mealType": v.get("recipeCategory", ""),
        "cuisine": v.get("recipeCuisine", ""),
        "keywords": split_list(v.get("keywords")),
        "minutes": total,
        "added": added_date(path),
        "ingredients": p.ingredients,
        **macros,
    }


def main():
    files = sorted(f for f in RECIPES.glob("*.html") if f.name != "index.html" and f.stem)
    entries = [build_entry(f) for f in files]
    entries.sort(key=lambda e: (e["added"], e["slug"]), reverse=True)

    (ROOT / "recipes.json").write_text(json.dumps(entries, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    data = json.dumps(entries, ensure_ascii=False, separators=(",", ":"))
    data = data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    fallback = "\n".join(
        f'<li><a href="{html.escape(e["url"])}">{html.escape(e["title"])}</a></li>' for e in sorted(entries, key=lambda e: e["title"].lower())
    )
    page = TEMPLATE.read_text(encoding="utf-8")
    for token, value in (("__RECIPES_JSON__", data), ("__FALLBACK_LIST__", fallback), ("__COUNT__", str(len(entries)))):
        if token not in page:
            sys.exit(f"Template is missing {token}")
        page = page.replace(token, value)
    (ROOT / "index.html").write_text(page, encoding="utf-8")
    print(f"Built index for {len(entries)} recipes")


if __name__ == "__main__":
    main()
