#!/usr/bin/env python3
"""블로그 굽기. 글 = posts/*.md 파일 하나.

    python3 build.py            # docs/ 를 다시 만든다(깃허브 페이지가 이 폴더를 보여 준다)
    python3 build.py --drafts   # 이름이 _ 로 시작하는 글 · draft: true 인 글도 넣는다(미리 보기)

글 쓰는 법은 posts/_template.md 에 있다. 덧붙일 꾸러미가 없다(파이썬만 있으면 된다).
"""
import html
import json
import re
import shutil
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "posts"
STATIC = ROOT / "static"
THEME = ROOT / "theme"
OUT = ROOT / "docs"
SITE = json.loads((ROOT / "site.json").read_text("utf-8"))
CATS = SITE["categories"]
CAT = {c["key"]: c for c in CATS}
DRAFTS = "--drafts" in sys.argv
E = html.escape


# ───────────────────────── 그림 조각

PIPS = {
    1: [(4, 4)],
    2: [(2, 2), (6, 6)],
    3: [(2, 2), (4, 4), (6, 6)],
    4: [(2, 2), (6, 2), (2, 6), (6, 6)],
    5: [(2, 2), (6, 2), (4, 4), (2, 6), (6, 6)],
    6: [(2, 2), (2, 4), (2, 6), (6, 2), (6, 4), (6, 6)],
    "?": [(3, 2), (4, 2), (5, 2), (5, 3), (4, 4), (4, 6)],
}


def die(n, cls=""):
    """도트 주사위. 몸 색은 CSS 의 --c, 눈 색은 --pip."""
    pips = "".join('<rect x="%d" y="%d" width="1" height="1"/>' % p for p in PIPS[n])
    return (
        '<svg class="die %s" viewBox="0 0 9 9" shape-rendering="crispEdges" aria-hidden="true">'
        '<path class="die-b" d="M1 0h7v1h1v7h-1v1h-7v-1h-1v-7h1z"/>'
        '<path class="die-s" d="M1 8h7v-1h1v1h-1v1h-7z"/>'
        '<g class="die-p">%s</g></svg>' % (cls, pips)
    )


def png_size(path):
    try:
        with open(path, "rb") as f:
            head = f.read(24)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", head[16:24])
    except OSError:
        pass
    return None


# ───────────────────────── 마크다운(쓰는 만큼만)

def secs(stamp):
    t = 0
    for part in stamp.split(":"):
        t = t * 60 + int(part)
    return t


def inline(s, ctx):
    codes = []

    def stash(m):
        codes.append("<code>%s</code>" % E(m.group(1)))
        return "\x00%d\x00" % (len(codes) - 1)

    s = re.sub(r"`([^`]+)`", stash, s)
    s = E(s, quote=False)

    def stamp(m):
        yt = ctx.get("youtube")
        if not yt:
            return '<span class="ts">%s</span>' % m.group(1)
        return '<a class="ts" href="https://www.youtube.com/watch?v=%s&amp;t=%ds" target="_blank" rel="noopener" title="영상의 이 대목 열기">%s</a>' % (
            yt, secs(m.group(1)), m.group(1))

    s = re.sub(r"\{(\d{1,2}(?::\d{2}){1,2})\}", stamp, s)
    s = s.replace("{?}", '<sup class="unsure" title="자동 자막에서 옮긴 값 · 확인 못 함">?</sup>')

    def link(m):
        text, url = m.group(1), m.group(2)
        if re.match(r"^https?://", url):
            return '<a href="%s" target="_blank" rel="noopener">%s</a>' % (url, text)
        if url.startswith("/"):
            url = ctx["root"] + url[1:]
        return '<a href="%s">%s</a>' % (url, text)

    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![*\w])\*([^*\n]+)\*(?![*\w])", r"<em>\1</em>", s)
    s = re.sub(r"~~(.+?)~~", r"<del>\1</del>", s)
    s = re.sub(r"==(.+?)==", r"<mark>\1</mark>", s)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], s)


