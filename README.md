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

```bash
#
zec process-api -h 24 -z 4
zec process-concat -h 24
zec process-blend -h 24
zec process-video -i lighter_blend/4/ -h 24
```


```bash
#
zec process-api -h 12 -z 4 --country usa
zec process-concat -h 12 -i downloads/usa/ -o mosaics/usa/
zec process-blend -h 12 -i mosaics/usa/ -o lighter_blend/global/
zec process-video -i lighter_blend/4/ -h 12
```

```bash
#
zec process-api -h 12 -z 4 --country china
zec process-concat -h 12 -i downloads/china/ -o mosaics/china/
zec blend -h 12 -c china -z 4
zec process-blend -h 12 -i mosaics/china/ -o lighter_blend/china/
zec process-video -i lighter_blend/4/ -h 12
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

### 4

处理这个数据 latest_times
数据结构是这样的
{'goes-east': [1743139200,
               1743139800,
               1743140400,
               1743141000,
               1743141600,
               1743142200],
 'goes-west': [1743139200,
               1743139800,
               1743140400,
               1743141000,
               1743141600,
               1743142200,
               1743142800],
 'himawari': [1743139200,
              1743139800,
              1743140400,
              1743141000,
              1743141600,
              1743142200,
              1743142800],
 'msg-iodc': [1743139800, 1743140700, 1743141600, 1743142500, 1743143400],
 'msg-zero': [1743139800,
              1743140700,
              1743141600,
              1743142500,
              1743143400,
              1743144300],
 'mtg-zero': [1743139200,
              1743139800,
              1743140400,
              1743141000,
              1743141600,
              1743142200,
              1743142800,
              1743143400,
              1743144000,
              1743144600]}

根据这个时间戳来分
比如 1743139200 这个时间戳，有 goes-west, goes-east, mtg-zero, msg-iodc, himawari,
需要考虑全部可能的时间戳
最后给我
[
  {
    timestamp: 1743139200,
    goes-west: 1743139200,
    goes-east: 1743139200,
    mtg-zero: 1743139200,
    msg-iodc: 1743139200,
    himawari: 1743139200,
  }
]
可能有的时间戳没有卫星是没有的，那就用它上一个可用的时间戳的时间点