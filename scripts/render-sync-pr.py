"""Render review metadata for a committed client distribution sync."""

import argparse
import json
import os
from pathlib import Path
import subprocess


def git(directory, *args):
    return subprocess.check_output(
        ["git", "-C", str(directory), *args], text=True, encoding="utf-8"
    ).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--distribution", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    client = os.environ["SYNC_CLIENT"]
    if client not in ("codex", "claude"):
        parser.error("SYNC_CLIENT must be codex or claude")
    source = Path(os.environ["GITHUB_WORKSPACE"])
    sha = os.environ["GITHUB_SHA"]
    subject = git(source, "show", "-s", "--format=%s", sha)
    names = git(args.distribution, "diff", "--name-only", "-z", "HEAD^", "HEAD")
    plugins = sorted({p.split("/")[1] for p in names.split("\0") if p.startswith("plugins/")})
    rows = []
    for plugin in plugins:
        manifest = args.distribution / "plugins" / plugin / f".{client}-plugin" / "plugin.json"
        version = json.loads(manifest.read_text(encoding="utf-8"))["version"] if manifest.exists() else "removed"
        rows.append(f"- `{plugin}`: `{version}`")
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    repository = os.environ["GITHUB_REPOSITORY"]
    values = dict(
        client=client,
        source_subject=subject.replace("[", "\\[").replace("]", "\\]"),
        source_sha=sha,
        source_url=f"{server}/{repository}/commit/{sha}",
        run_url=f"{server}/{repository}/actions/runs/{os.environ['GITHUB_RUN_ID']}",
        plugins="\n".join(rows) or "- 仅发行元数据变化，没有插件文件变更。",
        diff_stat=git(args.distribution, "diff", "--stat", "HEAD^", "HEAD"),
        client_validation=(
            "Codex 插件市场注册、列表及全部生成插件的安装。"
            if client == "codex" else
            "Claude 插件市场与插件校验、注册及全部生成插件的安装。"
        ),
    )
    template = (Path(__file__).parent / "templates" / "sync-pr.md.template").read_text(encoding="utf-8")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    title = f"chore({client}): 同步 {subject}"
    if len(title) > 120:
        title = title[:119] + "…"
    (args.output_dir / "title.txt").write_text(title + "\n", encoding="utf-8")
    (args.output_dir / "body.md").write_text(template.format(**values), encoding="utf-8")


if __name__ == "__main__":
    main()