LABELS = ("근거", "적용", "주의", "영상", "우리")
LIST_RE = re.compile(r"^(\s*)([-*]|\d+\.)\s+(.*)$")


def paragraph(text, ctx):
    m = re.match(r"^(%s)\s*[:：]\s*(.*)$" % "|".join(LABELS), text, re.S)
    if m:
        return '<p class="lab lab-%d"><span class="k">%s</span><span class="v">%s</span></p>' % (
            LABELS.index(m.group(1)), m.group(1), inline(m.group(2), ctx))
    return "<p>%s</p>" % inline(text, ctx)


def figure(alt, src, cap, ctx):
    local = None
    if not re.match(r"^https?://", src):
        local = STATIC / src.lstrip("/")
        src = ctx["root"] + src.lstrip("/")
    size = png_size(local) if local else None
    dims = ' width="%d" height="%d"' % size if size else ""
    cls = ' class="pixel"' if "/shots/" in src else ""
    out = '<figure><img src="%s" alt="%s"%s%s loading="lazy">' % (E(src), E(alt), dims, cls)
    if cap:
        out += "<figcaption>%s</figcaption>" % inline(cap, ctx)
    return out + "</figure>"


def container(kind, title, inner, ctx):
    body = blocks(inner, ctx)
    if kind == "take":
        ctx["takes"] = ctx.get("takes", 0) + 1
        n = ctx["takes"]
        badge = die(n) if n <= 6 else '<span class="num">%d</span>' % n
        return '<section class="take"><header>%s<h3>%s</h3></header><div class="take-b">%s</div></section>' % (
            badge, inline(title, ctx), body)
    if kind == "facts":
        head = '<p class="box-t">%s</p>' % inline(title, ctx) if title else ""
        return '<div class="facts">%s%s</div>' % (head, body)
    head = '<p class="box-t">%s</p>' % inline(title, ctx) if title else ""
    return '<aside class="box box-%s">%s%s</aside>' % (E(kind), head, body)


