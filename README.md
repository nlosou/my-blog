# my-blog

一个类似 [nullprogram.com](https://nullprogram.com/) 的极简个人技术博客。

- 极简白色背景、纯文本阅读体验
- Markdown 编写文章，YAML front matter
- 纯 Python 静态生成，零前端框架、零 JavaScript
- 支持标签、归档、文章目录（TOC）、代码高亮
- 同时输出 Atom 与 RSS 2.0
- 输出纯静态文件，适合 GitHub Pages

## 目录结构

```
content/
  posts/       # 文章（Markdown + YAML front matter）
  pages/       # 固定页面（如 about）
templates/     # HTML 模板
static/        # style.css、favicon.svg
scripts/
  build.py     # 生成器入口
  highlight.py # Pygments 高亮 + ARM 汇编 lexer
output/        # 构建产物（已 gitignore）
config.yaml    # 站点配置
requirements.txt
.github/workflows/pages.yml
```

## 快速开始

依赖 Python 3.10+，以及 `Markdown`、`Pygments`、`PyYAML`：

```bash
pip install -r requirements.txt
python3 scripts/build.py
```

本地预览：

```bash
python3 -m http.server 8000 --directory output
# 打开 http://localhost:8000/
```

每次修改文章或配置后重新运行 `python3 scripts/build.py` 即可。

## 写文章

在 `content/posts/` 下新建 Markdown 文件，文件名默认就是 URL 中的 slug。

```markdown
---
title: "STM32 智能手表项目"
date: 2026-09-25
tags: [embedded, stm32]
summary: "一句话摘要"
---

正文使用标准 Markdown。
```

### front matter 字段

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `title` | 是 | 文章标题 |
| `date` | 是 | 发布日期，格式 `YYYY-MM-DD` |
| `tags` | 否 | 标签，列表或逗号分隔字符串 |
| `summary` | 否 | 摘要，用于列表页与 Feed |
| `slug` | 否 | 自定义 URL，默认取文件名；URL 为 `/posts/{slug}/` |
| `draft` | 否 | `true` 时不发布 |
| `toc` | 否 | `false` 时关闭本文目录 |

### 文章目录（TOC）

默认开启：文章会从 `h2`–`h4` 标题自动生成目录，并显示在正文顶部。
可在 `config.yaml` 中通过 `site.toc` 与 `site.toc_depth` 调整。

- 全局关闭：`site.toc: false`
- 单篇关闭：在 front matter 中写 `toc: false`
- 中文标题同样会生成可点击的锚点

### 代码高亮

代码块用三反引号加语言名，Pygments 高亮，配色接近 GitHub 浅色主题：

````markdown
```c
int main(void) { return 0; }
```

```bash
./scripts/build.py
```

```arm
ldr r0, =_estack
mov sp, r0
bl main
```
````

针对嵌入式场景内置了轻量 ARM 汇编 lexer（`arm` / `armasm` / `aarch64` / `thumb`）。
C、Shell（`bash` / `sh`）、Makefile、Rust、Python 等由 Pygments 原生支持。

### 固定页面

放在 `content/pages/`，例如 `about.md` 会生成 `/about/`。页面默认不显示目录。

## Feed

构建会生成：

- `output/atom.xml`（Atom，推荐，优先使用）
- `output/rss.xml`（RSS 2.0）
- `output/sitemap.xml`

页面 `<head>` 中已声明两个 Feed，Atom 在前。

## 部署到 GitHub Pages

1. **修改 `config.yaml`**
   - 用户站点：`base_url: "https://USERNAME.github.io/"`
   - 项目站点：`base_url: "https://USERNAME.github.io/REPO/"`
2. **推送到 GitHub**
   ```bash
   git init
   git add .
   git commit -m "init blog"
   git remote add origin git@github.com:USERNAME/my-blog.git
   git push -u origin main
   ```
3. **开启 Pages**
   在仓库 **Settings → Pages → Build and deployment** 中，把 **Source** 选为 **GitHub Actions**。
4. 推送后，`.github/workflows/pages.yml` 会自动运行构建并发布 `output/`。

> 如果默认分支不是 `main`，请同步修改 `.github/workflows/pages.yml` 顶部的
> `branches: [main]`。

### 自定义域名 + HTTPS

1. 在 `config.yaml` 中设置 `site.cname: "example.com"`，构建会生成 `CNAME` 文件。
2. 在 Pages 设置中填写该域名。
3. 到域名服务商添加 DNS 记录（GitHub Pages 设置页会给出具体记录）。
4. HTTPS 由 GitHub 自动签发，无需额外配置。
