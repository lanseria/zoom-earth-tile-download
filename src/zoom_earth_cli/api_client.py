import os
import json
import logging
import requests
import time
from pprint import pprint
from datetime import datetime, timezone
from typing import Tuple, Optional, List
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from zoom_earth_cli.const import get_ranges_for_zoom
from zoom_earth_cli.utils import generate_black_tile, load_blacklist, save_blacklist, process_latest_times, filter_timestamps_by_hours


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


# --- Satellite Mapping (Optional Improvement) ---
SATELLITE_Y_RANGES = {
    "goes-east": range(0, 3),   # Includes 0, 1, 2
    "goes-west": range(3, 7),   # Includes 3, 4, 5, 6
    "mtg-zero":  range(7, 10),  # Includes 7, 8, 9
    "msg-iodc":  range(10, 12), # Includes 10, 11
    "himawari":  range(12, 16), # Includes 12, 13, 14, 15
}

def get_satellite_for_y(y: int) -> str | None:
    """Determines satellite based on Y coordinate using the mapping."""
    for sat, y_range in SATELLITE_Y_RANGES.items():
        if y in y_range:
            return sat
    return None

def fetch_latest_times():
    """获取各卫星最新时间戳
    """
    url = "https://tiles.zoom.earth/times/geocolor.json"
    try:
        logger.debug(f"开始获取卫星时间数据: {url}")
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # 生成带时间戳的文件名
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"./debug_output/satellite_times_{timestamp}.json"
        
        # 创建目录（如果不存在）
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        # 保存原始数据（不经过滤）
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.debug(f"原始时间数据已保存至 {filename}")
        except IOError as e:
            logger.error(f"保存时间数据文件失败: {str(e)}", exc_info=True)
        
        return data

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

def get_latest_times(hours: int = 2):
    """获取各卫星最新时间戳
    Args:
        hours: 仅保留最近N小时内的数据默认2小时
    """
    url = "https://tiles.zoom.earth/times/geocolor.json"
    try:
        data = fetch_latest_times()
        # 调用utils中的时间过滤函数
        filtered_data = filter_timestamps_by_hours(data, hours)
        
        logger.info(f"成功处理 {len(filtered_data)}/{len(data)} 个卫星（{hours}小时过滤）")
        return filtered_data

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

def download_tile(satellite: str, timestamp: int, x: int, y: int, zoom: int = 4) -> Tuple[bool, bool]:
    """下载单个贴图，返回（是否成功，是否黑图）
    
    Args:
        satellite: 卫星名称
        timestamp: 时间戳
        x: x坐标
        y: y坐标 
        zoom: zoom级别，默认为4
    """
    try:
        dt = datetime.fromtimestamp(timestamp, timezone.utc)
        date_str = dt.strftime("%Y-%m-%d")
        time_str = dt.strftime("%H%M")
        
        # 构建 URL 和文件路径
        url = f"https://tiles.zoom.earth/geocolor/{satellite}/{date_str}/{time_str}/{zoom}/{x}/{y}.jpg"
        save_dir = os.path.join("downloads", satellite, f"{zoom}", date_str, time_str)
        os.makedirs(save_dir, exist_ok=True)
        filename = os.path.join(save_dir, f"x{x}_y{y}.jpg")
        
        # 检查文件是否已存在
        if os.path.exists(filename):
            logger.info(f"文件已存在，跳过下载: {filename}")
            return (True, False)
            
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
        # if file_size < 0.2 * 1024:  # 0.2KB = 204.8 bytes
        #     logger.warning(f"检测到黑图: {filename} ({file_size/1024:.1f}KB)")
        #     generate_black_tile(filename, timestamp, x, y, zoom)  # 生成黑图替换
        #     os.remove(temp_file)  # 删除无效文件
        #     return (True, True)   # 成功生成黑图，需要记录到黑名单
        # else:
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

