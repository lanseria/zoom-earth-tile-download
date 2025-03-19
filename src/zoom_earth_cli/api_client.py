import os
import logging
import requests
from datetime import datetime, timezone


# 初始化模块级 logger
logger = logging.getLogger(__name__)

headers = {
    'accept': '*/*',
    'accept-language': 'zh-CN,zh;q=0.9',
    'cache-control': 'no-cache',
    'dnt': '1',
    'origin': 'https://zoom.earth',
    'pragma': 'no-cache',
    'priority': 'u=1, i',
    'referer': 'https://zoom.earth/',
    'sec-ch-ua': '"Chromium";v="134", "Not:A-Brand";v="24", "Google Chrome";v="134"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"macOS"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-site',
    'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36'
}

def get_latest_times():
    """获取各卫星最新时间戳"""
    url = "https://tiles.zoom.earth/times/geocolor.json"
    try:
        logger.debug(f"开始获取卫星时间数据: {url}")
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        result = {sat: max(times) for sat, times in data.items()}
        logger.info(f"成功获取 {len(data)} 个卫星的时间数据")
        return result
    except requests.exceptions.RequestException as e:
        logger.error(
            f"获取卫星时间失败 - URL: {url} | 状态码: {getattr(e.response, 'status_code', 'N/A')}",
            exc_info=True
        )
    except Exception as e:
        logger.error(
            f"处理卫星时间数据异常: {str(e)}",
            exc_info=True
        )
    return {}

def download_tile(satellite: str, timestamp: int, x: int, y: int) -> bool:
    """下载单个贴图"""
    try:
        dt = datetime.fromtimestamp(timestamp, timezone.utc)
        date_str = dt.strftime("%Y-%m-%d")
        time_str = dt.strftime("%H%M")
        
        # 构建 URL
        url = f"https://tiles.zoom.earth/geocolor/{satellite}/{date_str}/{time_str}/4/{x}/{y}.jpg"
        logger.debug(f"开始下载贴图: {url}")

        # 创建目录
        save_dir = os.path.join("downloads", satellite, date_str, time_str)
        os.makedirs(save_dir, exist_ok=True)
        filename = os.path.join(save_dir, f"x{x}_y{y}.jpg")
        
        # 下载文件
        response = requests.get(url, headers=headers, stream=True, timeout=15)
        response.raise_for_status()

        with open(filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        logger.info(f"下载完成: {filename} ({os.path.getsize(filename)/1024:.1f}KB)")
        return True
    except requests.exceptions.RequestException as e:
        logger.warning(
            f"下载失败 - URL: {url} | 状态码: {getattr(e.response, 'status_code', 'N/A')}"
        )
    except IOError as e:
        logger.error(
            f"文件写入失败: {filename} | 错误: {str(e)}",
            exc_info=True
        )
    except Exception as e:
        logger.error(
            f"未知下载错误: {str(e)}",
            exc_info=True
        )
    return False