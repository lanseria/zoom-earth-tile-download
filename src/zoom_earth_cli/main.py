import typer
from rich import print
from rich.panel import Panel
import logging
from pathlib import Path
from typing import List, Optional, Dict
import traceback
from datetime import datetime, timezone
from PIL import Image, ImageChops # Need ImageChops again
import time # 导入 time 模块

from zoom_earth_cli.ffmpeg import generate_timelapse
from zoom_earth_cli.api_client import batch_download, all_download
# No longer need get_ranges_for_zoom for this function's core logic
from zoom_earth_cli.utils import concat_tiles, smart_feather_alpha
# from zoom_earth_cli.const import get_ranges_for_zoom # Removed import


app = typer.Typer(help="Zoom Earth CLI")

# 配置日志格式
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('zoom_earth.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@app.command(name="process-video")
def process_video(
    input_dir: str = typer.Option(
        ...,
        "--input", "-i",
        help="原始卫星图像目录路径",
        exists=True,
        file_okay=False,
        dir_okay=True
    ),
    duration: int = typer.Option(
        24,
        "--duration", "-d",
        min=1,
        help="视频时间跨度（小时）"
    )
):
    """生成卫星延时视频（自动命名输出文件）"""
    try:
        # 生成带时间戳的输出文件名
        output_dir = Path("output_videos")
        output_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"timelapse_{timestamp}.mp4"

        # 调用生成逻辑
        generate_timelapse(
            input_dir=input_dir,
            output_file=str(output_file),
            duration_hours=duration,
            start_time=None,    # 自动获取最新时间
            framerate=30        # 固定默认帧率
        )

        typer.echo(f"\n[成功] 视频已生成至: {output_file}", err=True)

    except Exception as e:
        typer.secho(f"生成失败: {str(e)}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@app.command(name="process-blend")
def process_blend(
    mosaics_dir: str = typer.Option(
        "mosaics",
        "--mosaics-dir", "-m",
        help="包含拼接后卫星图像的目录",
        exists=True,
        file_okay=False,
        dir_okay=True
    ),
    output_filename: str = typer.Option(
        "lighter_blend", # Default output directory
        "--output-dir", "-o",
        help="输出混合图像序列的根目录"
    ),
    hours: int = typer.Option(
        0,
        "--hours", "-h",
        min=0,
        help="仅处理最新N小时内的数据（0表示不限制），默认0小时"
    )
) -> None:
    """
    扫描mosaics，为每个唯一时间戳生成一个混合图像。
    图像按时间倒序生成，如果卫星在某个时间点无数据，则使用其之前最新的数据。
    使用 'lighter' 模式混合，并根据预设X偏移量放置。
    可通过--hours参数限制只处理最近N小时的数据。
    """
    logger.info(f"开始扫描 mosaics 目录查找所有图像信息: {mosaics_dir}")
    mosaics_base_path = Path(mosaics_dir)
    output_base_dir = Path(output_filename) # output_filename is now the output dir
    zoom_level = 4 # Hardcoded zoom level

    # --- 1. 收集所有文件信息 ---
    # Structure: Dict[satellite_id, Dict[timestamp, file_path]]
    all_files_info: Dict[str, Dict[int, Path]] = {}
    logger.info(f"正在扫描 {mosaics_base_path} 下 zoom={zoom_level} 的图像...")
    for file_path in mosaics_base_path.glob(f"*/{zoom_level}/*/*.png"):
        try:
            # 验证路径结构: satellite_id, zoom, date, time.png
            relative_parts = file_path.relative_to(mosaics_base_path).parts
            if len(relative_parts) == 4 and relative_parts[1] == str(zoom_level):
                satellite_id = relative_parts[0]
                date_str = relative_parts[2]
                time_str = relative_parts[3].replace(".png", "")

                datetime_str = f"{date_str} {time_str}"
                dt_obj = datetime.strptime(datetime_str, "%Y-%m-%d %H%M")
                dt_obj_utc = dt_obj.replace(tzinfo=timezone.utc)
                timestamp = int(dt_obj_utc.timestamp())

                # 添加到数据结构
                if satellite_id not in all_files_info:
                    all_files_info[satellite_id] = {}
                all_files_info[satellite_id][timestamp] = file_path

            else:
                logger.debug(f"跳过不符合预期的路径格式: {file_path}")
        except ValueError as e:
            logger.warning(f"解析时间失败: {file_path} - {e}")
        except Exception as e:
            logger.error(f"处理文件 {file_path} 时发生未知错误: {e}")

    # --- 2. 检查是否收集到数据 ---
    if not all_files_info:
        logger.error(f"在 {mosaics_base_path} (zoom={zoom_level}) 中没有找到任何有效的图像信息。")
        raise typer.Exit(code=1)

    # --- 3. 合并、去重、排序所有时间戳 ---
    all_timestamps = set()
    for sat_timestamps in all_files_info.values():
        all_timestamps.update(sat_timestamps.keys())

    if not all_timestamps:
        logger.error("未能从收集到的文件中提取任何有效时间戳。")
        raise typer.Exit(code=1)

    # 获取当前UTC时间用于过滤
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    
    # 应用时间过滤
    filtered_timestamps = []
    for ts in all_timestamps:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        time_diff = now_utc - dt.replace(tzinfo=None)
        if hours == 0 or time_diff.total_seconds() <= hours * 3600:
            filtered_timestamps.append(ts)

    if not filtered_timestamps:
        logger.error(f"在指定的 {hours} 小时时间范围内没有找到任何有效时间戳。")
        raise typer.Exit(code=1)

    sorted_unique_timestamps = sorted(filtered_timestamps, reverse=True) # Newest first
    logger.info(f"共找到 {len(sorted_unique_timestamps)} 个唯一时间戳，将从最新开始处理。")

    # --- 4. 定义X偏移量 ---
    tile_width = 256
    satellite_offsets = {
        "goes-west": 0 * tile_width,
        "goes-east": 2 * tile_width,
        "mtg-zero": 6 * tile_width,  # Key used after resolving conflict
        "msg-iodc": 9 * tile_width,
        "himawari": 11 * tile_width,
    }
    # List of satellites relevant for blending
    relevant_satellites = list(satellite_offsets.keys())
    # Add msg-zero temporarily for conflict resolution step
    all_possible_satellites = relevant_satellites + ['msg-zero']


    # --- 5. 遍历唯一时间戳，生成混合图像 ---
    canvas_width = 4096
    canvas_height = 2048
    total_images_generated = 0

    for target_ts in sorted_unique_timestamps:
        target_dt = datetime.fromtimestamp(target_ts, tz=timezone.utc)
        target_date_str = target_dt.strftime("%Y-%m-%d")
        target_time_str = target_dt.strftime("%H%M")

        # --- 5a. 计算输出路径并检查是否已存在 ---
        output_dir_for_ts = output_base_dir / str(zoom_level) / target_date_str
        output_path = output_dir_for_ts / f"{target_time_str}.png"

        # Optional: Skip if already exists? For now, let's overwrite.
        # if output_path.exists():
        #     logger.debug(f"图像已存在，跳过: {output_path}")
        #     continue

        logger.info(f"--- 开始为时间戳 {target_ts} ({target_dt.isoformat()}) 生成混合图像 ---")

        # --- 5b. 确定此时间戳要使用的图像 ---
        images_to_use_for_ts: Dict[str, Path] = {}
        timestamps_used: Dict[str, int] = {} # Track actual timestamp used for conflict resolution

        for sat_id in all_files_info.keys(): # Iterate all satellites found
            available_ts_for_sat = sorted([ts for ts in all_files_info[sat_id].keys() if ts <= target_ts], reverse=True)
            if available_ts_for_sat:
                latest_available_ts = available_ts_for_sat[0]
                image_path = all_files_info[sat_id][latest_available_ts]
                images_to_use_for_ts[sat_id] = image_path
                timestamps_used[sat_id] = latest_available_ts
                logger.debug(f"  卫星 {sat_id}: 使用时间戳 {latest_available_ts} 的图像 ({image_path.name})")
            else:
                logger.debug(f"  卫星 {sat_id}: 在 {target_ts} 或之前无可用图像")

        # --- 5c. 处理 mtg-zero / msg-zero 冲突 ---
        mtg_path = images_to_use_for_ts.get('mtg-zero')
        msg_path = images_to_use_for_ts.get('msg-zero')
        mtg_ts = timestamps_used.get('mtg-zero')
        msg_ts = timestamps_used.get('msg-zero')

        final_images_to_blend: Dict[str, Path] = {}
        if mtg_path and msg_path:
            if mtg_ts >= msg_ts:
                logger.debug("  冲突解决: mtg-zero >= msg-zero, 使用 mtg-zero")
                final_images_to_blend['mtg-zero'] = mtg_path # Use mtg-zero key for offset
            else:
                logger.debug("  冲突解决: msg-zero > mtg-zero, 使用 msg-zero (作为 mtg-zero)")
                final_images_to_blend['mtg-zero'] = msg_path # Use mtg-zero key for offset
        elif mtg_path:
             final_images_to_blend['mtg-zero'] = mtg_path
        elif msg_path:
             logger.debug("  冲突解决: 只有 msg-zero, 使用 msg-zero (作为 mtg-zero)")
             final_images_to_blend['mtg-zero'] = msg_path # Use mtg-zero key for offset

        # Add other relevant satellites
        for sat_id in relevant_satellites:
            if sat_id != 'mtg-zero' and sat_id in images_to_use_for_ts:
                 final_images_to_blend[sat_id] = images_to_use_for_ts[sat_id]


        # --- 5d. 创建画布并混合 ---
        if not final_images_to_blend:
             logger.warning(f"时间戳 {target_ts}: 没有找到任何可用的卫星图像进行混合。")
             continue

        current_canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0)) # Transparent
        processed_count_for_ts = 0

        # Blend relevant satellites using their determined paths and offsets
        for satellite_id, image_path in final_images_to_blend.items():
             offset_x = satellite_offsets.get(satellite_id)
             if offset_x is None:
                 logger.warning(f"  内部错误: 卫星 {satellite_id} 缺少偏移量定义。")
                 continue

             if image_path.exists():
                 try:
                     with Image.open(image_path) as mosaic_img:
                         mosaic_img = mosaic_img.convert("RGBA")
                         temp_canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
                         paste_position = (offset_x, 0)
                         temp_canvas.paste(mosaic_img, paste_position, mosaic_img)
                         current_canvas = ImageChops.lighter(current_canvas, temp_canvas)
                         processed_count_for_ts += 1
                         logger.debug(f"    -> 已混合 {satellite_id} 从 {image_path.name}")
                 except Exception as e:
                     logger.error(f"    -> 打开或混合图像失败 {image_path}: {e}")
             else:
                 logger.warning(f"    -> 文件未找到（预期存在）: {image_path}")


        # --- 5e. 保存当前时间戳的图像 ---
        if processed_count_for_ts > 0:
            try:
                output_dir_for_ts.mkdir(parents=True, exist_ok=True)
                current_canvas.save(output_path)
                logger.info(f"  -> 成功生成并保存: {output_path} (混合了 {processed_count_for_ts} 个图像)")
                total_images_generated += 1
            except Exception as e:
                logger.error(f"  -> 保存混合图像失败 {output_path}: {e}")
        else:
             logger.warning(f"时间戳 {target_ts}: 处理了0个图像，未保存。")


    # --- 6. 完成总结 ---
    if total_images_generated > 0:
        logger.info(f"--- 全部完成 ---")
        logger.info(f"总共生成了 {total_images_generated} 张混合图像到目录: {output_base_dir}")
    else:
        logger.warning("任务完成，但没有生成任何混合图像。")

    # No return value needed


