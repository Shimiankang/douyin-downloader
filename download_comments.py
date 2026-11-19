#!/usr/bin/env python
"""Download one Douyin work's comments and attached media."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from apiproxy.douyin.comments import (
    CommentClient, CommentError, export_comments, resolve_aweme_id,
)


def load_cookie(config_path: Path) -> str:
    with config_path.open("r", encoding="utf-8") as file:
        try:
            config = yaml.safe_load(file) or {}
        except yaml.YAMLError as exc:
            raise ValueError("配置文件 YAML 格式错误") from exc
    if not isinstance(config, dict):
        raise ValueError("配置文件必须是 YAML 对象")
    cookies = config.get("cookies") or config.get("cookie")
    if isinstance(cookies, dict):
        return "; ".join(f"{key}={value}" for key, value in cookies.items())
    if isinstance(cookies, str) and cookies.lower() != "auto":
        return cookies.strip()
    raise ValueError("请在 config.yml 的 cookies 中配置浏览器 Cookie")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="抓取单个抖音作品的评论、回复及媒体")
    parser.add_argument("url", help="作品链接（含 modal_id）或作品 ID")
    parser.add_argument(
        "--config", type=Path, default=Path(__file__).with_name("config.yml"),
        help="含 cookies 的配置文件，默认使用项目根目录 config.yml",
    )
    parser.add_argument(
        "--output", type=Path, default=Path(__file__).with_name("Downloaded") / "comments",
        help="导出根目录；实际结果会放在其中的作品 ID 子目录",
    )
    parser.add_argument("--limit", type=int, default=100, help="一级评论上限，0 表示全部")
    parser.add_argument("--reply-limit", type=int, default=100,
                        help="每条一级评论的回复上限，0 表示全部")
    parser.add_argument("--no-replies", action="store_true", help="不抓取评论回复")
    parser.add_argument("--no-media", action="store_true", help="只保存 JSON，不下载媒体")
    parser.add_argument("--interval", type=float, default=0.5, help="接口请求最小间隔（秒）")
    args = parser.parse_args(argv)
    if args.limit < 0 or args.reply_limit < 0 or args.interval < 0:
        parser.error("上限和请求间隔不能为负数")

    try:
        cookie = load_cookie(args.config)
        client = CommentClient(cookie, interval=args.interval)
        aweme_id = resolve_aweme_id(args.url, client.session)
        output_dir = args.output / aweme_id
        export, downloaded, failures = export_comments(
            client,
            aweme_id,
            output_dir,
            source=args.url,
            limit=args.limit,
            reply_limit=args.reply_limit,
            include_replies=not args.no_replies,
            download_media=not args.no_media,
        )
    except (OSError, ValueError, CommentError) as exc:
        parser.exit(1, f"抓取失败：{exc}\n")

    print(
        f"作品 {aweme_id}：一级评论 {export['top_level_count']} 条，"
        f"回复 {export['reply_count']} 条，媒体 {downloaded} 个，"
        f"媒体失败 {failures} 个"
    )
    print(f"结果：{output_dir / 'comments.json'}")
    print(f"原始数据：{output_dir / 'comments_raw.json'}")
    for warning in client.warnings:
        print(f"提示：{warning}")
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