def blocks(lines, ctx):
    out, para = [], []
    i, n = 0, len(lines)

    def flush():
        if para:
            out.append(paragraph(" ".join(x.strip() for x in para), ctx))
            para.clear()

    while i < n:
        ln = lines[i]
        st = ln.strip()
        if not st:
            flush()
            i += 1
            continue

        m = re.match(r"^:::\s*(\w+)\s*(.*)$", st)
        if m:
            flush()
            depth, j, inner = 1, i + 1, []
            while j < n:
                s2 = lines[j].strip()
                if re.match(r"^:::\s*\w+", s2):
                    depth += 1
                elif s2 == ":::":
                    depth -= 1
                    if depth == 0:
                        break
                inner.append(lines[j])
                j += 1
            out.append(container(m.group(1), m.group(2).strip(), inner, ctx))
            i = j + 1
            continue

        m = re.match(r"^(#{2,4})\s+(.*)$", st)
        if m:
            flush()
            level = len(m.group(1))
            text = inline(m.group(2), ctx)
            if level == 2:
                ctx["toc"].append(re.sub(r"<[^>]+>", "", text))
                out.append('<h2 id="s%d">%s</h2>' % (len(ctx["toc"]), text))
            else:
                out.append("<h%d>%s</h%d>" % (level, text, level))
            i += 1
            continue

        if re.match(r"^-{3,}$", st):
            flush()
            out.append("<hr>")
            i += 1
            continue

        m = re.match(r'^!\[(.*?)\]\((\S+?)(?:\s+"(.*?)")?\)$', st)
        if m:
            flush()
            out.append(figure(m.group(1), m.group(2), m.group(3), ctx))
            i += 1
            continue

        m = re.match(r'^@\[youtube\]\(([\w-]+)(?:\s+"(.*?)")?\)$', st)
        if m:
            flush()
            out.append(video(m.group(1), m.group(2) or "유튜브 영상"))
            i += 1
            continue

        if st.startswith(">"):
            flush()
            inner = []
            while i < n and lines[i].strip().startswith(">"):
                inner.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            out.append("<blockquote>%s</blockquote>" % blocks(inner, ctx))
            continue

        if st.startswith("|") and i + 1 < n and re.match(r"^\|?\s*:?-{2,}", lines[i + 1].strip()):
            flush()
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            head, body = rows[0], rows[2:]
            t = "<thead><tr>%s</tr></thead>" % "".join("<th>%s</th>" % inline(c, ctx) for c in head)
            t += "<tbody>%s</tbody>" % "".join(
                "<tr>%s</tr>" % "".join("<td>%s</td>" % inline(c, ctx) for c in r) for r in body)
            out.append('<div class="table-wrap"><table>%s</table></div>' % t)
            continue

        m = LIST_RE.match(ln)
        if m:
            flush()
            indent = len(m.group(1))
            ordered = m.group(2)[0].isdigit()
            width = indent + len(m.group(2)) + 1
            items = []
            while i < n:
                l2 = lines[i]
                m2 = LIST_RE.match(l2)
                lead = len(l2) - len(l2.lstrip())
                if m2 and len(m2.group(1)) == indent and m2.group(2)[0].isdigit() == ordered:
                    items.append([m2.group(3)])
                    i += 1
                elif not l2.strip():
                    k = i + 1
                    while k < n and not lines[k].strip():
                        k += 1
                    if k >= n:
                        break
                    nxt = LIST_RE.match(lines[k])
                    nlead = len(lines[k]) - len(lines[k].lstrip())
                    if nlead > indent:
                        items[-1].append("")
                        i += 1
                    elif nxt and len(nxt.group(1)) == indent and nxt.group(2)[0].isdigit() == ordered:
                        i = k
                    else:
                        break
                elif lead > indent:
                    items[-1].append(l2[min(lead, width):])
                    i += 1
                else:
                    break
            lis = []
            for it in items:
                body = blocks(it, ctx)
                if body.count("<p") == 1 and body.startswith("<p>") and body.endswith("</p>"):
                    body = body[3:-4]
                lis.append("<li>%s</li>" % body)
            tag = "ol" if ordered else "ul"
            out.append("<%s>%s</%s>" % (tag, "".join(lis), tag))
            continue

        if st.startswith("<"):
            flush()
            raw = []
            while i < n and lines[i].strip():
                raw.append(lines[i])
                i += 1
            out.append("\n".join(raw))
            continue

        para.append(ln)
        i += 1

    flush()
    return "\n".join(out)


def video(yt, title):
    return (
        '<div class="video"><iframe src="https://www.youtube-nocookie.com/embed/%s" title="%s" loading="lazy" '
        'allow="accelerometer; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" '
        'referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe></div>' % (E(yt), E(title))
    )


# ───────────────────────── 글 읽기

def read_post(path):
    raw = path.read_text("utf-8")
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", raw, re.S)
    if not m:
        raise SystemExit("머리말(--- … ---)이 없다: %s" % path.name)
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"')
    nm = re.match(r"^_?(\d{4}-\d{2}-\d{2})-(.+)$", path.stem)
    meta.setdefault("date", nm.group(1) if nm else "")
    meta["slug"] = meta.get("slug") or (nm.group(2) if nm else path.stem.lstrip("_"))
    meta["tags"] = [t.strip() for t in meta.get("tags", "").strip("[]").split(",") if t.strip()]
    meta["draft"] = path.name.startswith("_") or meta.get("draft", "").lower() == "true"
    for need in ("title", "category", "date"):
        if not meta.get(need):
            raise SystemExit("머리말에 %s 이(가) 없다: %s" % (need, path.name))
    if meta["category"] not in CAT:
        raise SystemExit("모르는 갈래 '%s': %s (쓸 수 있는 것: %s)" % (meta["category"], path.name, ", ".join(CAT)))
    meta["body"] = m.group(2)
    meta["url"] = "%s/%s/" % (meta["category"], meta["slug"])
    meta["mins"] = max(1, round(len(re.sub(r"\s+", "", meta["body"])) / 600))
    return meta