@app.command(name="process-concat")
def process_concat(
    input_dir: str = typer.Option("downloads", help="原始瓦片目录"),
    output_dir: str = typer.Option("mosaics", help="拼接结果目录"),
    tile_size: int = typer.Option(256, min=128, max=512, help="瓦片像素尺寸"),
    rotate: int = typer.Option(0, help="瓦片旋转角度 (0/90/180/270)"),
    show_coords: bool = typer.Option(False, "--show-coords/--no-coords", help="是否显示瓦片坐标信息"),
    satellites: Optional[List[str]] = typer.Option(
        None,
        "--satellites", "-s",
        help="选择卫星列表（空格分隔），例如 goes-east goes-west himawari，默认全部卫星"
    ),
    hours: int = typer.Option(
        2,
        "--hours", "-h",
        min=0,
        help="仅处理最新N小时内的数据（0表示不限制），默认2小时"
    ),
):
    """
    卫星图片拼接命令行工具
    """
    logger.info("启动卫星图片拼接任务...")

    base_path = Path(input_dir)
    if not base_path.exists():
        logger.error("输入目录不存在")
        raise typer.Exit(code=1)

    # 获取当前UTC时间
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

    # 遍历目录结构：卫星/日期/zoom/时间
    for satellite in base_path.iterdir():
        # 过滤非目录和不在列表中的卫星
        if not satellite.is_dir():
            continue
        if satellites and satellite.name not in satellites:
            logger.debug(f"跳过非指定卫星: {satellite.name}")
            continue

        # 遍历 satellite 目录下的 zoom 级别目录
        for zoom_dir in satellite.iterdir(): # 使用 iterdir 获取直接子项
            if not zoom_dir.is_dir():
                logger.debug(f"跳过非目录项: {zoom_dir}")
                continue # 跳过文件或其他非目录项

            if not zoom_dir.name.isdigit():
                logger.debug(f"跳过非数字命名的 zoom 目录: {zoom_dir.name}")
                continue # 跳过名称不是数字的目录

            # 确认 zoom_dir 是一个有效的 zoom 级别目录
            logger.info(f"处理 zoom 目录: {zoom_dir.name}") # 移动日志记录

            # 遍历 zoom 目录下的日期目录
            for date_dir in zoom_dir.iterdir():
                if not date_dir.is_dir():
                    logger.debug(f"跳过 {zoom_dir.name} 下的非日期目录项: {date_dir}")
                    continue

                # 遍历日期目录下的时间目录
                for time_dir in date_dir.iterdir():
                    if not time_dir.is_dir():
                        logger.debug(f"跳过 {date_dir.name} 下的非时间目录项: {time_dir}")
                        continue

                    # 处理时间范围过滤
                    if hours > 0:
                        try:
                            # 解析日期和时间（目录格式为 2025-03-20 和 1130）
                            dt = datetime.strptime(
                                f"{date_dir.name}{time_dir.name}",
                                "%Y-%m-%d%H%M"  # 匹配 2025-03-201130 格式
                            )
                        except ValueError as e:
                            logger.warning(f"时间格式错误: {date_dir.name}/{time_dir.name} ({e})")
                            continue

                        # 计算时间差（UTC 时间）
                        time_diff = now_utc - dt
                        if time_diff.total_seconds() > hours * 3600:
                            logger.debug(f"跳过过期数据 [{dt}] 距今 {time_diff}")
                            continue

                    # 生成输出路径（包含zoom级别）
                    output_path = (
                        Path(output_dir)
                        / satellite.name
                        / zoom_dir.name # 添加 zoom 级别
                        / date_dir.name
                        / f"{time_dir.name}.png"
                    )

                    # 执行拼接
                    concat_tiles(
                        tile_dir=time_dir,
                        output_path=output_path,  # type: ignore
                        tile_size=tile_size,
                        rotate_deg=rotate,
                        show_coords=show_coords
                    )

    logger.info("所有拼接任务已完成")


