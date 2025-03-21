import os
import logging
import requests
from datetime import datetime, timezone
from typing import Tuple
from functools import partial
from concurrent.futures import ThreadPoolExecutor

from zoom_earth_cli.utils import generate_black_tile, load_blacklist, save_blacklist
from zoom_earth_cli.const import X_RANGE, Y_RANGE

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

def download_tile(satellite: str, timestamp: int, x: int, y: int) -> Tuple[bool, bool]:
    """下载单个贴图，返回（是否成功，是否黑图）"""
    try:
        dt = datetime.fromtimestamp(timestamp, timezone.utc)
        date_str = dt.strftime("%Y-%m-%d")
        time_str = dt.strftime("%H%M")
        
        # 构建 URL 和文件路径
        url = f"https://tiles.zoom.earth/geocolor/{satellite}/{date_str}/{time_str}/4/{x}/{y}.jpg"
        save_dir = os.path.join("downloads", satellite, date_str, time_str)
        os.makedirs(save_dir, exist_ok=True)
        filename = os.path.join(save_dir, f"x{x}_y{y}.jpg")
        logger.debug(f"开始下载贴图: {url}")

        # 下载到临时文件（避免部分写入）
        temp_file = filename + ".tmp"
        response = requests.get(url, headers=headers, stream=True, timeout=15)
        response.raise_for_status()

        # 写入临时文件
        with open(temp_file, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        # 检查文件大小是否过小（<0.2KB）
        file_size = os.path.getsize(temp_file)
        if file_size < 0.2 * 1024:  # 0.2KB = 204.8 bytes
            logger.warning(f"检测到黑图: {filename} ({file_size/1024:.1f}KB)")
            generate_black_tile(filename, timestamp, x, y)  # 生成黑图替换
            os.remove(temp_file)  # 删除无效文件
            return (True, True)   # 成功生成黑图，需要记录到黑名单
        else:
            os.rename(temp_file, filename)  # 重命名为正式文件
            logger.info(f"下载成功: {filename} ({file_size/1024:.1f}KB)")
            return (True, False)  # 成功且无需记录

    except requests.exceptions.RequestException as e:
        status_code = getattr(e.response, "status_code", "N/A")
        logger.warning(f"下载失败 - URL: {url} | 状态码: {status_code}")
        return (False, False)
    except Exception as e:
        logger.error(f"未知错误: {str(e)}", exc_info=True)
        return (False, False)

def batch_download(concurrency: int = 5):
    """批量下载主逻辑（包含黑名单过滤）"""
    latest_times = get_latest_times()
    if not latest_times:
        logging.error("获取卫星时间数据失败")
        return

    blacklist = load_blacklist()
    x_range = X_RANGE
    y_range = Y_RANGE

    for satellite, timestamp in latest_times.items():
        logging.info(f"开始处理卫星: {satellite}")
        
        # 生成所有区域并分割
        all_coords = [(x, y) for x in x_range for y in y_range]
        total_all = len(all_coords)
        skip_coords = {(x, y) for x, y in all_coords if (x, y) in blacklist[satellite]}
        download_coords = [c for c in all_coords if c not in skip_coords]
        
        # 处理已跳过的区域
        for x, y in skip_coords:
            generate_black_tile(satellite, timestamp, x, y)
        
        # 提交下载任务
        total_download = len(download_coords)
        if total_download == 0:
            logging.info(f"卫星 {satellite} 无需要下载的区域，跳过。")
            continue
            
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            download_func = partial(download_tile, satellite, timestamp)
            results = list(executor.map(lambda c: download_func(c[0], c[1]), download_coords))
        
        # 解析结果
        success_count = sum(succ for succ, _ in results)
        new_black_coords = [download_coords[i] for i, (_, is_blk) in enumerate(results) if is_blk]
        
        # 更新黑名单
        if new_black_coords:
            blacklist[satellite].update(new_black_coords)
            save_blacklist(blacklist)
        
        # 统计信息
        effective_success = success_count - len(new_black_coords)
        skipped_count = len(skip_coords) + len(new_black_coords)
        failed_count = total_download - success_count
        
        logging.info(
            f"完成 {satellite} - 总数: {total_all}\n"
            f"成功: {effective_success} | 跳过: {skipped_count} | 失败: {failed_count}\n"
            f"新增黑名单: {len(new_black_coords)}"
        )
