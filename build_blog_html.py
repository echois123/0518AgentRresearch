import html
import re
import shutil
from pathlib import Path
from typing import Optional

from lxml import html as lxml_html
from markdown_it import MarkdownIt
from PIL import Image


SRC = Path("/Users/xyf/Documents/New project 3/Final版本_统一排版版.md")
OUT = Path("/Users/xyf/Documents/New project 3/Final版本_统一排版版_blog.html")
PREVIEW_DIR = SRC.parent / ".preview-cache"
DEPLOY_DIR = SRC.parent / "docs"
PREVIEW_COMMON_WIDTH = 1200
PREVIEW_DETAIL_WIDTH = 900


def strip_outer_wrapper(text: str) -> str:
    text = re.sub(r"<style>.*?</style>\s*", "", text, count=1, flags=re.S)
    text = text.replace('<div class="report-doc">', "", 1)
    text = re.sub(r"\n?</div>\s*$", "", text.strip(), count=1)
    return text.strip() + "\n"


def normalize_summary_title(line: str) -> str:
    match = re.match(r'\s*<p class="summary-title">(.*?)</p>\s*', line)
    if not match:
        return line
    content = match.group(1).strip()
    return f'<p class="summary-title">{content}</p>'


def preprocess_markdown(text: str) -> str:
    lines = text.splitlines()
    processed = []
    skip_manual_toc = False

    for line in lines:
        if line.strip() == "## **🎲 目录**":
            skip_manual_toc = True
            continue
        if skip_manual_toc:
            if line.strip() == "---":
                skip_manual_toc = False
            continue
        processed.append(normalize_summary_title(line))

    result = "\n".join(processed)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip() + "\n"


def strip_inline_formatting(text: str) -> str:
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"_([^_]+)_", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def slugify(text: str, seen: dict[str, int]) -> str:
    base = strip_inline_formatting(text).lower()
    base = re.sub(r"[“”\"'‘’]", "", base)
    base = re.sub(r"[^\w\u4e00-\u9fff\s\-]+", "", base)
    base = re.sub(r"\s+", "-", base).strip("-")
    if not base:
        base = "section"
    count = seen.get(base, 0)
    seen[base] = count + 1
    return base if count == 0 else f"{base}-{count + 1}"


def collect_headings(markdown_text: str) -> list[dict]:
    headings = []
    seen: dict[str, int] = {}
    for line in markdown_text.splitlines():
        match = re.match(r"^(#{2,4})\s+(.*)$", line)
        if not match:
            continue
        level = len(match.group(1))
        raw_title = match.group(2).strip()
        plain_title = strip_inline_formatting(raw_title)
        if "目录" in plain_title:
            continue
        slug = slugify(plain_title, seen)
        headings.append(
            {
                "level": level,
                "raw": raw_title,
                "plain": plain_title,
                "slug": slug,
            }
        )
    return headings


def inject_heading_ids(html_body: str, headings: list[dict]) -> str:
    iterator = iter(headings)

    def replace(match: re.Match) -> str:
        heading = next(iterator, None)
        if heading is None:
            return match.group(0)
        tag = match.group(1)
        inner = match.group(2)
        return f'<{tag} id="{html.escape(heading["slug"], quote=True)}">{inner}</{tag}>'

    return re.sub(r"<(h[2-4])>(.*?)</\1>", replace, html_body, flags=re.S)


def wrap_tables(html_body: str) -> str:
    return re.sub(r"<table>(.*?)</table>", r'<div class="table-wrap"><table>\1</table></div>', html_body, flags=re.S)


def _node_text(node) -> str:
    return "".join(node.itertext()).replace("\xa0", " ").strip()


def _add_class(node, class_name: str) -> None:
    current = node.get("class", "").strip()
    parts = current.split() if current else []
    if class_name not in parts:
        parts.append(class_name)
    node.set("class", " ".join(parts).strip())


def ensure_preview_image(src_value: str, *, width: int) -> Optional[str]:
    source_path = SRC.parent / src_value
    if not source_path.exists() or not source_path.is_file():
        return None

    PREVIEW_DIR.mkdir(exist_ok=True)
    preview_name = f"{source_path.stem}-w{width}.webp"
    preview_path = PREVIEW_DIR / preview_name

    needs_regen = (
        not preview_path.exists()
        or preview_path.stat().st_mtime < source_path.stat().st_mtime
    )
    if needs_regen:
        with Image.open(source_path) as image:
            image = image.convert("RGB")
            if image.width > width:
                target_height = max(1, round(image.height * width / image.width))
                image = image.resize((width, target_height), Image.Resampling.LANCZOS)
            image.save(preview_path, format="WEBP", quality=92, method=6)

    return f".preview-cache/{preview_name}"