@app.command(name="process-concat-all")
def process_concat_all(
    input_dir: str = typer.Option("downloads", help="由 process-all 下载的原始瓦片目录"),
    output_dir: str = typer.Option("mosaics_all", help="拼接结果目录"),
    tile_size: int = typer.Option(256, min=128, max=512, help="瓦片像素尺寸"),
    rotate: int = typer.Option(0, help="瓦片旋转角度 (0/90/180/270)"),
    show_coords: bool = typer.Option(False, "--show-coords/--no-coords", help="是否显示瓦片坐标信息"),
    hours: int = typer.Option(
        0,
        "--hours", "-h",
        min=0,
        help="仅处理最新N小时内的数据（0表示不限制），默认1小时"
    ),
    zoom_level: int = typer.Option(
        4,
        "--zoom", "-z",
        min=4, max=5,
        help="要处理的 zoom 级别 (4 或 5)，默认 4"
    )
):
    """
    拼接由 process-all 下载的卫星图片
    """
    logger.info(f"启动 'process-all' 图片拼接任务 (Zoom: {zoom_level})...")

    base_path = Path(input_dir)
    if not base_path.exists():
        logger.error(f"输入目录不存在: {input_dir}")
        raise typer.Exit(code=1)

    # 获取当前UTC时间
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

    # 遍历目录结构：zoom/日期/时间
    zoom_path = base_path / str(zoom_level)
    if not zoom_path.is_dir():
        logger.warning(f"Zoom 级别目录不存在: {zoom_path}")
        return # 或者 raise typer.Exit(code=1) 如果需要强制

    # 遍历日期目录
    for date_dir in zoom_path.glob("*"):
        if not date_dir.is_dir():
            continue

        # 遍历时间目录
        for time_dir in date_dir.glob("*"):
            if not time_dir.is_dir():
                continue

            # 处理时间范围过滤
            if hours > 0:
                try:
                    # 解析日期和时间（目录格式为 2025-03-20 和 1130）
                    dt = datetime.strptime(
                        f"{date_dir.name}{time_dir.name}",
                        "%Y-%m-%d%H%M"  # 匹配 2025-03-201130 格式
                    )
                except ValueError as e:
                    logger.warning(f"时间格式错误: {date_dir.name}/{time_dir.name} ({e})")
                    continue

                # 计算时间差（UTC 时间）
                time_diff = now_utc - dt
                if time_diff.total_seconds() > hours * 3600:
                    logger.debug(f"跳过过期数据 [{dt}] 距今 {time_diff}")
                    continue

            # 生成输出路径（包含zoom级别）
            output_path = (
                Path(output_dir)
                / str(zoom_level)
                / date_dir.name
                / f"{time_dir.name}.png"
            )

            # 执行拼接
            try:
                concat_tiles(
                    tile_dir=time_dir,
                    output_path=output_path,
                    tile_size=tile_size,
                    rotate_deg=rotate,
                    reverse_y=False, # 根据实际需要调整
                    show_coords=show_coords,
                    swap_xy=True # 根据实际需要调整
                )
            except Exception as e:
                 logger.error(f"拼接失败: {time_dir} -> {output_path} | 错误: {e}", exc_info=True)


    logger.info(f"Zoom {zoom_level} 的拼接任务已完成")


