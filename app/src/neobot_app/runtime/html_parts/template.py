"""卡片 HTML 模板（自包含：内联 CSS、无 JS、无外链）。"""

from __future__ import annotations

_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{title_text}</title>
{font_meta}<style>
{variables}
{common}
{theme_css}
</style>
</head>
<body>
<main class="card" style="width: {width}px;">
{decor}
<div class="card-veil" aria-hidden="true"></div>
<header class="card-head">
<div class="card-head-main">
<h1 class="card-title">{title}</h1>
{subtitle}
</div>
{emblem}
</header>
<section class="card-body">
{body}
</section>
{footer}
</main>
</body>
</html>
"""