def optimize_article_images(html_body: str) -> str:
    root = lxml_html.fragment_fromstring(html_body, create_parent="div")
    images = root.xpath(".//img[@src]")

    for image in images:
        original_src = image.get("src", "").strip()
        if not original_src or re.match(r"^(https?:|data:)", original_src):
            continue

        class_names = set((image.get("class") or "").split())
        preview_width = PREVIEW_COMMON_WIDTH if "common-shot" in class_names else PREVIEW_DETAIL_WIDTH
        preview_src = ensure_preview_image(original_src, width=preview_width)
        if not preview_src:
            continue

        image.set("data-fullsrc", original_src)
        image.set("src", preview_src)
        image.set("fetchpriority", "low")

    return "".join(
        lxml_html.tostring(child, encoding="unicode")
        for child in root
    )


def build_deploy_bundle() -> None:
    if DEPLOY_DIR.exists():
        shutil.rmtree(DEPLOY_DIR)
    DEPLOY_DIR.mkdir(parents=True, exist_ok=True)

    shutil.copy2(OUT, DEPLOY_DIR / "index.html")

    preview_target = DEPLOY_DIR / ".preview-cache"
    if PREVIEW_DIR.exists():
        shutil.copytree(PREVIEW_DIR, preview_target)

    for pattern in ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.gif", "*.svg"):
        for asset in SRC.parent.glob(pattern):
            if asset.name == OUT.name:
                continue
            shutil.copy2(asset, DEPLOY_DIR / asset.name)

    (DEPLOY_DIR / ".nojekyll").write_text("", encoding="utf-8")