def batch_download(
        concurrency: int = 5,
        satellites: Optional[List[str]] = None,
        hours: int = 2,
        zoom: int = 4
    ):
    """批量下载主逻辑（包含黑名单过滤）优化版
    
    Args:
        concurrency: 并发线程数，默认5
        satellites: 要处理的卫星列表，默认全部
        hours: 仅处理最新N小时内的数据，0表示不限制
        zoom: zoom级别，默认为4
    """

    if satellites is None:
        satellites = ["goes-east", "goes-west", "himawari", "msg-iodc", "msg-zero", "mtg-zero"]

    latest_times = get_latest_times(hours=hours)
    if not latest_times:
        logging.error("获取卫星时间数据失败")
        return
    
    filtered_times = {k: v for k, v in latest_times.items() if k in satellites}
    blacklist = load_blacklist() 

    # 阶段1: 预处理
    tasks = []
    pre_stats = defaultdict(lambda: defaultdict(dict))

    for satellite in filtered_times:
        pre_stats[satellite] = {}
        x_range, y_range = get_ranges_for_zoom(zoom, satellite)
        for timestamp in filtered_times[satellite]:
            all_coords = [(x, y) for x in x_range for y in y_range]
            # 获取当前卫星当前zoom的黑名单坐标
            zoom_bl = blacklist.get(satellite, {}).get(zoom, set())
            skip_coords = {(x, y) for x, y in all_coords if (x, y) in zoom_bl}
            
            # 生成黑瓷砖
            for x, y in skip_coords:
                generate_black_tile(satellite, timestamp, x, y, zoom)
            
            # 记录预处理数据
            pre_stats[satellite][timestamp] = {
                'total': len(all_coords),
                'skipped': len(skip_coords),
                'downloadable': len(all_coords) - len(skip_coords)
            }
            
            # 生成下载任务
            tasks.extend([(satellite, timestamp, x, y) 
                        for x, y in all_coords if (x, y) not in skip_coords])

    # 阶段2: 批量并行下载
    def _download_wrapper(args):
        satellite, timestamp, x, y = args
        success, is_black = download_tile(satellite, timestamp, x, y, zoom)
        return (satellite, timestamp, success, is_black, x, y)

    results = []
    if tasks:
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(_download_wrapper, task) for task in tasks]
            for future in as_completed(futures):
                results.append(future.result())
    else:
        logging.info("没有需要下载的任务")
        return

    # 阶段3: 处理结果
    result_stats = defaultdict(lambda: defaultdict(lambda: {
        'success': 0, 'failed': 0, 'new_black': 0
    }))
    new_black = defaultdict(lambda: defaultdict(set))  # 新结构: {sat: {zoom: set}}

    for satellite, timestamp, success, is_black, x, y in results:
        result_stats[satellite][timestamp]['success' if success else 'failed'] += 1
        if is_black:
            new_black[satellite][zoom].add((x, y))  # 关联当前zoom
            result_stats[satellite][timestamp]['new_black'] += 1

    # 更新黑名单（支持zoom层级）
    for sat in new_black:
        for z in new_black[sat]:
            # 合并当前zoom的黑名单
            blacklist.setdefault(sat, {}).setdefault(z, set()).update(new_black[sat][z])
    save_blacklist(blacklist)  # 使用新的保存方法

    # 阶段4: 失败任务重试
    failed_tasks = []
    for satellite, timestamp, success, is_black, x, y in results:
        if not success:
            failed_tasks.append((satellite, timestamp, x, y))
    
    # 重试失败的任务
    if failed_tasks:
        logging.info(f"\n开始重试 {len(failed_tasks)} 个失败任务...")
        retry_results = []
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(_download_wrapper, task) for task in failed_tasks]
            for future in as_completed(futures):
                retry_results.append(future.result())
        
        # 更新重试结果
        for satellite, timestamp, success, is_black, x, y in retry_results:
            if success:
                result_stats[satellite][timestamp]['success'] += 1
                result_stats[satellite][timestamp]['failed'] -= 1
                if is_black:
                    new_black[satellite].add((x, y))
                    result_stats[satellite][timestamp]['new_black'] += 1

    # 阶段5: 生成统计报告
    for satellite in filtered_times:
        sat_total = sat_success = sat_skipped = sat_failed = sat_new_black = 0
        
        for timestamp in filtered_times[satellite]:
            # 获取预处理数据
            pre = pre_stats[satellite][timestamp]
            # 获取结果数据
            res = result_stats[satellite][timestamp]
            
            # 累加卫星统计
            sat_total += pre['total']
            sat_success += res.get('success',0)
            sat_skipped += pre['skipped']
            sat_failed += res.get('failed',0)
            sat_new_black += res.get('new_black',0)

        # 生成卫星汇总日志
        logging.info(f"\n卫星 {satellite} 汇总:")
        logging.info(f"处理时间点: {len(filtered_times[satellite])}")
        logging.info(f"总处理区域: {sat_total}")
        logging.info(f"成功率: {sat_success/(sat_total - sat_skipped)*100:.1f}% [成功{sat_success}/尝试{sat_total - sat_skipped}]")
        logging.info(f"新增黑名单数: {sat_new_black}")
        if sat_failed > 0:
            logging.info(f"失败任务数: {sat_failed} (已重试)")