def nice_date(d):
    y, mo, da = d.split("-")
    return "%s. %d. %d." % (y, int(mo), int(da))


# ───────────────────────── 화면 틀

THEME_BOOT = (
    "<script>(function(){try{var t=localStorage.getItem('theme');"
    "if(t==='light'||t==='dark')document.documentElement.setAttribute('data-theme',t);}catch(e){}})();</script>"
)


def page(title, body, root, desc=None, active=None, og_path="", og_type="website"):
    full = title + " · " + SITE["title"] if title else SITE["title"]
    desc = desc or SITE["description"]
    nav = "".join(
        '<a class="tab c-%s%s" href="%s%s/"%s>%s<span class="tab-l"><span class="long">%s</span><span class="short">%s</span></span></a>' % (
            c["key"], " on" if active == c["key"] else "", root, c["key"],
            ' aria-current="page"' if active == c["key"] else "",
            die(c["pips"]), E(c["name"]), E(c["short"]))
        for c in CATS)
    return """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{full}</title>
<meta name="description" content="{desc}">
<meta property="og:title" content="{full}">
<meta property="og:description" content="{desc}">
<meta property="og:type" content="{og_type}">
<meta property="og:url" content="{site}/{og_path}">
<meta property="og:image" content="{site}/{shot}">
<meta name="color-scheme" content="light dark">
{boot}
<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/galmuri@2.40.3/dist/galmuri.css">
<link rel="stylesheet" href="{root}assets/style.css">
<link rel="icon" href="{root}assets/favicon.svg" type="image/svg+xml">
</head>
<body>
<a class="skip" href="#main">본문으로</a>
<header class="top">
  <div class="wrap top-in">
    <a class="brand" href="{root}">{brand_die}<span>{name}</span></a>
    <nav class="tabs" aria-label="갈래">{nav}</nav>
    <button class="theme" type="button" aria-label="밝게 · 어둡게 바꾸기" title="밝게 · 어둡게">
      <svg viewBox="0 0 9 9" shape-rendering="crispEdges" aria-hidden="true"><path d="M3 0h3v1h1v1h1v1h1v3h-1v1h-1v1h-1v1h-3v-1h-1v-1h-1v-1h-1v-3h1v-1h1v-1h1z"/><path class="half" d="M5 1h1v1h1v1h1v3h-1v1h-1v1h-1z"/></svg>
    </button>
  </div>
</header>
<main id="main">
{body}
</main>
<footer class="foot">
  <div class="wrap foot-in">
    <span>{name}</span>
    <span class="foot-r"><a href="{root}">처음</a>{foot_links}</span>
  </div>
</footer>
<script src="{root}assets/app.js" defer></script>
</body>
</html>
""".format(
        full=E(full), desc=E(desc), og_type=og_type, site=SITE["site_url"], og_path=og_path,
        shot=SITE["game"]["shot"], boot=THEME_BOOT, root=root, brand_die=die(6, "brand-die"),
        name=E(SITE["title"]), nav=nav, body=body,
        foot_links="".join(' · <a href="%s%s/">%s</a>' % (root, c["key"], E(c["short"])) for c in CATS),
    )


def card(p, root, show_cat=True):
    c = CAT[p["category"]]
    chip = '<span class="chip c-%s">%s%s</span>' % (c["key"], die(c["pips"]), E(c["short"])) if show_cat else ""
    tags = "".join('<span class="tag">%s</span>' % E(t) for t in p["tags"][:4])
    draft = '<span class="tag draft">초안</span>' if p["draft"] else ""
    return (
        '<li class="card c-%s"><a href="%s%s">'
        '<div class="card-m">%s<time datetime="%s">%s</time><span class="mins">%d분</span>%s</div>'
        '<h3>%s</h3><p>%s</p><div class="tags">%s</div></a></li>' % (
            c["key"], root, p["url"], chip, p["date"], nice_date(p["date"]), p["mins"], draft,
            E(p["title"]), E(p.get("summary", "")), tags)
    )


