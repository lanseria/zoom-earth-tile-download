import os
import json
import logging
import requests
import time
from pprint import pprint
from datetime import datetime, timezone
from typing import Tuple, Optional, List
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

def get_latest_times(hours: int = 1):
    """获取各卫星最新时间戳（支持时间范围过滤）
    
    Args:
        hours: 仅保留最近N小时内的数据（0表示不限制），默认1小时
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
        
        # 处理时间数据
        current_time = time.time()
        result = {}
        
        for satellite, timestamps in data.items():
            # 时间范围过滤
            if hours > 0:
                valid_times = [ts for ts in timestamps 
                              if (current_time - ts) <= hours * 3600]
                if not valid_times:
                    logger.warning(f"卫星 {satellite} 无有效数据（最新数据 {round((current_time - max(timestamps))/3600,1)} 小时前）")
                    continue
                latest = valid_times
            else:
                latest = timestamps
            
            result[satellite] = latest
        
        logger.info(f"成功处理 {len(result)}/{len(data)} 个卫星（{hours}小时过滤）")
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

def batch_download(
        concurrency: int = 5,
        satellites: Optional[List[str]] = None,
        hours: int = 1
    ):
    """批量下载主逻辑（包含黑名单过滤）
    
    Args:
        concurrency: 并发线程数，默认5
        satellites: 要处理的卫星列表，默认全部（包含 goes-east, goes-west, himawari, msg-iodc, msg-zero, mtg-zero）
        hours: 仅处理最新N小时内的数据，0表示不限制，默认1小时
    """
    # 设置卫星默认值
    if satellites is None:
        satellites = ["goes-east", "goes-west", "himawari", "msg-iodc", "msg-zero", "mtg-zero"]
    
    latest_times = get_latest_times(hours=hours)
    if not latest_times:
        logging.error("获取卫星时间数据失败")
        return

    # pprint(latest_times)
    # 卫星过滤
    filtered_times = {k: v for k, v in latest_times.items() if k in satellites}
    # pprint(filtered_times)
    # return

    blacklist = load_blacklist()
    x_range = X_RANGE
    y_range = Y_RANGE

    for satellite, timestamps in filtered_times.items():
        logging.info(f"开始处理卫星: {satellite}，共有 {len(timestamps)} 个时间点")
        
        # 初始化卫星级统计
        sat_total = 0
        sat_success = 0
        sat_skipped = 0
        sat_failed = 0
        sat_new_black = 0
        
        # 遍历每个时间戳
        for timestamp in timestamps:
            logging.info(f"处理时间点: {datetime.fromtimestamp(timestamp):%Y-%m-%d %H:%M}")
            
            # 生成所有区域并分割
            all_coords = [(x, y) for x in x_range for y in y_range]
            total_all = len(all_coords)
            skip_coords = {(x, y) for x, y in all_coords if (x, y) in blacklist.get(satellite, set())}
            download_coords = [c for c in all_coords if c not in skip_coords]
            
            # 处理已跳过的区域
            for x, y in skip_coords:
                generate_black_tile(satellite, timestamp, x, y)
            
            # 提交下载任务
            total_download = len(download_coords)
            if total_download == 0:
                logging.info(f"时间点 {timestamp} 无需要下载的区域")
                continue
                
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                download_func = partial(download_tile, satellite, timestamp)
                results = list(executor.map(lambda c: download_func(c[0], c[1]), download_coords))
            
            # 解析当前时间点结果
            success_count = sum(succ for succ, _ in results)
            new_black_coords = [download_coords[i] for i, (_, is_blk) in enumerate(results) if is_blk]
            
            # 更新黑名单
            if new_black_coords:
                blacklist[satellite].update(new_black_coords)
                save_blacklist(blacklist)
            
            # 统计当前时间点
            current_skipped = len(skip_coords) + len(new_black_coords)
            current_failed = total_download - success_count
            
            logging.info(
                f"时间点完成 - 总数: {total_all}\n"
                f"成功: {success_count} | 跳过: {current_skipped} | 失败: {current_failed}\n"
                f"新增黑名单: {len(new_black_coords)}"
            )
            
            # 累加卫星级统计
            sat_total += total_all
            sat_success += success_count
            sat_skipped += current_skipped
            sat_failed += current_failed
            sat_new_black += len(new_black_coords)
        
        # 输出卫星汇总日志
        logging.info(
            f"卫星 {satellite} 汇总 - 总处理时间点: {len(timestamps)}\n"
            f"总计成功: {sat_success} | 总计跳过: {sat_skipped} | 总计失败: {sat_failed}\n"
            f"总新增黑名单: {sat_new_black}"
        )

