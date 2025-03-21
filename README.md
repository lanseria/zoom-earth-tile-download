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
zec process-concat
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

我有这么几张图
- mosaics/goes-east/2025-03-21/0200.png
- mosaics/goes-west/2025-03-21/0200.png
- mosaics/himawari/2025-03-21/0130.png
- mosaics/msg-iodc/2025-03-21/0145.png
- mosaics/msg-zero/2025-03-21/0145.png
- mosaics/mtg-zero/2025-03-21/0150.png
他们都是 4096 * 2048 的图片，
将他们叠放在一起，并都使用 "明亮" 的效果，生成一张新的 4096 * 2048 图片