def empty(c, root, small=False):
    return (
        '<div class="empty c-%s%s">%s<p class="empty-t">아직 글이 없습니다</p>'
        '<p class="empty-s">첫 글을 준비하고 있어요.</p></div>' % (
            c["key"], " small" if small else "", die("?", "big"))
    )


def render_home(posts):
    g = SITE["game"]
    size = png_size(STATIC / g["shot"]) or (960, 540)
    tiles = ""
    for c in CATS:
        cnt = sum(1 for p in posts if p["category"] == c["key"])
        tiles += (
            '<a class="tile c-%s" href="%s/">%s<span class="tile-n">%s</span>'
            '<span class="tile-b">%s</span><span class="tile-c%s">%s</span></a>' % (
                c["key"], c["key"], die(c["pips"], "big"), E(c["name"]), E(c["blurb"]),
                "" if cnt else " zero", ("글 %d" % cnt) if cnt else "준비 중")
        )
    latest = posts[:8]
    if latest:
        lst = '<ul class="cards">%s</ul>' % "".join(card(p, "") for p in latest)
    else:
        lst = empty({"key": "log"}, "")
    body = """
<section class="hero wrap">
  <div class="hero-t">
    <p class="kicker">DEV NOTES</p>
    <h1>{title}</h1>
    <p class="lede">{tagline}</p>
  </div>
  <figure class="now">
    <div class="now-f"><img class="pixel" src="{shot}" alt="{alt}" width="{w}" height="{h}"></div>
    <figcaption><span class="now-k">만드는 중</span><strong>{game}</strong><span class="now-l">{line}</span></figcaption>
  </figure>
</section>
<section class="wrap">
  <h2 class="sec">갈래</h2>
  <div class="tiles">{tiles}</div>
</section>
<section class="wrap">
  <h2 class="sec">새 글</h2>
  {lst}
</section>
""".format(title=E(SITE["title"]), tagline=E(SITE["tagline"]), shot=g["shot"], alt=E(g["shot_alt"]),
           w=size[0], h=size[1], game=E(g["name"]), line=E(g["line"]), tiles=tiles, lst=lst)
    return page("", body, "", desc=SITE["tagline"])


def render_cat(c, posts):
    mine = [p for p in posts if p["category"] == c["key"]]
    lst = '<ul class="cards">%s</ul>' % "".join(card(p, "../", False) for p in mine) if mine else empty(c, "../")
    body = """
<section class="cat-h wrap c-{key}">
  {die}
  <div><h1>{name}</h1><p class="lede">{blurb}</p></div>
  <span class="cat-c">{cnt}</span>
</section>
<section class="wrap">{lst}</section>
""".format(key=c["key"], die=die(c["pips"], "big"), name=E(c["name"]), blurb=E(c["blurb"]),
           cnt=("글 %d" % len(mine)) if mine else "준비 중", lst=lst)
    return page(c["name"], body, "../", desc=c["name"] + " — " + c["blurb"], active=c["key"], og_path=c["key"] + "/")


