# 抖音下载器使用说明

## 🚀 快速开始

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 配置 Cookie（首次使用需要）
```bash
# 自动获取（推荐）
python cookie_extractor.py

# 或手动获取
python get_cookies_manual.py
```

`get_cookies_manual.py` 只检查常见 Cookie 字段，缺少 `msToken` 不等于 Cookie 无效；是否可用应以目标接口的实际响应为准。这个助手默认写入 `config_simple.yml`，而 `DouYinCommand.py` 读取的是 `config.yml`。

### 3. 开始下载

#### V1.0 稳定版（推荐用于单个视频）
```bash
# 编辑 config.yml 配置文件
# 然后运行
python DouYinCommand.py
```

动图／实况作品也可以按单个作品下载：把网页版链接（包括 `modal_id`）填入 `config.yml` 的 `link`，再运行上面的命令。每张实况图会保存一张静图（如 `*_image_1.webp`）和一段动态视频（`*_image_1_live.mp4`）；普通图集仍只保存静图。配置文件名是 `config.yml`。

#### V2.0 增强版（推荐用于用户主页）
```bash
# 下载用户主页
python downloader.py -u "https://www.douyin.com/user/xxxxx"

# 下载用户主页中打开的单个实况作品
python downloader.py -u "https://www.douyin.com/user/xxxxx?modal_id=作品ID"

# 自动获取 Cookie 并下载
python downloader.py --auto-cookie -u "https://www.douyin.com/user/xxxxx"
```

## 📋 版本对比

| 功能 | V1.0 (DouYinCommand.py) | V2.0 (downloader.py) |
|------|------------------------|---------------------|
| 单个视频下载 | ✅ 完全正常 | ⚠️ API 问题 |
| 用户主页下载 | ✅ 正常 | ✅ 完全正常 |
| Cookie 管理 | 手动配置 | 自动获取 |
| 使用复杂度 | 简单 | 中等 |
| 稳定性 | 高 | 中等 |

## 🎯 推荐使用场景

- **下载单个视频**：使用 V1.0
- **下载用户主页**：使用 V2.0
- **批量下载**：使用 V2.0
- **学习研究**：两个版本都可以

## 📞 获取帮助

- 查看详细文档：`README.md`
- 报告问题：[GitHub Issues](https://github.com/jiji262/douyin-downloader/issues)
