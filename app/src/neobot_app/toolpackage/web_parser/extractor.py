"""Content extraction from HTML pages.

Strategy (priority order):
1. readability-lxml — best results for article-like pages
2. trafilatura — good general-purpose extraction
3. BeautifulSoup fallback — basic <article>/<main>/<body> extraction
"""

from __future__ import annotations

import re
import time
from datetime import datetime as dt
from typing import Optional

from bs4 import BeautifulSoup

from neobot_app.toolpackage.web_parser.models import PageMetadata, ParsedPage

REMOVE_TAGS = [
    "script", "style", "nav", "footer", "header", "aside",
    "noscript", "iframe", "form", "object", "embed",
]

REMOVE_IDS_RE = re.compile(
    r"^(ad|ads|banner|sidebar|comment|footer|header|nav|menu"
    r"|share|social|related|recommend|sponsor|popup)",
    re.I,
)


class ContentExtractor:
    """Extract main content from HTML."""

    def __init__(self, fallback_to_bs4: bool = True) -> None:
        self._fallback_to_bs4 = fallback_to_bs4

    def extract(self, html: str, url: str = "") -> ParsedPage:
        """Extract content from raw HTML."""
        t0 = time.perf_counter()

        try:
            result = self._extract_readability(html, url)
            result.parse_time_ms = (time.perf_counter() - t0) * 1000
            return result
        except ImportError:
            pass
        except Exception:
            pass

        try:
            result = self._extract_trafilatura(html, url)
            result.parse_time_ms = (time.perf_counter() - t0) * 1000
            return result
        except ImportError:
            pass
        except Exception:
            pass

        if self._fallback_to_bs4:
            result = self._extract_bs4(html, url)
        else:
            result = ParsedPage(url=url, error="所有提取方法均不可用，请安装 readability-lxml 或 trafilatura")

        result.parse_time_ms = (time.perf_counter() - t0) * 1000
        return result

    def _extract_readability(self, html: str, url: str) -> ParsedPage:
        from readability import Document

        doc = Document(html)
        title = doc.title() or ""
        content_html = doc.summary() or ""

        soup = BeautifulSoup(html, "lxml")
        metadata = self._extract_metadata(soup, title)

        content_text = self._html_to_text(content_html)
        content_markdown = self._html_to_markdown(content_html)
        summary = self._generate_summary(content_text)
        images = self._extract_images(content_html)

        return ParsedPage(
            url=url,
            metadata=metadata,
            content_html=content_html,
            content_text=content_text,
            content_markdown=content_markdown,
            summary=summary,
            images=images,
        )

    def _extract_trafilatura(self, html: str, url: str) -> ParsedPage:
        import trafilatura

        result = trafilatura.extract(
            html,
            url=url,
            output_format="python",
            with_metadata=True,
            include_comments=False,
            include_tables=True,
            include_images=True,
        )

        if result is None or (isinstance(result, dict) and not result.get("text")):
            return ParsedPage(url=url, error="trafilatura 未能提取到有效内容")

        if isinstance(result, dict):
            text = result.get("text", "")
            metadata_raw = result.get("metadata", {})
        else:
            text = str(result)
            metadata_raw = {}

        metadata = PageMetadata(
            title=metadata_raw.get("title", ""),
            author=metadata_raw.get("author", ""),
            publish_date=metadata_raw.get("date"),
            description=metadata_raw.get("description", ""),
            site_name=metadata_raw.get("sitename", ""),
        )

        content_md = self._text_to_markdown(text)
        summary = self._generate_summary(text)

        return ParsedPage(
            url=url,
            metadata=metadata,
            content_text=text,
            content_markdown=content_md,
            summary=summary,
        )

    def _extract_bs4(self, html: str, url: str) -> ParsedPage:
        soup = BeautifulSoup(html, "lxml")
        metadata = self._extract_metadata(soup, "")

        content_el = (
            soup.find("article")
            or soup.find("main")
            or soup.find(role="main")
            or soup.find("div", class_=re.compile(r"content|article|post|entry", re.I))
        )
        if content_el is None:
            content_el = soup.find("body") or soup

        clean = BeautifulSoup(str(content_el), "lxml")
        for tag in REMOVE_TAGS:
            for el in clean.find_all(tag):
                el.decompose()

        content_html = str(clean)
        content_text = self._html_to_text(content_html)
        content_md = self._html_to_markdown(content_html)
        summary = self._generate_summary(content_text)
        images = self._extract_images(content_html)

        return ParsedPage(
            url=url,
            metadata=metadata,
            content_html=content_html,
            content_text=content_text,
            content_markdown=content_md,
            summary=summary,
            images=images,
        )

    def _extract_metadata(self, soup: BeautifulSoup, fallback_title: str = "") -> PageMetadata:
        def _meta(name: str) -> str:
            for attr in ("property", "name"):
                tag = soup.find("meta", attrs={attr: name})
                if tag and tag.get("content"):
                    return tag["content"].strip()
            return ""

        title = (
            _meta("og:title")
            or _meta("twitter:title")
            or (soup.title.string.strip() if soup.title else "")
            or fallback_title
        )

        author = _meta("author") or _meta("article:author") or ""
        description = _meta("description") or _meta("og:description") or ""
        site_name = _meta("og:site_name") or ""
        favicon = ""
        fav_tag = soup.find("link", rel=re.compile(r"(shortcut )?icon", re.I))
        if fav_tag and fav_tag.get("href"):
            favicon = fav_tag["href"]

        pub_date_str = (
            _meta("article:published_time")
            or _meta("date")
            or _meta("pubdate")
        )
        pub_date = None
        if pub_date_str:
            try:
                pub_date = dt.fromisoformat(pub_date_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        return PageMetadata(
            title=title,
            author=author,
            publish_date=pub_date,
            description=description,
            site_name=site_name,
            favicon_url=favicon,
        )

    @staticmethod
    def _html_to_text(html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        for tag in soup.find_all(REMOVE_TAGS):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _html_to_markdown(html: str) -> str:
        try:
            from markdownify import markdownify
            return markdownify(html, heading_style="ATX", strip=["script", "style", "nav", "footer"])
        except ImportError:
            soup = BeautifulSoup(html, "lxml")
            for a in soup.find_all("a", href=True):
                a.replace_with(f"[{a.get_text(strip=True)}]({a['href']})")
            text = soup.get_text(separator="\n\n", strip=True)
            return re.sub(r"\n{3,}", "\n\n", text)

    @staticmethod
    def _text_to_markdown(text: str) -> str:
        return text

    @staticmethod
    def _generate_summary(text: str, max_chars: int = 500) -> str:
        cleaned = text.strip()
        if len(cleaned) <= max_chars:
            return cleaned
        truncated = cleaned[:max_chars]
        last_period = max(truncated.rfind("。"), truncated.rfind(". "), truncated.rfind("！"))
        if last_period > max_chars // 2:
            return cleaned[: last_period + 1] + "..."
        return truncated.rsplit(" ", 1)[0] + "..."

    @staticmethod
    def _extract_images(html: str) -> list[str]:
        soup = BeautifulSoup(html, "lxml")
        images = []
        for img in soup.find_all("img", src=True):
            src = img["src"].strip()
            if src and not src.startswith("data:"):
                images.append(src)
        return images
