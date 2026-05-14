# Agent 竞品调研页面

这个仓库用于生成并发布竞品调研网页。

## 本地生成

运行下面这条命令会同时完成三件事：

1. 根据 `Final版本_统一排版版.md` 重新生成 HTML
2. 生成页面预览图缓存
3. 自动产出 GitHub Pages 可发布目录 `docs/`

```bash
python3 build_blog_html.py
```

生成结果：

- 页面源文件：`Final版本_统一排版版_blog.html`
- GitHub Pages 发布目录：`docs/`

## GitHub Pages 发布

推荐直接使用仓库里的 `docs/` 目录作为 Pages 发布源。

### 1. 在 GitHub 新建仓库

仓库名可以自定义，例如：

`agent-competitor-report`

### 2. 把本地仓库推到 GitHub

把下面的 `<你的仓库地址>` 替换成你在 GitHub 上新建仓库后的地址：

```bash
git init
git add .
git commit -m "Initial site publish"
git branch -M main
git remote add origin <你的仓库地址>
git push -u origin main
```

### 3. 打开 GitHub Pages

进入 GitHub 仓库页面：

1. 打开 `Settings`
2. 打开 `Pages`
3. 在 `Build and deployment` 里选择 `Deploy from a branch`
4. Branch 选择 `main`
5. Folder 选择 `/docs`
6. 点击 `Save`

几分钟后，GitHub 会给你一个公开链接：

`https://<你的 GitHub 用户名>.github.io/<仓库名>/`

## 后续更新

每次你修改正文后，只需要重新执行：

```bash
python3 build_blog_html.py
```

然后提交并推送：

```bash
git add .
git commit -m "Update report"
git push
```

GitHub Pages 会自动重新发布 `docs/` 里的新内容。
