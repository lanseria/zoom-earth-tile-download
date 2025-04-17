from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List
from zoom_earth_cli.utils import concat_tiles

def process_concat_core(
    input_dir: str,
    output_dir: str,
    tile_size: int,
    rotate: int,
    show_coords: bool,
    satellites: Optional[List[str]],
    hours: int,
    logger
):
    """
    卫星图片拼接核心逻辑
    """
    logger.info("启动卫星图片拼接任务...")

    base_path = Path(input_dir)
    if not base_path.exists():
        logger.error("输入目录不存在")
        raise SystemExit(1)

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

    for satellite in base_path.iterdir():
        if not satellite.is_dir():
            continue
        if satellites and satellite.name not in satellites:
            logger.debug(f"跳过非指定卫星: {satellite.name}")
            continue

        for zoom_dir in satellite.iterdir():
            if not zoom_dir.is_dir():
                logger.debug(f"跳过非目录项: {zoom_dir}")
                continue
            if not zoom_dir.name.isdigit():
                logger.debug(f"跳过非数字命名的 zoom 目录: {zoom_dir.name}")
                continue

            logger.info(f"处理 zoom 目录: {zoom_dir.name}")

            for date_dir in zoom_dir.iterdir():
                if not date_dir.is_dir():
                    logger.debug(f"跳过 {zoom_dir.name} 下的非日期目录项: {date_dir}")
                    continue

                for time_dir in date_dir.iterdir():
                    if not time_dir.is_dir():
                        logger.debug(f"跳过 {date_dir.name} 下的非时间目录项: {time_dir}")
                        continue

                    if hours > 0:
                        try:
                            dt = datetime.strptime(
                                f"{date_dir.name}{time_dir.name}",
                                "%Y-%m-%d%H%M"
                            )
                        except ValueError as e:
                            logger.warning(f"时间格式错误: {date_dir.name}/{time_dir.name} ({e})")
                            continue

                        time_diff = now_utc - dt
                        if time_diff.total_seconds() > hours * 3600:
                            logger.debug(f"跳过过期数据 [{dt}] 距今 {time_diff}")
                            continue

                    output_path = (
                        Path(output_dir)
                        / satellite.name
                        / zoom_dir.name
                        / date_dir.name
                        / f"{time_dir.name}.png"
                    )

                    concat_tiles(
                        tile_dir=time_dir,
                        output_path=output_path,  # type: ignore
                        tile_size=tile_size,
                        rotate_deg=rotate,
                        show_coords=show_coords
                    )

    logger.info("所有拼接任务已完成")
