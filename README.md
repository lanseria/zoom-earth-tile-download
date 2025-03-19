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

如果将一张图，用 python 将其围绕中心点旋转任意角度，可以得到一个新的图像。
但反过来，如何我已经有一旋转的图，与原图，如何获得旋转角度？使用python能不能解决这个问题？