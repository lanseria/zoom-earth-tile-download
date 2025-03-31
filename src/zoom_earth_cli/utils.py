
import logging
import os
import json
from pathlib import Path
import platform
from PIL import Image, ImageDraw, ImageFont
from typing import Dict, List, Optional, Any
import numpy as np
from typing import Dict, Set, Tuple
from collections import defaultdict

from zoom_earth_cli.const import BLACKLIST_PATH

def get_system_font():
    """获取系统默认字体"""
    system = platform.system()
    try:
        if system == "Windows":
            return "arial.ttf"
        elif system == "Darwin":
            return "/System/Library/Fonts/Supplemental/Arial.ttf"
        else:
            return "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    except:
        return ImageFont.load_default()

def draw_tile_info(draw, position, text, tile_size):
    """在指定位置绘制坐标信息"""
    # 动态计算字体大小（基于瓦片尺寸）
    font_size = max(10, tile_size // 10)
    
    try:
        font = ImageFont.truetype(get_system_font(), font_size)
    except IOError:
        font = ImageFont.load_default()
    
    # 计算文字包围盒
    text_bbox = draw.textbbox((0,0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    
    # 自动调整位置（带背景框）
    padding = 2
    x, y = position
    rect_position = (
        x + padding,
        y + padding,
        x + text_width + padding*2,
        y + text_height + padding*2
    )
    
    # 绘制背景框
    draw.rectangle(rect_position, fill=(0,0,0,128))  # 半透明黑色背景
    
    # 绘制文字（白色文字）
    draw.text(
        (x + padding, y + padding),
        text,
        fill="white",
        font=font
    )

def load_blacklist() -> Dict[str, Dict[int, Set[Tuple[int, int]]]]:
    """加载黑名单配置，返回格式: {satellite: {zoom: set((x,y))}}"""
    if not os.path.exists(BLACKLIST_PATH):
        return defaultdict(lambda: defaultdict(set))
    
    try:
        with open(BLACKLIST_PATH, 'r') as f:
            raw = json.load(f)
        
        # 使用双重默认字典结构
        blacklist = defaultdict(lambda: defaultdict(set))
        
        for sat, zoom_data in raw.items():
            for zoom_str, coords in zoom_data.items():
                zoom = int(zoom_str)
                # 将列表转换为元组集合
                blacklist[sat][zoom] = {tuple(coord) for coord in coords}
        
        return blacklist
    
    except Exception as e:
        logging.error(f"加载黑名单失败：{e}")
        # 保持结构一致性，返回双重默认字典
        return defaultdict(lambda: defaultdict(set))

def save_blacklist(blacklist: Dict[str, Dict[int, Set[Tuple[int, int]]]]):
    """保存支持zoom层级的黑名单配置"""
    # 转换为可序列化的字典结构
    serializable = defaultdict(dict)
    
    for sat, zoom_data in blacklist.items():
        for zoom, coords in zoom_data.items():
            # 将元组集合转换为列表的列表，zoom转换为字符串作为key
            serializable[sat][str(zoom)] = [list(c) for c in coords]
    
    try:
        with open(BLACKLIST_PATH, 'w') as f:
            json.dump(serializable, f, indent=2)
    except Exception as e:
        logging.error(f"保存黑名单失败：{e}")

def get_tile_path(satellite: str, timestamp: str, x: int, y: int, zoom: int) -> str:
    """生成图片存储路径（示例）"""
    return f"tiles/{satellite}/{zoom}/{timestamp}/{x}_{y}.png"

def generate_black_tile(satellite: str, timestamp: str, x: int, y: int, zoom: int = 4):
    """生成全黑图片并保存"""
    path = get_tile_path(satellite, zoom, timestamp, x, y)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        img = Image.new('RGB', (256, 256), (0, 0, 0))
        img.save(path)
        logging.debug(f"生成全黑图片：{path}")
    except Exception as e:
        logging.error(f"生成全黑图片失败：{path}, 错误：{e}")

def validate_coordinates(filename: str) -> tuple:
    """解析文件名中的坐标"""
    try:
        x_part, y_part = Path(filename).stem.split("_")
        return int(x_part[1:]), int(y_part[1:])
    except Exception as e:
        logging.warning(f"坐标解析失败: {filename} - {str(e)}")
        return None, None

def concat_tiles(
    tile_dir: Path, 
    output_path: Path, 
    tile_size: int = 256,
    rotate_deg: int = 0,  # 新增旋转参数
    reverse_y: bool = False,
    show_coords: bool = False,
    swap_xy: bool = True  # 新增坐标轴交换参数
):
    """拼接卫星图片（支持旋转）"""
    # 如果输出文件已存在则跳过拼接
    if output_path.exists():
        logging.info(f"拼接图已存在，跳过: {output_path}")
        return
    # 验证旋转角度有效性
    valid_deg = {0, 90, 180, 270}
    if rotate_deg not in valid_deg:
        raise ValueError(f"无效旋转角度，可选值：{valid_deg}")

    # 生成瓦片坐标映射（基于预定义范围）
    # 收集瓦片并解析坐标
    coord_map = {}
    for tile_file in tile_dir.glob("x*_y*.jpg"):
        x, y = validate_coordinates(tile_file.name)
        if x is not None and y is not None:
            # 根据参数交换坐标轴
            if swap_xy:
                x, y = y, x  # 交换XY坐标
            coord_map[(x, y)] = str(tile_file)
    
    if not coord_map:
        logging.warning(f"跳过空目录: {tile_dir}")
        return

    # 计算坐标范围
    x_coords = {x for x, _ in coord_map}
    y_coords = {y for _, y in coord_map}
    
    # 根据旋转角度调整坐标轴
    if rotate_deg in (90, 270):
        # 交换XY轴尺寸
        canvas_width = (max(y_coords) - min(y_coords) + 1) * tile_size
        canvas_height = (max(x_coords) - min(x_coords) + 1) * tile_size
    else:
        canvas_width = (max(x_coords) - min(x_coords) + 1) * tile_size
        canvas_height = (max(y_coords) - min(y_coords) + 1) * tile_size

    canvas = Image.new('RGB', (canvas_width, canvas_height))

    # 拼接处理（带旋转）
    for (orig_x, orig_y), path in coord_map.items():
        try:
            img = Image.open(path)
            
            # 应用旋转（保持比例）
            if rotate_deg != 0:
                img = img.rotate(
                    -rotate_deg,  # PIL使用逆时针角度
                    expand=True,
                    fillcolor=(40, 40, 40)  # 填充透明区域
                )
            # 统一尺寸（旋转可能改变比例）
            img = img.resize((tile_size, tile_size))
            
            # 计算新坐标（考虑旋转后的坐标系）
            if rotate_deg == 90:
                new_x = (orig_y - min(y_coords))
                new_y = (max(x_coords) - orig_x)
            elif rotate_deg == 180:
                new_x = (max(x_coords) - orig_x)
                new_y = (max(y_coords) - orig_y)
            elif rotate_deg == 270:
                new_x = (max(y_coords) - orig_y)
                new_y = orig_x - min(x_coords)
            else:
                new_x = orig_x - min(x_coords)
                new_y = orig_y - min(y_coords)

            # 调整Y轴方向
            if reverse_y:
                new_y = (max(y_coords) - min(y_coords)) - new_y

            # 计算最终位置
            pos = (
                new_x * tile_size,
                new_y * tile_size
            )
            
            # 粘贴到画布
            canvas.paste(img, pos)
            # 添加坐标标注（使用原始坐标）
            if show_coords:
                draw = ImageDraw.Draw(canvas)
                text = f"x:{orig_x}\ny:{orig_y}"
                draw_tile_info(draw, pos, text, tile_size)
        except Exception as e:
            logging.error(f"处理失败 [{Path(path).name}]: {str(e)}")

    # 保存结果
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, quality=95)
    logging.info(f"生成拼接图: {output_path}")

def add_feather_alpha(img, feather_width=100, black_threshold=10, debug=True):
    """为图像添加透明度通道和羽化效果"""
    # 转换为RGBA模式
    img = img.convert("RGBA")
    data = np.array(img)
    height, width = img.height, img.width  # 注意这里的顺序是(height, width)
    
    # 创建基础Alpha通道（非黑色区域不透明）
    r, g, b, a = data.T  # 这里转置后维度变为 (channels, height, width)
    black_mask = (r <= black_threshold) & (g <= black_threshold) & (b <= black_threshold)
    alpha = np.where(black_mask, 0, 255).astype(np.uint8).T  # 需要再次转置回(height, width)
    
    # 生成水平羽化渐变（修正维度顺序）
    feather = np.ones((height, width), dtype=np.float32)  # 使用(height, width)顺序
    
    # 左侧渐变（0 → 1）
    feather[:, :feather_width] = np.linspace(0, 1, feather_width)
    # 右侧渐变（1 → 0）
    feather[:, -feather_width:] = np.linspace(1, 0, feather_width)
    
    # 应用羽化到Alpha通道（现在两个数组维度一致）
    alpha = (alpha.astype(np.float32) * feather).clip(0, 255).astype(np.uint8)
    
    data[..., 3] = alpha
    # 调试输出
    if debug:
        # 保存各阶段结果
        debug_dir = "debug_output"
        os.makedirs(debug_dir, exist_ok=True)
        # 保存羽化蒙版
        Image.fromarray((feather*255).astype(np.uint8)).save(f"{debug_dir}/feather_mask.png")
        # 保存最终效果
        preview = Image.alpha_composite(img.convert("RGBA"), Image.fromarray(data))
        preview.save(f"{debug_dir}/final_preview.png")
    return Image.fromarray(data)

def smart_feather_alpha(img, left_margin, right_margin, feather_width=150, debug=False, debug_dir=""):
    # 将图像转换为RGBA模式，确保包含Alpha通道
    img_rgba = img.convert("RGBA")
    width, height = img_rgba.size
    
    # 初始化Alpha通道为全透明
    alpha = np.zeros((height, width), dtype=np.uint8)
    
    left = left_margin
    right = right_margin
    W = right - left  # 保留区域宽度
    
    if W > 0:
        if W >= 2 * feather_width:
            # 保留区域足够宽，应用标准羽化
            left_end = left + feather_width
            right_start = right - feather_width
        else:
            # 保留区域较窄，调整羽化宽度为一半
            left_end = left + W // 2
            right_start = right - W // 2
        
        # 确保羽化边界有效
        left_end = min(left_end, right)
        right_start = max(right_start, left)
        
        x = np.arange(width)
        
        # 处理左侧羽化区域
        mask_left = (x >= left) & (x < left_end)
        if left_end > left:
            alpha_left = ((x[mask_left] - left) / (left_end - left) * 255).astype(np.uint8)
            alpha[:, mask_left] = alpha_left
        
        # 处理中间不透明区域
        mask_mid = (x >= left_end) & (x < right_start)
        alpha[:, mask_mid] = 255
        
        # 处理右侧羽化区域
        mask_right = (x >= right_start) & (x < right)
        if right_start < right:
            alpha_right = ((right - x[mask_right]) / (right - right_start) * 255).astype(np.uint8)
            alpha[:, mask_right] = alpha_right
    
    # 应用Alpha通道到图像
    img_rgba.putalpha(Image.fromarray(alpha, mode='L'))
    
    if debug:
        os.makedirs(debug_dir, exist_ok=True)
        debug_filename = f"feathered_{W}_{os.path.basename(img.filename)}"
        debug_path = os.path.join(debug_dir, debug_filename)
        img_rgba.save(debug_path)
        print(f"Debug image saved to: {debug_path}")
    
    return img_rgba

def filter_timestamps_by_hours(latest_times: Dict[str, List[int]], hours: int) -> Dict[str, List[int]]:
    """Filters timestamps to keep only those within the last N hours."""
    if hours <= 0:
        # Return a copy to avoid modifying the original dict downstream
        return {sat: list(ts_list) for sat, ts_list in latest_times.items()}

    max_ts = 0
    try:
        # Find the overall latest timestamp across all non-empty lists
        all_ts = [ts for ts_list in latest_times.values() for ts in ts_list]
        if not all_ts:
             return {sat: [] for sat in latest_times} # No timestamps anywhere
        max_ts = max(all_ts)
    except ValueError:
        # Handle case where latest_times might be empty or contain only empty lists
         return {sat: [] for sat in latest_times}


    cutoff_ts = max_ts - hours * 3600  # Calculate cutoff time

    filtered_data = {}
    for satellite, timestamps in latest_times.items():
        # Keep timestamps greater than or equal to the cutoff
        filtered_data[satellite] = sorted([ts for ts in timestamps if ts >= cutoff_ts])

    return filtered_data


def process_latest_times(latest_times: Dict[str, List[int]], hours: int = 2) -> List[Dict[str, Any]]:
    """
    Processes latest time data, groups by timestamp, and fills in the latest value for each satellite.

    Args:
        latest_times: Dictionary of satellite names to lists of timestamps {satellite: [timestamps]}.
        hours: Only keep data within the last N hours (0 means no limit). Default is 2.

    Returns:
        A list of dictionaries, sorted by timestamp. Each dictionary contains:
        {
            'timestamp': The master timestamp for this entry,
            'goes-east': Latest timestamp for goes-east <= master timestamp,
            'goes-west': Latest timestamp for goes-west <= master timestamp,
            ... (for all satellites)
        }
        Only includes master timestamps from the point where *all* satellites have reported at least once.
    """
    if not latest_times:
        return []

    # 1. Filter timestamps by the specified hour window
    filtered_data = filter_timestamps_by_hours(latest_times, hours)

    # If filtering removed all data points across all satellites, return empty
    if not any(filtered_data.values()):
        print("Warning: Filtering removed all timestamps.")
        return []

    # 2. Get the list of all satellites we need to track (from the original input keys)
    satellites = list(latest_times.keys())
    if not satellites:
        return [] # No satellites specified

    # 3. Collect all unique timestamps from the *filtered* data and sort them
    all_timestamps_set: Set[int] = set()
    for sat in satellites:
        # Use .get to handle cases where a satellite might have no data after filtering
        all_timestamps_set.update(filtered_data.get(sat, []))

    if not all_timestamps_set:
        # If, after filtering, there are no timestamps left at all
        print("Warning: No timestamps remain after filtering.")
        return []

    sorted_timestamps = sorted(list(all_timestamps_set))

    # 4. Find the first "master" timestamp where *all* satellites have at least one data point <= that timestamp
    start_ts: Optional[int] = None
    start_index: int = -1
    for i, ts in enumerate(sorted_timestamps):
        all_sats_have_data = True
        for sat in satellites:
            # Check if there exists any timestamp for this satellite <= current ts
            has_data_at_or_before_ts = any(t <= ts for t in filtered_data.get(sat, []))
            if not has_data_at_or_before_ts:
                all_sats_have_data = False
                break  # No need to check other satellites for this ts

        if all_sats_have_data:
            start_ts = ts
            start_index = i
            break # Found the first valid starting timestamp

    # If no timestamp exists where all satellites have data (e.g., one satellite never reported)
    if start_ts is None:
        print(f"Warning: Could not find a timestamp where all satellites ({', '.join(satellites)}) have data.")
        return []

    # 5. Initialize the 'last known timestamp' for each satellite based on the found start_ts
    current_latest_ts: Dict[str, int] = {}
    for sat in satellites:
        # Find the maximum timestamp for this satellite that is <= start_ts
        # We know at least one exists because of the check in step 4
        relevant_times = [t for t in filtered_data.get(sat, []) if t <= start_ts]
        # This list is guaranteed non-empty by the logic in step 4
        current_latest_ts[sat] = max(relevant_times)


    # 6. Iterate through sorted timestamps *starting from the valid start index*
    result: List[Dict[str, Any]] = []
    for i in range(start_index, len(sorted_timestamps)):
        master_ts = sorted_timestamps[i]
        entry: Dict[str, Any] = {'timestamp': master_ts}

        # Update the 'last known timestamp' for any satellite that has a new data point *at* master_ts
        for sat in satellites:
             # Check if this satellite specifically reported at master_ts
             # Using a set could be faster for large lists, but requires pre-conversion
             if master_ts in filtered_data.get(sat, []):
                 current_latest_ts[sat] = master_ts
             # Otherwise, current_latest_ts[sat] remains unchanged (carry-forward)

        # Populate the result entry with the current latest timestamp for each satellite
        for sat in satellites:
            entry[sat] = current_latest_ts[sat]

        result.append(entry)

    return result
