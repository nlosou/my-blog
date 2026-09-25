#!/usr/bin/env python3
"""极简静态博客生成器。

用法：
    python3 scripts/build.py            # 构建到 output/
    python3 scripts/build.py --clean    # 先清空 output/ 再构建

依赖：markdown、pygments、pyyaml（见 requirements.txt）。
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import os
import re
import shutil
from dataclasses import dataclass
from email.utils import format_datetime
from pathlib import Path

import markdown
import yaml
from markdown.extensions.toc import slugify_unicode

from highlight import HighlightCodePreprocessor

ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content"
POSTS_DIR = CONTENT_DIR / "posts"
PAGES_DIR = CONTENT_DIR / "pages"
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
OUTPUT_DIR = ROOT / "output"
CONFIG_FILE = ROOT / "config.yaml"

FRONT_MATTER_RE = re.compile(
    r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", re.DOTALL
)
PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def esc(value) -> str:
    """HTML/XML 属性与文本转义。"""
    return html.escape(str(value), quote=True)


def render(template: str, **ctx) -> str:
    """替换模板中的 {{ key }} 占位符。"""
    def repl(match: re.Match) -> str:
        value = ctx.get(match.group(1), "")
        return "" if value is None else str(value)

    return PLACEHOLDER_RE.sub(repl, template)


def render_list(template: str, items: list[dict]) -> str:
    """用同一个片段模板渲染一组条目。"""
    return "\n".join(render(template, **item) for item in items)


def slugify(value) -> str:
    """生成 ASCII slug；非 ASCII 标签退化为短哈希，避免空路径。"""
    s = str(value).strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if not s:
        s = "tag-" + hashlib.sha1(str(value).encode("utf-8")).hexdigest()[:8]
    return s


def valid_toc_depth(value: str) -> str:
    """校验 toc_depth，形如 '2' 或 '2-4'，非法时回退默认值。"""
    return value if re.fullmatch(r"[1-6](?:-[1-6])?", value) else "2-4"


def load_config() -> dict:
    raw = {}
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    site = raw.get("site", {}) or {}
    return {
        "title": str(site.get("title", "My Blog")),
        "description": str(site.get("description", "")),
        "author": str(site.get("author", "")),
        "base_url": str(site.get("base_url", "")).rstrip("/"),
        "language": str(site.get("language", "zh-CN")),
        "timezone_offset": str(site.get("timezone_offset", "+08:00")),
        "cname": str(site.get("cname", "")),
        "toc": bool(site.get("toc", True)),
        "toc_depth": valid_toc_depth(str(site.get("toc_depth", "2-4"))),
    }


def load_templates() -> dict:
    templates = {}
    for path in sorted(TEMPLATES_DIR.glob("*.html")):
        templates[path.stem] = path.read_text(encoding="utf-8")
    return templates


def parse_date(value) -> dt.datetime:
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, dt.date):
        return dt.datetime(value.year, value.month, value.day)
    if isinstance(value, str):
        text = value.strip()
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return dt.datetime.strptime(text, fmt)
            except ValueError:
                continue
        raise SystemExit(f"无法解析日期: {value!r}")
    raise SystemExit("front matter 缺少 date")


def parse_offset(offset: str) -> dt.timezone:
    m = re.match(r"([+-])(\d{2}):(\d{2})", offset)
    if not m:
        return dt.timezone.utc
    sign = 1 if m.group(1) == "+" else -1
    delta = dt.timedelta(hours=int(m.group(2)), minutes=int(m.group(3)))
    return dt.timezone(sign * delta)


def rfc3339(value: dt.datetime, tz: dt.timezone) -> str:
    return value.replace(tzinfo=tz).isoformat(timespec="seconds")


def parse_markdown_file(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    match = FRONT_MATTER_RE.match(text)
    if match:
        try:
            meta = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError as exc:
            raise SystemExit(f"front matter 解析失败: {path}: {exc}")
        body = text[match.end():]
    else:
        meta = {}
        body = text
    return meta, body


def markdown_to_html(text: str, toc_enabled: bool, toc_depth: str) -> tuple[str, str]:
    md = markdown.Markdown(
        extensions=["tables", "sane_lists", "attr_list", "toc"],
        extension_configs={
            "toc": {
                "marker": "",
                "toc_depth": toc_depth,
                "slugify": slugify_unicode,
                "title": "目录",
                "title_class": "toc-title",
            }
        },
    )
    md.preprocessors.register(HighlightCodePreprocessor(md), "highlight_code", 25)
    body = md.convert(text)
    toc_html = md.toc if (toc_enabled and md.toc_tokens) else ""
    return body, toc_html


def normalize_tags(value) -> list[str]:
    if value is None:
        return []
    raw = [value] if isinstance(value, str) else list(value)
    out: list[str] = []
    for item in raw:
        for part in str(item).split(","):
            part = part.strip()
            if part and part not in out:
                out.append(part)
    return out


@dataclass
class Post:
    slug: str
    title: str
    date: dt.datetime
    tags: list
    summary: str
    content_html: str
    toc_html: str


@dataclass
class Page:
    slug: str
    title: str
    content_html: str


def load_posts(cfg: dict) -> list[Post]:
    posts = []
    if not POSTS_DIR.exists():
        return posts
    for path in sorted(POSTS_DIR.glob("*.md")):
        meta, body = parse_markdown_file(path)
        if meta.get("draft"):
            continue
        toc_enabled = bool(meta["toc"]) if "toc" in meta else cfg["toc"]
        body_html, toc_html = markdown_to_html(body, toc_enabled, cfg["toc_depth"])
        posts.append(
            Post(
                slug=slugify(meta.get("slug") or path.stem),
                title=str(meta.get("title") or path.stem),
                date=parse_date(meta.get("date")),
                tags=normalize_tags(meta.get("tags")),
                summary=str(meta.get("summary") or ""),
                content_html=body_html,
                toc_html=toc_html,
            )
        )
    posts.sort(key=lambda p: p.date, reverse=True)
    return posts


def load_pages(cfg: dict) -> list[Page]:
    pages = []
    if not PAGES_DIR.exists():
        return pages
    for path in sorted(PAGES_DIR.glob("*.md")):
        meta, body = parse_markdown_file(path)
        if meta.get("draft"):
            continue
        body_html, _ = markdown_to_html(body, False, cfg["toc_depth"])
        pages.append(
            Page(
                slug=slugify(meta.get("slug") or path.stem),
                title=str(meta.get("title") or path.stem),
                content_html=body_html,
            )
        )
    return pages


def build_tags(posts: list[Post]) -> dict[str, list[Post]]:
    mapping: dict[str, list[Post]] = {}
    for post in posts:
        for tag in post.tags:
            mapping.setdefault(tag, []).append(post)
    return mapping


def relative_root(out_dir: Path) -> str:
    rel = os.path.relpath(OUTPUT_DIR, out_dir).replace(os.sep, "/")
    return "." if rel == "" else rel


def tag_links_html(tags: list[str], root: str) -> str:
    parts = []
    for tag in tags:
        href = f"{root}/tags/{slugify(tag)}/"
        parts.append(f'<a class="tag" href="{esc(href)}">{esc(tag)}</a>')
    return " ".join(parts)


def post_item(post: Post, root: str) -> dict:
    summary_html = f'<p class="summary">{esc(post.summary)}</p>' if post.summary else ""
    return {
        "title": esc(post.title),
        "url": f"{root}/posts/{post.slug}/",
        "date": post.date.strftime("%Y-%m-%d"),
        "date_iso": post.date.strftime("%Y-%m-%d"),
        "tag_links": tag_links_html(post.tags, root),
        "summary_html": summary_html,
    }


def render_full(body: str, *, page_title: str, description: str, root: str,
                tpl: dict, cfg: dict) -> str:
    site_title = esc(cfg["title"])
    title = f"{esc(page_title)} · {site_title}" if page_title else site_title
    return render(
        tpl["base"],
        site_title=site_title,
        title=title,
        description=esc(description),
        author=esc(cfg["author"]),
        language=esc(cfg["language"]),
        year=str(dt.date.today().year),
        root=root,
        content=body,
    )


def write_file(rel: str, content: str) -> None:
    path = OUTPUT_DIR / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_archive(posts: list[Post], root: str) -> str:
    by_year: dict[int, list[Post]] = {}
    for post in posts:
        by_year.setdefault(post.date.year, []).append(post)

    parts = []
    for year in sorted(by_year, reverse=True):
        parts.append(f"<h2>{year}</h2>")
        parts.append('<ul class="archive-list">')
        for post in by_year[year]:
            date = post.date.strftime("%Y-%m-%d")
            parts.append(
                f'<li><time datetime="{date}">{date}</time> '
                f'<a href="{root}/posts/{post.slug}/">{esc(post.title)}</a></li>'
            )
        parts.append("</ul>")
    return "\n".join(parts)


def build_atom(posts: list[Post], cfg: dict, tz: dt.timezone) -> str:
    base = cfg["base_url"]
    updated = max((p.date for p in posts), default=dt.datetime.now())
    entries = []
    for post in posts:
        url = f"{base}/posts/{post.slug}/"
        categories = "\n".join(
            f'    <category term="{esc(tag)}"/>' for tag in post.tags
        )
        summary = f"    <summary>{esc(post.summary)}</summary>\n" if post.summary else ""
        entries.append(
            "  <entry>\n"
            f"    <title>{esc(post.title)}</title>\n"
            f'    <link href="{esc(url)}"/>\n'
            f"    <id>{esc(url)}</id>\n"
            f"    <published>{rfc3339(post.date, tz)}</published>\n"
            f"    <updated>{rfc3339(post.date, tz)}</updated>\n"
            f"{summary}"
            f'    <content type="html">{esc(post.content_html)}</content>\n'
            f"{categories}\n"
            "  </entry>"
        )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom">\n'
        f"  <title>{esc(cfg['title'])}</title>\n"
        f'  <link href="{esc(base + "/atom.xml")}" rel="self"/>\n'
        f'  <link href="{esc(base + "/")}"/>\n'
        f"  <id>{esc(base + '/')}</id>\n"
        f"  <updated>{rfc3339(updated, tz)}</updated>\n"
        f"  <author><name>{esc(cfg['author'])}</name></author>\n"
        "  <generator>my-blog</generator>\n"
        + "\n".join(entries)
        + "\n</feed>\n"
    )


def build_rss(posts: list[Post], cfg: dict, tz: dt.timezone) -> str:
    base = cfg["base_url"]
    now = dt.datetime.now(tz)
    items = []
    for post in posts:
        url = f"{base}/posts/{post.slug}/"
        categories = "".join(
            f"      <category>{esc(tag)}</category>\n" for tag in post.tags
        )
        items.append(
            "    <item>\n"
            f"      <title>{esc(post.title)}</title>\n"
            f"      <link>{esc(url)}</link>\n"
            f'      <guid isPermaLink="true">{esc(url)}</guid>\n'
            f"      <pubDate>{format_datetime(post.date.replace(tzinfo=tz))}</pubDate>\n"
            f"      <description>{esc(post.content_html)}</description>\n"
            f"{categories}"
            "    </item>"
        )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "  <channel>\n"
        f"    <title>{esc(cfg['title'])}</title>\n"
        f"    <link>{esc(base + '/')}</link>\n"
        f"    <description>{esc(cfg['description'])}</description>\n"
        f"    <language>{esc(cfg['language'])}</language>\n"
        f"    <lastBuildDate>{format_datetime(now)}</lastBuildDate>\n"
        f'    <atom:link href="{esc(base + "/rss.xml")}" rel="self" type="application/rss+xml"/>\n'
        "    <generator>my-blog</generator>\n"
        + "\n".join(items)
        + "\n  </channel>\n"
        "</rss>\n"
    )


def build_sitemap(posts: list[Post], pages: list[Page], tags: dict, cfg: dict) -> str:
    base = cfg["base_url"]
    parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]

    def add(url: str, lastmod: str | None = None) -> None:
        loc = f"{base}/{url}"
        if lastmod:
            parts.append(f"  <url><loc>{esc(loc)}</loc><lastmod>{lastmod}</lastmod></url>")
        else:
            parts.append(f"  <url><loc>{esc(loc)}</loc></url>")

    add("")
    for post in posts:
        add(f"posts/{post.slug}/", post.date.strftime("%Y-%m-%d"))
    for page in pages:
        add(f"{page.slug}/")
    add("tags/")
    for tag in sorted(tags):
        add(f"tags/{slugify(tag)}/")
    parts.append("</urlset>")
    return "\n".join(parts) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="构建静态博客")
    parser.add_argument("--clean", action="store_true", help="构建前清空 output/")
    args = parser.parse_args()

    cfg = load_config()
    tpl = load_templates()
    posts = load_posts(cfg)
    pages = load_pages(cfg)
    tags = build_tags(posts)
    tz = parse_offset(cfg["timezone_offset"])

    if args.clean and OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 首页
    home_root = relative_root(OUTPUT_DIR)
    if posts:
        home_items = [post_item(p, home_root) for p in posts]
        post_list_html = render_list(tpl["_post_item"], home_items)
    else:
        post_list_html = "<p>还没有文章。</p>"
    home_body = render(tpl["index"], post_list=post_list_html)
    write_file(
        "index.html",
        render_full(home_body, page_title="", description=cfg["description"],
                    root=home_root, tpl=tpl, cfg=cfg),
    )

    # 文章页
    for post in posts:
        out_dir = OUTPUT_DIR / "posts" / post.slug
        root = relative_root(out_dir)
        body = render(
            tpl["post"],
            title=esc(post.title),
            date=post.date.strftime("%Y-%m-%d"),
            date_iso=post.date.strftime("%Y-%m-%d"),
            tag_links=tag_links_html(post.tags, root),
            toc=post.toc_html,
            content=post.content_html,
        )
        write_file(
            f"posts/{post.slug}/index.html",
            render_full(body, page_title=post.title, description=post.summary or cfg["description"],
                        root=root, tpl=tpl, cfg=cfg),
        )

    # 标签总览
    tags_root = relative_root(OUTPUT_DIR / "tags")
    tag_items = [
        {"url": f"{tags_root}/tags/{slugify(tag)}/", "tag": esc(tag), "count": str(len(posts_))}
        for tag, posts_ in sorted(tags.items(), key=lambda kv: kv[0].lower())
    ]
    tags_body = render(tpl["tags"], tag_list=render_list(tpl["_tag_item"], tag_items))
    write_file(
        "tags/index.html",
        render_full(tags_body, page_title="标签", description="全部标签",
                    root=tags_root, tpl=tpl, cfg=cfg),
    )

    # 单标签页
    for tag, posts_ in sorted(tags.items(), key=lambda kv: kv[0].lower()):
        out_dir = OUTPUT_DIR / "tags" / slugify(tag)
        root = relative_root(out_dir)
        items = [post_item(p, root) for p in posts_]
        body = render(tpl["tag"], tag=esc(tag), post_list=render_list(tpl["_post_item"], items))
        write_file(
            f"tags/{slugify(tag)}/index.html",
            render_full(body, page_title=f"标签：{tag}", description=f"标签 {tag} 下的文章",
                        root=root, tpl=tpl, cfg=cfg),
        )

    # 归档页
    archive_root = relative_root(OUTPUT_DIR / "archive")
    archive_body = render(tpl["archive"], archive=build_archive(posts, archive_root))
    write_file(
        "archive/index.html",
        render_full(archive_body, page_title="归档", description="按年份归档",
                    root=archive_root, tpl=tpl, cfg=cfg),
    )

    # 固定页面
    for page in pages:
        out_dir = OUTPUT_DIR / page.slug
        root = relative_root(out_dir)
        body = render(tpl["page"], title=esc(page.title), content=page.content_html)
        write_file(
            f"{page.slug}/index.html",
            render_full(body, page_title=page.title, description=cfg["description"],
                        root=root, tpl=tpl, cfg=cfg),
        )

    # 404
    not_found_root = relative_root(OUTPUT_DIR)
    body_404 = render(tpl["404"], root=not_found_root)
    write_file(
        "404.html",
        render_full(body_404, page_title="404", description="页面不存在",
                    root=not_found_root, tpl=tpl, cfg=cfg),
    )

    # Feeds 与 sitemap
    write_file("atom.xml", build_atom(posts, cfg, tz))
    write_file("rss.xml", build_rss(posts, cfg, tz))
    write_file("sitemap.xml", build_sitemap(posts, pages, tags, cfg))

    # 静态资源
    if STATIC_DIR.exists():
        for src in STATIC_DIR.rglob("*"):
            if src.is_file():
                rel = src.relative_to(STATIC_DIR)
                dest = OUTPUT_DIR / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)

    # robots.txt（按 base_url 动态生成）
    write_file(
        "robots.txt",
        f"User-agent: *\nAllow: /\nSitemap: {cfg['base_url']}/sitemap.xml\n",
    )

    # GitHub Pages 相关
    write_file(".nojekyll", "")
    if cfg["cname"]:
        write_file("CNAME", cfg["cname"] + "\n")

    print(f"构建完成：{len(posts)} 篇文章，{len(tags)} 个标签，{len(pages)} 个页面")
    print(f"输出目录：{OUTPUT_DIR}")


if __name__ == "__main__":
    main()