def postprocess_article_html(html_body: str) -> str:
    root = lxml_html.fragment_fromstring(html_body, create_parent="div")
    for heading in root.xpath(".//h4"):
        if _node_text(heading).strip().startswith("阶段"):
            _add_class(heading, "stage-heading")
    tables = root.xpath(".//table")

    for table in tables:
        first_header_nodes = table.xpath("./thead/tr[1]/th[1]")
        first_header_text = _node_text(first_header_nodes[0]) if first_header_nodes else ""
        first_header_text_compact = first_header_text.replace(" ", "")

        if first_header_text.startswith("1️⃣ DeepSeek 本身") or first_header_text.startswith("1️⃣ OpenAI Codex 更像"):
            _add_class(table, "plain-list-table")
            for th in table.xpath(".//th"):
                th.tag = "td"

        header_cells = table.xpath("./thead/tr[1]/th|./thead/tr[1]/td")
        header_texts = [_node_text(cell).strip() for cell in header_cells]
        if header_texts == ["CodeX", "Claude Code"]:
            _add_class(table, "equal-two-col-table")
        elif len(header_texts) == 2 and first_header_text not in {"分类", "维度"}:
            _add_class(table, "equal-two-col-table")
        elif not header_texts:
            first_row_cells = table.xpath("./tbody/tr[1]/td|./tbody/tr[1]/th")
            if len(first_row_cells) == 2:
                _add_class(table, "equal-two-col-table")
        if first_header_text == "分类":
            _add_class(table, "category-stack-table")
        if first_header_text == "维度":
            _add_class(table, "dimension-compare-table")
        if first_header_text == "关系阶段":
            _add_class(table, "relationship-stage-table")

        if "equal-two-col-table" in (table.get("class", "") or "").split():
            for row in table.xpath("./tbody/tr"):
                cells = row.xpath("./td|./th")
                if len(cells) != 2:
                    continue
                is_emphasis_row = True
                for cell in cells:
                    non_empty_children = [
                        child for child in cell
                        if isinstance(getattr(child, "tag", None), str)
                    ]
                    cell_text = (cell.text or "").strip()
                    tail_text = "".join((child.tail or "") for child in non_empty_children).strip()
                    if cell_text or tail_text or len(non_empty_children) != 1 or non_empty_children[0].tag != "strong":
                        is_emphasis_row = False
                        break
                if is_emphasis_row:
                    _add_class(row, "emphasis-row")

        if (
            first_header_text_compact.startswith("共性趋势1｜更联通")
            or first_header_text_compact.startswith("共性趋势2｜更懂我")
            or first_header_text_compact.startswith("共性趋势3｜更靠谱")
        ):
            _add_class(table, "trend-table")
            for row in table.xpath("./tbody/tr"):
                cells = row.xpath("./td|./th")
                if not cells:
                    continue
                first_cell_text = _node_text(cells[0])
                if len(cells) >= 3 and not _node_text(cells[1]) and not _node_text(cells[2]):
                    cells[0].set("colspan", str(len(cells)))
                    for extra in cells[1:]:
                        extra.getparent().remove(extra)
                    continue
                if first_cell_text.startswith("🧒 用户体验") or first_cell_text.startswith("💆 用户体验") or first_cell_text.startswith("🙋 用户体验") or first_cell_text.startswith("👤 用户体验"):
                    cells[0].set("colspan", str(len(cells)))
                    for extra in cells[1:]:
                        extra.getparent().remove(extra)
                if (
                    first_cell_text.startswith("用户无需频繁切换工具")
                    or first_cell_text.startswith("用户可以用更少的解释成本")
                    or first_cell_text.startswith("用户不再只是获得 demo 级别的结果")
                ):
                    cells[0].set("colspan", str(len(cells)))
                    for extra in cells[1:]:
                        extra.getparent().remove(extra)

        if first_header_text.startswith("用户的体验旅程"):
            _add_class(table, "analysis-framework-table")
            colgroup = lxml_html.fragment_fromstring(
                (
                    "<colgroup>"
                    '<col class="analysis-col-journey">'
                    '<col class="analysis-col-equal">'
                    '<col class="analysis-col-equal">'
                    '<col class="analysis-col-equal">'
                    '<col class="analysis-col-equal">'
                    '<col class="analysis-col-equal">'
                    "</colgroup>"
                )
            )
            table.insert(0, colgroup)
            for row in table.xpath("./tbody/tr"):
                first_cells = row.xpath("./td[1]")
                if not first_cells:
                    continue
                label = _node_text(first_cells[0])
                if label in {"用户的心理模型", "用户期望的伙伴画像", "产品体验关注点", "产品转化流失点"}:
                    _add_class(first_cells[0], "vertical-label")

    inner = "".join(
        lxml_html.tostring(child, encoding="unicode")
        for child in root
    )
    inner = inner.replace("<strong>伙伴画像</strong>：", "<br><strong>伙伴画像</strong>：")
    return inner


def build_toc(headings: list[dict]) -> str:
    hidden_keywords = ("阶段一", "阶段二", "阶段三", "阶段四", "阶段五")
    hidden_titles = {"订阅模式对比", "模式的判断与启示"}
    blocks = []
    for item in headings:
        if any(keyword in item["plain"] for keyword in hidden_keywords):
            continue
        if item["plain"] in hidden_titles:
            continue
        extra_class = " toc-link-nested" if item["plain"].startswith(("2.2.2.1", "2.2.2.2")) else ""
        label = item["plain"]
        blocks.append(
            f'<a class="toc-link level-{item["level"]}{extra_class}" href="#{html.escape(item["slug"], quote=True)}">{html.escape(label)}</a>'
        )
    return "\n".join(blocks)


def render_html(markdown_text: str) -> str:
    md = MarkdownIt("default", {"html": True, "linkify": False, "breaks": False})
    return md.render(markdown_text)