@app.command(name="process-api")
def process_from_api(
    concurrency: int = typer.Option(
        20,
        "--concurrency", "-c",
        min=1, max=20,
        help="并发下载线程数 (1-20)"
    ),
    satellites: List[str] = typer.Option(
        None,
        "--satellites", "-s",
        help="选择卫星列表（空格分隔），例如 goes-east goes-west himawari, msg-iodc, msg-zero, mtg-zer, 默认全部卫星"
    ),
    hours: int = typer.Option(
        1,
        "--hours", "-h",
        min=0,
        help="仅下载最新N小时内的数据（0表示不限制），默认1小时"
    ),
    zoom: int = typer.Option(
        4,
        "--zoom", "-z",
        min=4, max=5,
        help="zoom级别 (4或5)，默认4"
    )
):
    """主流程（支持卫星选择和时间过滤）"""
    try:
        logger.info(f"启动下载任务 | 并发数: {concurrency} | 卫星: {satellites or '全部'} | 时间范围: {hours}小时")
        batch_download(
            concurrency=concurrency,
            satellites=satellites,
            hours=hours,
            zoom=zoom
        )
        print(Panel("[bold green]所有任务完成![/]", title="完成通知"))
    except Exception as e:
        logger.error(f"严重错误: {str(e)}")
        logger.debug(traceback.format_exc())
        print(Panel(f"[bold red]API 处理错误: {str(e)}[/]", title="严重错误"))