def all_download(
    concurrency: int = 20,
    hours: int = 2,
    zoom: int = 4
):
    """根据规则批量下载卫星图片"""
    logger.info(f"Starting download process: concurrency={concurrency}, hours={hours}, zoom={zoom}")

    # 获取时间数据
    try:
        latest_times = get_latest_times(hours=hours)
        if not latest_times:
            logger.error("获取卫星时间数据失败 (get_latest_times returned empty)")
            return
    except Exception as e:
        logger.error(f"获取卫星时间数据时出错: {e}", exc_info=True)
        return
    pprint(latest_times)

def download_tile_by_rule(satellite: str, timestamp: int, x: int, y: int, zoom: int) -> bool:
    """根据规则下载单个贴图，返回是否成功
    
    Args:
        satellite: 卫星名称 (e.g., 'goes-east')
        timestamp: 该卫星的时间戳
        x: x坐标
        y: y坐标
        zoom: zoom级别

    Returns:
        是否成功下载
    """
    try:
        dt = datetime.fromtimestamp(timestamp, timezone.utc)
        date_str = dt.strftime("%Y-%m-%d")
        time_str = dt.strftime("%H%M")

        # 构建URL和文件路径
        url = f"https://tiles.zoom.earth/geocolor/{satellite}/{date_str}/{time_str}/{zoom}/{x}/{y}.jpg"
        save_dir = os.path.join("downloads", f"{zoom}", date_str, time_str)
        os.makedirs(save_dir, exist_ok=True)
        filename = os.path.join(save_dir, f"x{x}_y{y}.jpg") # Simplified filename

        # 检查文件是否已存在
        if os.path.exists(filename):
            # logger.debug(f"文件已存在，跳过下载: {filename}")
            return True

        logger.debug(f"开始下载贴图: {url}")

        # 下载到临时文件
        temp_file = filename + ".tmp"
        response = requests.get(url, headers=headers, stream=True, timeout=15) # Increased timeout slightly
        response.raise_for_status() # Check for 4xx/5xx errors

        # 写入临时文件
        with open(temp_file, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        # TODO (Optional): Add check for blank/black image here if needed
        # e.g., check file size: if os.path.getsize(temp_file) < MIN_EXPECTED_SIZE: raise ValueError("Downloaded file too small")
        # or use Pillow: from PIL import Image; img = Image.open(temp_file); ... check properties ...

        # 重命名为正式文件
        os.rename(temp_file, filename)
        logger.debug(f"下载成功: {filename}") # Changed to debug for less verbose success logs
        return True

    except requests.exceptions.HTTPError as e:
        # Specifically log HTTP errors (404 Not Found is common)
        logger.warning(f"下载失败 (HTTP {e.response.status_code}) - URL: {url}")
        # Clean up temp file if it exists
        if 'temp_file' in locals() and os.path.exists(temp_file):
            os.remove(temp_file)
        return False
    except requests.exceptions.RequestException as e:
        # Other network errors (timeout, connection error)
        logger.warning(f"下载失败 (Network Error) - URL: {url} | Error: {e}")
        if 'temp_file' in locals() and os.path.exists(temp_file):
            os.remove(temp_file)
        return False
    except Exception as e:
        logger.error(f"下载贴图时发生未知错误 ({satellite}, {timestamp}, {x}, {y}, {zoom}): {e}", exc_info=True)
        if 'temp_file' in locals() and os.path.exists(temp_file):
            os.remove(temp_file)
        return False

def _download_wrapper_by_rule(args):
    """包装下载任务（用于线程池）"""
    satellite, timestamp, x, y, zoom = args
    success = download_tile_by_rule(satellite, timestamp, x, y, zoom)
    # Return satellite and timestamp too for potential analysis
    return (satellite, timestamp, success, x, y)