def build_page(article_html: str, toc_html: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Agent 竞品调研</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    :root {{
      --bg: #ffffff;
      --paper: #ffffff;
      --text: #171717;
      --muted: #666666;
      --line: #e7e5e4;
      --accent: #111111;
      --accent-soft: #f6f5f2;
      --quote-bg: #fafaf9;
      --sans: "Inter", "PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
      --serif: "Inter", "PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
    }}
    * {{
      box-sizing: border-box;
    }}
    html {{
      scroll-behavior: smooth;
    }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: var(--sans);
      -webkit-font-smoothing: antialiased;
      text-rendering: optimizeLegibility;
    }}
    .layout {{
      max-width: 1480px;
      margin: 0 auto;
      padding: 32px 28px 96px;
      display: grid;
      grid-template-columns: 260px minmax(0, 1fr);
      column-gap: 56px;
      align-items: start;
    }}
    .main {{
      min-width: 0;
      grid-column: 2;
    }}
    .hero {{
      max-width: 860px;
      margin: 0 0 48px;
      padding-top: 32px;
    }}
    .hero h1 {{
      margin: 0 0 18px;
      font-size: 64px;
      line-height: 1.02;
      letter-spacing: -0.05em;
      font-weight: 800;
    }}
    .article {{
      max-width: 860px;
      margin: 0;
      padding: 0;
      background: transparent;
      border: 0;
      border-radius: 0;
      box-shadow: none;
    }}
    .article h1,
    .article h2,
    .article h3,
    .article h4 {{
      margin: 40px 0 16px;
      line-height: 1.4;
      font-weight: 700;
      scroll-margin-top: 24px;
      color: #191919;
    }}
    .article h2:first-child {{
      margin-top: 0;
    }}
    .article h2 {{
      margin-top: 50px;
      font-size: 28px;
      letter-spacing: -0.018em;
    }}
    .article h3 {{
      font-size: 24px;
      letter-spacing: -0.014em;
    }}
    .article h4 {{
      font-size: 20px;
      letter-spacing: -0.01em;
    }}
    .article h4.stage-heading {{
      font-size: 16px;
      line-height: 1.5;
      font-weight: 700;
      letter-spacing: 0;
      margin-top: 32px;
    }}
    .article h5,
    .article h6 {{
      margin: 28px 0 14px;
      font-size: 20px;
      line-height: 1.4;
      font-weight: 700;
      color: #191919;
      letter-spacing: -0.01em;
    }}
    .article p,
    .article li {{
      font-size: 16px;
      line-height: 1.8;
      color: var(--text);
    }}
    .article p.appendix-group-title {{
      margin: 18px 0 8px;
      font-size: 14px;
      line-height: 1.6;
      font-weight: 600;
      color: #2f2f2f;
    }}
    .article p {{
      margin: 0 0 22px;
    }}
    .article p.table-caption,
    .article p.figure-caption {{
      margin-top: 8px;
    }}
    .article ul,
    .article ol {{
      margin: 0 0 16px 1.22em;
      padding: 0;
    }}
    .article ol {{
      list-style: none;
      margin-left: 0;
      padding-left: 0;
    }}
    .article li + li {{
      margin-top: 6px;
    }}
    .article hr {{
      border: 0;
      border-top: 1px solid var(--line);
      margin: 36px 0;
    }}
    .article strong {{
      font-weight: 700;
    }}
    .article a {{
      color: inherit;
      text-decoration-color: rgba(26, 137, 23, 0.35);
      text-underline-offset: 2px;
    }}
    .article code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: .84em;
      background: #f2f2f2;
      padding: .12em .35em;
      border-radius: 6px;
    }}
    .article img {{
      display: block;
      max-width: 100%;
      height: auto;
      cursor: zoom-in;
      image-rendering: auto;
      backface-visibility: hidden;
    }}
    .article img.common-shot {{
      width: min(100%, 1744px);
      margin: 20px 0 24px;
      border-radius: 12px;
    }}
    .article td img.detail-shot {{
      display: block;
      width: 100%;
      max-width: 100%;
      height: clamp(220px, 24vw, 320px);
      margin: 12px 0 0;
      border-radius: 10px;
      border: 1px solid #ececec;
      box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
      background: #fff;
      object-fit: contain;
      object-position: center top;
    }}
    @media (max-width: 900px) {{
      .article td img.detail-shot {{
        height: clamp(180px, 44vw, 260px);
      }}
    }}
    .article blockquote {{
      margin: 20px 0;
      padding: 0 0 0 18px;
      background: transparent;
      border-left: 2px solid #d6d3d1;
      border-radius: 0;
    }}
    .article blockquote p:last-child {{
      margin-bottom: 0;
    }}
    .article blockquote p,
    .article blockquote li {{
      font-size: 15px;
      line-height: 1.8;
    }}
    .callout {{
      margin: 24px 0 28px;
      padding: 16px 18px;
      background: var(--accent-soft);
      border: 1px solid #ece9e2;
      border-left: 2px solid #d6d3d1;
      border-radius: 10px;
    }}
    .callout p:last-child,
    .callout ul:last-child,
    .callout ol:last-child {{
      margin-bottom: 0;
    }}
    .callout p,
    .callout li,
    .callout p em,
    .callout li em {{
      font-size: 15px;
      line-height: 1.75;
      font-style: normal;
    }}
    .summary-title {{
      margin: 0 0 10px;
      font: 700 16px/1.6 var(--sans);
      color: #191919;
      letter-spacing: -0.01em;
    }}
    .table-caption {{
      margin: 8px 0 0;
      text-align: center;
      color: #8a8f98;
      font: 400 10px/1.6 var(--sans);
    }}
    .table-wrap {{
      width: 100%;
      overflow-x: auto;
      margin: 18px 0 6px;
      background: transparent;
      border: 1px solid var(--line);
      border-radius: 0;
      content-visibility: auto;
      contain-intrinsic-size: 900px;
    }}
    .article table {{
      width: 100%;
      min-width: 620px;
      border-collapse: collapse;
      font-size: 13px;
      background: #fff;
    }}
    .article th,
    .article td {{
      padding: 14px 14px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      line-height: 1.7;
      word-break: break-word;
      white-space: normal;
      font-size: 14px;
    }}
    .article th {{
      background: #fafaf9;
      font: 700 14px/1.6 var(--sans);
      color: #191919;
    }}
    .plain-list-table thead td,
    .plain-list-table td {{
      background: transparent;
      font-weight: 400;
      font-family: var(--serif);
      border-bottom: 1px solid #d9d9d9;
    }}
    .plain-list-table strong {{
      font-weight: 400;
    }}
    .equal-two-col-table {{
      table-layout: fixed;
    }}
    .equal-two-col-table th,
    .equal-two-col-table td {{
      width: 50%;
    }}
    .equal-two-col-table tbody:first-child tr:first-child td,
    .equal-two-col-table tbody:first-child tr:first-child th {{
      font-weight: 400;
      color: #191919;
      background: #fff;
    }}
    .equal-two-col-table tr.emphasis-row td,
    .equal-two-col-table tr.emphasis-row th {{
      background: #f6f6f3;
    }}
    .category-stack-table {{
      table-layout: fixed;
    }}
    .category-stack-table th:first-child,
    .category-stack-table td:first-child {{
      width: 24%;
    }}
    .dimension-compare-table {{
      table-layout: fixed;
    }}
    .dimension-compare-table th:first-child,
    .dimension-compare-table td:first-child {{
      width: 18%;
    }}
    .trend-table thead th:first-child,
    .trend-table thead th:first-child strong {{
      font-size: 15px;
      line-height: 1.55;
    }}
    .trend-table tbody tr:nth-child(1) strong,
    .trend-table tbody tr:nth-child(3) strong {{
      font-weight: 400;
    }}
    .trend-table td:first-child {{
      white-space: normal;
    }}
    .trend-table tbody tr:nth-child(1) td:first-child,
    .trend-table tbody tr:nth-child(3) td:first-child {{
      font: 400 15px/1.55 var(--sans);
      color: #191919;
    }}
    .trend-table tbody tr:nth-child(1) td:nth-child(2) {{
      font: 400 15px/1.55 var(--sans);
      color: #191919;
    }}
    .trend-table tbody tr:nth-child(2) td:nth-child(1),
    .trend-table tbody tr:nth-child(2) td:nth-child(2),
    .trend-table tbody tr:nth-child(3) td:first-child,
    .trend-table tbody tr:nth-child(3) td:nth-child(2) {{
      width: 50%;
      vertical-align: top;
      white-space: normal;
    }}
    .trend-table td[colspan] {{
      width: 100%;
    }}
    .trend-table tbody tr:nth-child(2) td:first-child:only-child {{
      display: block;
      width: 100%;
    }}
    .trend-table tbody tr:nth-child(4) td[colspan] {{
      padding-right: 18px;
    }}
    .analysis-framework-table td.vertical-label {{
      background: #fafafa;
      color: #191919;
      font: 700 14px/1.45 var(--sans);
      writing-mode: vertical-rl;
      text-orientation: upright;
      letter-spacing: 0.12em;
      text-align: center;
      vertical-align: middle;
      min-width: 92px;
      width: 92px;
      padding: 18px 10px;
    }}
    .analysis-framework-table {{
      table-layout: fixed;
    }}
    .analysis-framework-table col.analysis-col-journey {{
      width: 56px;
    }}
    .analysis-framework-table col.analysis-col-equal {{
      width: calc((100% - 56px) / 5);
    }}
    .analysis-framework-table th {{
      text-align: center;
      vertical-align: middle;
    }}
    .analysis-framework-table th:first-child {{
      writing-mode: vertical-rl;
      text-orientation: upright;
      letter-spacing: 0.08em;
      width: 56px;
      min-width: 56px;
      padding: 14px 6px;
    }}
    .relationship-stage-table {{
      table-layout: fixed;
    }}
    .relationship-stage-table th:first-child,
    .relationship-stage-table td:first-child {{
      width: 18%;
      white-space: nowrap;
    }}
    .article h5 strong,
    .article h6 strong {{
      font-size: 20px;
      font-weight: 700;
    }}
    .article h5,
    .article h6,
    .article h5 strong,
    .article h6 strong {{
      font-size: 20px;
      line-height: 1.5;
    }}
    .article tr:last-child td {{
      border-bottom: 0;
    }}
    .toc {{
      position: fixed;
      top: 50vh;
      left: max(28px, calc(50vw - 740px + 28px));
      transform: translateY(-50%);
      width: 260px;
      max-height: calc(100vh - 96px);
      display: flex;
      flex-direction: column;
      justify-content: center;
      gap: 18px;
      padding: 8px 0;
      background: transparent;
      border: 0;
      border-radius: 0;
      box-shadow: none;
      overflow-y: auto;
      z-index: 10;
    }}
    .toc-links {{
      display: flex;
      flex-direction: column;
      gap: 8px;
    }}
    .image-lightbox {{
      position: fixed;
      inset: 0;
      z-index: 60;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 28px;
      background: rgba(17, 17, 17, 0.82);
      opacity: 0;
      pointer-events: none;
      transition: opacity .2s ease;
    }}
    .image-lightbox.is-open {{
      opacity: 1;
      pointer-events: auto;
    }}
    .image-lightbox-toolbar {{
      position: absolute;
      top: 20px;
      right: 74px;
      display: inline-flex;
      align-items: center;
      gap: 10px;
      padding: 8px 10px;
      border-radius: 999px;
      background: rgba(255,255,255,.92);
      box-shadow: 0 6px 20px rgba(0,0,0,.18);
    }}
    .image-lightbox-toolbar button {{
      border: 0;
      background: transparent;
      color: #191919;
      font: 600 18px/1 var(--sans);
      cursor: pointer;
      width: 28px;
      height: 28px;
      border-radius: 999px;
    }}
    .image-lightbox-toolbar button:hover {{
      background: rgba(0,0,0,.06);
    }}
    .image-lightbox-zoom-label {{
      min-width: 48px;
      text-align: center;
      color: #444;
      font: 500 13px/1 var(--sans);
    }}
    .image-lightbox img {{
      max-width: min(92vw, 1400px);
      max-height: 88vh;
      width: auto;
      height: auto;
      display: block;
      border-radius: 10px;
      box-shadow: 0 20px 60px rgba(0,0,0,.28);
      background: #fff;
      transform-origin: center center;
      transition: transform .14s ease;
    }}
    .image-lightbox-close {{
      position: absolute;
      top: 20px;
      right: 20px;
      border: 0;
      border-radius: 999px;
      width: 42px;
      height: 42px;
      background: rgba(255,255,255,.92);
      color: #191919;
      font: 500 24px/1 var(--sans);
      cursor: pointer;
      box-shadow: 0 6px 20px rgba(0,0,0,.18);
    }}
    body.lightbox-open {{
      overflow: hidden;
    }}
    .toc-title {{
      margin: 0;
      color: #8a8f98;
      font: 700 12px/1.4 var(--sans);
      letter-spacing: .08em;
      text-transform: uppercase;
    }}
    .toc-link {{
      display: block;
      width: 100%;
      box-sizing: border-box;
      padding: 6px 0 6px 14px;
      border-left: 1px solid transparent;
      color: #9aa0a9;
      text-decoration: none;
      font: 500 12px/1.45 var(--sans);
      overflow-wrap: anywhere;
      transition: color .18s ease, border-color .18s ease;
    }}
    .toc-link:hover {{
      color: #4b5563;
      border-left-color: #c7cbd1;
    }}
    .toc-link.is-active {{
      color: #191919;
      border-left-color: #191919;
      font-weight: 600;
      background: linear-gradient(90deg, rgba(23, 23, 23, 0.04) 0%, rgba(23, 23, 23, 0) 100%);
    }}
    .toc-link.level-3 {{
      padding-left: 24px;
    }}
    .toc-link.level-4 {{
      padding-left: 38px;
      white-space: normal;
      overflow: visible;
      text-overflow: clip;
    }}
    .toc-link.toc-link-nested {{
      padding-left: 50px;
    }}
    .footer-note {{
      max-width: 860px;
      margin: 36px 0 0;
      text-align: center;
      color: #8a8a8a;
      font: 400 12px/1.5 var(--sans);
    }}
    @media (max-width: 1100px) {{
      .layout {{
        grid-template-columns: 220px minmax(0, 1fr);
        column-gap: 24px;
        padding-inline: 18px;
      }}
      .hero,
      .article,
      .footer-note {{
        max-width: 760px;
      }}
      .hero h1 {{
        font-size: 52px;
      }}
      .article p,
      .article li {{
        font-size: 16px;
      }}
    }}
    @media (max-width: 768px) {{
      .layout {{
        display: block;
        padding: 20px 14px 56px;
      }}
      .toc {{
        position: static;
        left: auto;
        transform: none;
        width: auto;
        display: block;
        max-height: none;
        margin: 0 0 24px;
      }}
      .toc-links {{
        display: block;
      }}
      .hero h1 {{
        font-size: 38px;
        letter-spacing: -0.04em;
      }}
      .article h2 {{
        font-size: 28px;
      }}
      .article h3 {{
        font-size: 24px;
      }}
      .article h4 {{
        font-size: 20px;
      }}
      .article h5,
      .article h6 {{
        font-size: 20px;
      }}
      .article p,
      .article li {{
        font-size: 16px;
        line-height: 1.78;
      }}
    }}
  </style>