@app.command(name="process-all")
def process_all(
    concurrency: int = typer.Option(
        20,
        "--concurrency", "-c",
        min=1, max=40,
        help="并发下载线程数 (1-20)"
    ),
    hours: int = typer.Option(
        1,
        "--hours", "-h",
        min=1,
        help="仅下载最新N小时内的数据（0表示不限制），默认1小时"
    ),
    zoom: int = typer.Option(
        4,
        "--zoom", "-z",
        min=4, max=5,
        help="zoom级别 (4或5)，默认4"
    )
):
    """
    下载所有卫星数据
    """
    try:
        logger.info(f"启动下载任务 | 并发数: {concurrency} | 时间范围: {hours}小时")
        all_download(
            concurrency=concurrency,
            hours=hours,
            zoom=zoom
        )
        print(Panel("[bold green]所有任务完成![/]", title="完成通知"))
    except Exception as e:
        logger.error(f"严重错误: {str(e)}")
        logger.debug(traceback.format_exc())
        print(Panel(f"[bold red]API 处理错误: {str(e)}[/]", title="严重错误"))

@app.command(name="legacy-process-api")
def legacy_process_from_api():
    """兼容旧版计算命令"""
    process_from_api() # 直接调用新的函数

if __name__ == "__main__":
    app()