def render_post(p, posts):
    root = "../../"
    c = CAT[p["category"]]
    ctx = {"root": root, "toc": [], "youtube": p.get("youtube")}
    content = blocks(p["body"].splitlines(), ctx)
    toc = ""
    if len(ctx["toc"]) >= 3:
        toc = '<nav class="toc" aria-label="차례"><p class="toc-t">차례</p><ol>%s</ol></nav>' % "".join(
            '<li><a href="#s%d">%s</a></li>' % (k + 1, t) for k, t in enumerate(ctx["toc"]))
    source = ""
    if p.get("youtube"):
        source = (
            '<section class="source"><p class="source-k">원본 영상</p>%s'
            '<p class="source-m"><a href="https://www.youtube.com/watch?v=%s" target="_blank" rel="noopener">%s</a>'
            '<span>%s</span></p></section>' % (
                video(p["youtube"], p.get("source_title", "원본 영상")), p["youtube"],
                E(p.get("source_title", "유튜브에서 보기")),
                E(" · ".join(x for x in (p.get("source_channel"), p.get("source_length")) if x)))
        )
    k = posts.index(p)
    newer = posts[k - 1] if k > 0 else None
    older = posts[k + 1] if k + 1 < len(posts) else None
    pn = ""
    if newer or older:
        pn = '<nav class="pn" aria-label="앞뒤 글">%s%s</nav>' % (
            '<a class="pn-a" href="%s%s"><span>다음 글</span><strong>%s</strong></a>' % (root, newer["url"], E(newer["title"])) if newer else "<span></span>",
            '<a class="pn-a r" href="%s%s"><span>이전 글</span><strong>%s</strong></a>' % (root, older["url"], E(older["title"])) if older else "<span></span>")
    tags = "".join('<span class="tag">%s</span>' % E(t) for t in p["tags"])
    body = """
<article class="post c-{key}">
  <header class="post-h wrap narrow">
    <a class="chip c-{key}" href="{root}{key}/">{die}{cat}</a>
    <h1>{title}</h1>
    {summary}
    <p class="post-m"><time datetime="{date}">{nice}</time><span>읽는 데 {mins}분</span>{draft}</p>
    <div class="tags">{tags}</div>
  </header>
  <div class="wrap narrow prose">
    {source}
    {toc}
    {content}
  </div>
  <div class="wrap narrow">{pn}<p class="back"><a href="{root}{key}/">← {cat} 목록</a></p></div>
</article>
""".format(key=c["key"], root=root, die=die(c["pips"]), cat=E(c["name"]), title=E(p["title"]),
           summary='<p class="lede">%s</p>' % E(p["summary"]) if p.get("summary") else "",
           date=p["date"], nice=nice_date(p["date"]), mins=p["mins"],
           draft='<span class="tag draft">초안</span>' if p["draft"] else "",
           tags=tags, source=source, toc=toc, content=content, pn=pn)
    return page(p["title"], body, root, desc=p.get("summary"), active=c["key"], og_path=p["url"], og_type="article")


def render_404():
    base = SITE["base"]
    body = """
<section class="wrap"><div class="empty c-log">%s<p class="empty-t">없는 쪽입니다</p>
<p class="empty-s"><a href="%s">처음으로 돌아가기</a></p></div></section>
""" % (die("?", "big"), base)
    return page("없는 쪽", body, base)


FAVICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 9 9" shape-rendering="crispEdges">'
    '<path fill="#d9453b" d="M1 0h7v1h1v7h-1v1h-7v-1h-1v-7h1z"/>'
    '<g fill="#fffaf0">%s</g></svg>' % "".join('<rect x="%d" y="%d" width="1" height="1"/>' % p for p in PIPS[5])
)


def write(rel, text):
    path = OUT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, "utf-8")


def main():
    posts = []
    for f in sorted(SRC.glob("*.md")):
        p = read_post(f)
        if p["draft"] and not DRAFTS:
            continue
        posts.append(p)
    posts.sort(key=lambda p: (p["date"], p["slug"]), reverse=True)
    seen = {}
    for p in posts:
        if p["url"] in seen:
            raise SystemExit("주소가 겹친다: %s" % p["url"])
        seen[p["url"]] = 1

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    if STATIC.exists():
        shutil.copytree(STATIC, OUT, dirs_exist_ok=True)
    (OUT / "assets").mkdir(exist_ok=True)
    for f in THEME.iterdir():
        shutil.copy(f, OUT / "assets" / f.name)
    write("assets/favicon.svg", FAVICON)
    write(".nojekyll", "")

    write("index.html", render_home(posts))
    for c in CATS:
        write(c["key"] + "/index.html", render_cat(c, posts))
    for p in posts:
        write(p["url"] + "index.html", render_post(p, posts))
    write("404.html", render_404())
    print("구웠다: 글 %d편 → %s" % (len(posts), OUT))
    for c in CATS:
        print("  %s %d" % (c["name"], sum(1 for p in posts if p["category"] == c["key"])))


if __name__ == "__main__":
    main()