</head>
<body>
  <div class="image-lightbox" aria-hidden="true">
    <div class="image-lightbox-toolbar">
      <button class="image-lightbox-zoom-out" type="button" aria-label="缩小图片">−</button>
      <div class="image-lightbox-zoom-label">100%</div>
      <button class="image-lightbox-zoom-in" type="button" aria-label="放大图片">+</button>
      <button class="image-lightbox-zoom-reset" type="button" aria-label="重置缩放">↺</button>
    </div>
    <button class="image-lightbox-close" type="button" aria-label="关闭图片预览">×</button>
    <img src="" alt="" />
  </div>
  <div class="layout">
    <aside class="toc" id="doc-toc">
      <div class="toc-title">目录</div>
      <nav class="toc-links">
{toc_html}
      </nav>
    </aside>
    <main class="main">
      <header class="hero">
        <h1>Agent 竞品调研</h1>
      </header>
      <article class="article">
{article_html}
      </article>
      <div class="footer-note">From XIYUFAN 2026-05-18</div>
    </main>
  </div>
  <script>
    const body = document.body;
    const articleImages = document.querySelectorAll('.article img');
    const lightbox = document.querySelector('.image-lightbox');
    const lightboxImage = lightbox.querySelector('img');
    const lightboxClose = lightbox.querySelector('.image-lightbox-close');
    const zoomInButton = lightbox.querySelector('.image-lightbox-zoom-in');
    const zoomOutButton = lightbox.querySelector('.image-lightbox-zoom-out');
    const zoomResetButton = lightbox.querySelector('.image-lightbox-zoom-reset');
    const zoomLabel = lightbox.querySelector('.image-lightbox-zoom-label');
    const tocLinks = Array.from(document.querySelectorAll('#doc-toc .toc-link'));
    const observedHeadings = tocLinks
      .map((link) => {{
        const href = link.getAttribute('href') || '';
        if (!href.startsWith('#')) return null;
        const targetId = decodeURIComponent(href.slice(1));
        const target = document.getElementById(targetId);
        if (!target) return null;
        return {{ link, target }};
      }})
      .filter(Boolean);
    let lightboxScale = 1;

    function updateLightboxZoom() {{
      lightboxImage.style.transform = `scale(${{lightboxScale}})`;
      zoomLabel.textContent = `${{Math.round(lightboxScale * 100)}}%`;
    }}

    function setLightboxZoom(nextScale) {{
      lightboxScale = Math.min(4, Math.max(0.5, nextScale));
      updateLightboxZoom();
    }}
    function openLightbox(image) {{
      lightboxImage.src = image.getAttribute('data-fullsrc') || image.getAttribute('src') || '';
      lightboxImage.alt = image.getAttribute('alt') || '';
      lightboxScale = 1;
      updateLightboxZoom();
      lightbox.classList.add('is-open');
      lightbox.setAttribute('aria-hidden', 'false');
      body.classList.add('lightbox-open');
    }}

    function closeLightbox() {{
      lightbox.classList.remove('is-open');
      lightbox.setAttribute('aria-hidden', 'true');
      lightboxImage.src = '';
      lightboxImage.alt = '';
      lightboxScale = 1;
      updateLightboxZoom();
      body.classList.remove('lightbox-open');
    }}

    articleImages.forEach((image) => {{
      image.addEventListener('click', () => openLightbox(image));
    }});

    function alignDetailShotRows() {{
      document.querySelectorAll('.article table tr').forEach((row) => {{
        const images = Array.from(row.querySelectorAll('td img.detail-shot'));
        if (images.length < 2) return;
        images.forEach((image) => {{
          image.style.marginTop = '12px';
        }});
        const offsets = images.map((image) => image.getBoundingClientRect().top);
        const maxOffset = Math.max(...offsets);
        images.forEach((image, index) => {{
          const delta = maxOffset - offsets[index];
          if (delta > 1) {{
            image.style.marginTop = `${{12 + delta}}px`;
          }}
        }});
      }});
    }}

    function setActiveTocLink(activeLink) {{
      tocLinks.forEach((link) => link.classList.remove('is-active'));
      if (activeLink) {{
        activeLink.classList.add('is-active');
      }}
    }}

    function updateActiveTocLink() {{
      if (!observedHeadings.length) return;
      const scrollAnchor = window.innerHeight * 0.22;
      let current = observedHeadings[0];

      observedHeadings.forEach((item) => {{
        const top = item.target.getBoundingClientRect().top;
        if (top - scrollAnchor <= 0) {{
          current = item;
        }}
      }});

      setActiveTocLink(current.link);
    }}

    tocLinks.forEach((link) => {{
      link.addEventListener('click', () => {{
        setActiveTocLink(link);
      }});
    }});

    lightboxClose.addEventListener('click', closeLightbox);
    zoomInButton.addEventListener('click', () => setLightboxZoom(lightboxScale + 0.25));
    zoomOutButton.addEventListener('click', () => setLightboxZoom(lightboxScale - 0.25));
    zoomResetButton.addEventListener('click', () => setLightboxZoom(1));
    lightboxImage.addEventListener('dblclick', () => setLightboxZoom(1));
    lightbox.addEventListener('wheel', (event) => {{
      if (!lightbox.classList.contains('is-open')) return;
      event.preventDefault();
      const delta = event.deltaY < 0 ? 0.2 : -0.2;
      setLightboxZoom(lightboxScale + delta);
    }}, {{ passive: false }});
    lightbox.addEventListener('click', (event) => {{
      if (event.target === lightbox) closeLightbox();
    }});
    window.addEventListener('keydown', (event) => {{
      if (event.key === 'Escape' && lightbox.classList.contains('is-open')) closeLightbox();
    }});
    window.addEventListener('load', () => {{
      alignDetailShotRows();
      updateActiveTocLink();
    }});
    window.addEventListener('resize', () => {{
      alignDetailShotRows();
      updateActiveTocLink();
    }});
    window.addEventListener('scroll', updateActiveTocLink, {{ passive: true }});
  </script>
</body>
</html>
"""


def main() -> None:
    source = SRC.read_text(encoding="utf-8")
    source = strip_outer_wrapper(source)
    source = preprocess_markdown(source)

    headings = collect_headings(source)
    article_html = render_html(source)
    article_html = optimize_article_images(article_html)
    article_html = inject_heading_ids(article_html, headings)
    article_html = wrap_tables(article_html)
    article_html = postprocess_article_html(article_html)

    toc_html = build_toc(headings)
    page_html = build_page(article_html, toc_html)
    OUT.write_text(page_html, encoding="utf-8")
    build_deploy_bundle()
    print(OUT)


if __name__ == "__main__":
    main()
