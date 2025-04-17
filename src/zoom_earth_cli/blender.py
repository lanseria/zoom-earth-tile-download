from typing import Dict
from pathlib import Path
from datetime import datetime, timezone
from PIL import Image, ImageChops

def process_blend_core(
    mosaics_dir: str,
    output_base_dir: str,
    hours: int,
    canvas_width: int,
    canvas_height: int,
    satellite_offsets: Dict[str, int],
    logger,
    zoom_level: int = 4,
    overwrite: bool = False,
):
    mosaics_base_path = Path(mosaics_dir)
    output_base_dir = Path(output_base_dir)

    # 1. 收集所有文件信息
    all_files_info: Dict[str, Dict[int, Path]] = {}
    logger.info(f"正在扫描 {mosaics_base_path} 下 zoom={zoom_level} 的图像...")
    for file_path in mosaics_base_path.glob(f"*/{zoom_level}/*/*.png"):
        try:
            relative_parts = file_path.relative_to(mosaics_base_path).parts
            if len(relative_parts) == 4 and relative_parts[1] == str(zoom_level):
                satellite_id = relative_parts[0]
                date_str = relative_parts[2]
                time_str = relative_parts[3].replace(".png", "")

                datetime_str = f"{date_str} {time_str}"
                dt_obj = datetime.strptime(datetime_str, "%Y-%m-%d %H%M")
                dt_obj_utc = dt_obj.replace(tzinfo=timezone.utc)
                timestamp = int(dt_obj_utc.timestamp())

                if satellite_id not in all_files_info:
                    all_files_info[satellite_id] = {}
                all_files_info[satellite_id][timestamp] = file_path
            else:
                logger.debug(f"跳过不符合预期的路径格式: {file_path}")
        except Exception as e:
            logger.warning(f"解析文件失败: {file_path} - {e}")

    if not all_files_info:
        logger.error(f"在 {mosaics_base_path} (zoom={zoom_level}) 中没有找到任何有效的图像信息。")
        return 0, 0

    # 2. 合并所有时间戳
    all_timestamps = set()
    for sat_timestamps in all_files_info.values():
        all_timestamps.update(sat_timestamps.keys())
    if not all_timestamps:
        logger.error("未能从收集到的文件中提取任何有效时间戳。")
        return 0, 0

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    filtered_timestamps = [
        ts for ts in all_timestamps
        if hours == 0 or (now_utc - datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)).total_seconds() <= hours * 3600
    ]
    if not filtered_timestamps:
        logger.error(f"在指定的 {hours} 小时时间范围内没有找到任何有效时间戳。")
        return 0, 0

    sorted_unique_timestamps = sorted(filtered_timestamps, reverse=True)
    logger.info(f"共找到 {len(sorted_unique_timestamps)} 个唯一时间戳，将从最新开始处理。")

    # 3. 相关卫星列表与偏移处理
    tile_width = 256
    relevant_satellites = list(satellite_offsets.keys())
    all_possible_satellites = relevant_satellites + ['msg-zero']

    total_images_generated = 0
    total_images_skipped = 0

    for target_ts in sorted_unique_timestamps:
        target_dt = datetime.fromtimestamp(target_ts, tz=timezone.utc)
        target_date_str = target_dt.strftime("%Y-%m-%d")
        target_time_str = target_dt.strftime("%H%M")

        output_dir_for_ts = output_base_dir / str(zoom_level) / target_date_str
        output_path = output_dir_for_ts / f"{target_time_str}.png"

        if not overwrite and output_path.exists():
            logger.debug(f"图像已存在，跳过: {output_path}")
            total_images_skipped += 1
            continue

        logger.info(f"--- 开始为时间戳 {target_ts} ({target_dt.isoformat()}) 生成混合图像 ---")

        images_to_use_for_ts: Dict[str, Path] = {}
        timestamps_used: Dict[str, int] = {}

        for sat_id in all_files_info.keys():
            available_ts_for_sat = sorted([ts for ts in all_files_info[sat_id].keys() if ts <= target_ts], reverse=True)
            if available_ts_for_sat:
                latest_available_ts = available_ts_for_sat[0]
                image_path = all_files_info[sat_id][latest_available_ts]
                images_to_use_for_ts[sat_id] = image_path
                timestamps_used[sat_id] = latest_available_ts
                logger.debug(f"  卫星 {sat_id}: 使用时间戳 {latest_available_ts} 的图像 ({image_path.name})")
            else:
                logger.debug(f"  卫星 {sat_id}: 在 {target_ts} 或之前无可用图像")

        mtg_path = images_to_use_for_ts.get('mtg-zero')
        msg_path = images_to_use_for_ts.get('msg-zero')
        mtg_ts = timestamps_used.get('mtg-zero')
        msg_ts = timestamps_used.get('msg-zero')

        final_images_to_blend: Dict[str, Path] = {}
        if mtg_path and msg_path:
            if mtg_ts >= msg_ts:
                final_images_to_blend['mtg-zero'] = mtg_path
            else:
                final_images_to_blend['mtg-zero'] = msg_path
        elif mtg_path:
            final_images_to_blend['mtg-zero'] = mtg_path
        elif msg_path:
            final_images_to_blend['mtg-zero'] = msg_path

        for sat_id in relevant_satellites:
            if sat_id != 'mtg-zero' and sat_id in images_to_use_for_ts:
                final_images_to_blend[sat_id] = images_to_use_for_ts[sat_id]

        if not final_images_to_blend:
            logger.warning(f"时间戳 {target_ts}: 没有找到任何可用的卫星图像进行混合。")
            continue

        current_canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
        processed_count_for_ts = 0

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

    logger.info(f"处理完成。共生成 {total_images_generated} 个混合图像，跳过 {total_images_skipped} 个已存在的图像。")
    return total_images_generated, total_images_skipped