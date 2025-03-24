# Zoom Earth Cli

A simple CLI demo using Typer and Rich.

## python venv

```bash
# 创建虚拟环境（venv 是 Python 内置工具）
python3.12 -m venv myenv
# macOS/Linux
source myenv/bin/activate

# Windows (PowerShell)
.\myenv\Scripts\Activate.ps1

deactivate
```

## Installation

```bash
# 升级 pip
python -m pip install --upgrade pip

# 设置默认镜像源
pip config set global.index-url https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple

# 如果需要设置额外的镜像源
pip config set global.extra-index-url "https://pypi.mirrors.ustc.edu.cn/simple/ https://pypi.doubanio.com/simple/"

pip install .
```

For development:
```bash
pip install -e ".[test]"
```

## Usage

Add two numbers:
```bash
zec process-api
zec process-api -s himawari -h 24
zec process-concat
zec process-concat -s himawari -h 24
zec process-video -i mosaics/himawari
```
## Running Tests

```bash
pytest
```

For build:

```bash
pip install -e ".[build]"
python scripts/build.py
# for linux
sudo apt-get install binutils
```

## Requirements

- <Python 3.13
- typer
- rich

## AI Prompt

### 1

我有这么几张图
- mosaics/goes-east/2025-03-21/0200.png
- mosaics/goes-west/2025-03-21/0200.png
- mosaics/himawari/2025-03-21/0130.png
- mosaics/msg-iodc/2025-03-21/0145.png
- mosaics/msg-zero/2025-03-21/0145.png
- mosaics/mtg-zero/2025-03-21/0150.png
他们都是 4096 * 2048 的图片，
将他们叠放在一起，并都使用 "明亮" 的效果，生成一张新的 4096 * 2048 图片

### 2

给这个方法添加一个 过滤器，用来判断某个卫星对应的xy区域是不用下载的，当然一次是空的，每次下载图片时，通过判断文件大小，小于0.2KB的将当作全黑图片，记录在 一个 配置文件里，下次再次下载前，先读取这个文件，当遇到需要下载全黑图片时，就不下载直接自己生成256*256的全黑图片用来替换，避免过度下载，注意，生成这个配置文件仅当配置文件不存在时，去记录生成

### 3 

给这个方法添加一个两个参数

- 选择哪个卫星，默认全部 有 goes-east, goes-west, himawari, msg-iodc, msg-zero, mtg-zero
- 选择哪个最新几小时内，默认最新的 1 小时,