
import logging
from pathlib import Path
import platform
from PIL import Image, ImageDraw, ImageFont
from typing import Dict
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from zoom_earth_cli.api_client import get_latest_times, download_tile

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

def batch_download(concurrency: int = 5):
    """批量下载主逻辑"""
    latest_times: Dict = get_latest_times()
    
    if not latest_times:
        logging.error("获取卫星时间数据失败")
        return

    # 定义下载范围
    x_range = range(4, 12)
    y_range = range(0, 16)

    for satellite, timestamp in latest_times.items():
        logging.info(f"开始处理卫星: {satellite}")
        
        # 生成所有坐标组合
        x_range = range(4, 12)
        y_range = range(0, 16)
        args = [(x, y) for x in x_range for y in y_range]
        total = len(args)
        
        # 创建线程池
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            # 包装下载函数固定卫星和时间参数
            download_func = partial(
                download_tile,
                satellite,
                timestamp
            )
            
            # 提交并发任务
            results = executor.map(
                lambda params: download_func(params[0], params[1]),
                args
            )
            
            # 统计结果
            success = sum(results)
            skipped = total - success

        logging.info(
            f"完成 {satellite} - "
            f"成功: {success}/{total} "
            f"({success/total:.1%}) 失败: {skipped}"
        )


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
    # 验证旋转角度有效性
    valid_deg = {0, 90, 180, 270}
    if rotate_deg not in valid_deg:
        raise ValueError(f"无效旋转角度，可选值：{valid_deg}")

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
    canvas.save(output_path, quality=95)
    logging.info(f"生成拼接图: {output_path}")
