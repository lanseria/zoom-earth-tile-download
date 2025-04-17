import typer
from rich import print
from rich.panel import Panel
import logging
from pathlib import Path
from typing import List, Optional
import traceback
from datetime import datetime
import traceback

from zoom_earth_cli.ffmpeg import generate_timelapse
from zoom_earth_cli.api_client import batch_download
from zoom_earth_cli.blender import process_blend_core
from zoom_earth_cli.const import get_satellite_tile_range, get_bound_tile_range, calculate_canvas_size, COUNTRY_BOUNDS
from zoom_earth_cli.concat import process_concat_core

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
        "--hours", "-h",
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


@app.command(name="blend")
def blend(
    mosaics_dir: str = typer.Option(
        "mosaics",
        "--input", "-i",
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
    country: str = typer.Option(
        "global",
        "--country", "-c",
        help="指定国家，默认为全球范围"
    ),
    zoom_level: int = typer.Option(
        4,
        "--zoom", "-z",
        min=4, max=5,
        help="zoom级别 (4或5)，默认4"
    ),
    hours: int = typer.Option(
        0,
        "--hours", "-h",
        min=0,
        help="仅处理最新N小时内的数据（0表示不限制），默认0小时"
    ),
) -> None:
    """
    扫描mosaics，为每个唯一时间戳生成一个混合图像。
    图像按时间倒序生成，如果卫星在某个时间点无数据，则使用其之前最新的数据。
    使用 'lighter' 模式混合，并根据预设X偏移量放置。
    可通过--hours参数限制只处理最近N小时的数据。
    """
    country_bounds = COUNTRY_BOUNDS[country]
    c_x_range, c_y_range = get_bound_tile_range(zoom=zoom_level, bound=country_bounds)
    print(f"国家: {country} | X范围: {c_x_range} | Y范围: {c_y_range}")
    canvas_width, canvas_height = calculate_canvas_size(c_x_range, c_y_range)

    # 拼接 mosaics_dir 和 country
    mosaics_dir = str(Path(mosaics_dir) / country)
    output_filename = str(Path(output_filename) / country)
    process_blend_core(
        canvas_height=canvas_height,
        canvas_width=canvas_width,
        mosaics_dir=mosaics_dir,
        output_base_dir=output_filename,
        hours=hours,
        logger=logger,
        satellite_offsets={
            "msg-iodc": 0,
            "himawari": 1,
        },
        zoom_level=zoom_level,
    )


@app.command(name="process-blend")
def process_blend(
    mosaics_dir: str = typer.Option(
        "mosaics/global",
        "--input", "-i",
        help="包含拼接后卫星图像的目录",
        exists=True,
        file_okay=False,
        dir_okay=True
    ),
    output_filename: str = typer.Option(
        "lighter_blend/global", # Default output directory
        "--output-dir", "-o",
        help="输出混合图像序列的根目录"
    ),
    hours: int = typer.Option(
        0,
        "--hours", "-h",
        min=0,
        help="仅处理最新N小时内的数据（0表示不限制），默认0小时"
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="强制覆盖已存在的输出文件"
    )
) -> None:
    """
    扫描mosaics，为每个唯一时间戳生成一个混合图像。
    图像按时间倒序生成，如果卫星在某个时间点无数据，则使用其之前最新的数据。
    使用 'lighter' 模式混合，并根据预设X偏移量放置。
    可通过--hours参数限制只处理最近N小时的数据。
    """
    process_blend_core(
        canvas_height=2048,
        canvas_width=4096,
        mosaics_dir=mosaics_dir,
        output_base_dir=output_filename,
        hours=hours,
        logger=logger,
        satellite_offsets={
            "goes-west": 0 * 256,
            "goes-east": 2 * 256,
            "mtg-zero": 6 * 256,
            "msg-iodc": 9 * 256,
            "himawari": 11 * 256,
        },
        zoom_level=4,
        overwrite=overwrite
    )


@app.command(name="process-concat")
def process_concat(
    input_dir: str = typer.Option(
        "downloads/global",
        "--input", "-i",
        help="原始瓦片目录"
    ),
    output_dir: str = typer.Option(
        "mosaics/global",
        "--output", "-o",
        help="拼接结果目录"
    ),
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
    process_concat_core(
        input_dir=input_dir,
        output_dir=output_dir,
        tile_size=tile_size,
        rotate=rotate,
        show_coords=show_coords,
        satellites=satellites,
        hours=hours,
        logger=logger
    )


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
        help="选择卫星列表（空格分隔），例如 goes-east goes-west himawari, msg-iodc, msg-zero, mtg-zero, 默认全部卫星"
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
    ),
    country: str = typer.Option(
        None,
        "--country",
        help="按国家边界筛选（可选: usa, canada, china, india, brazil, australia, russia, japan, france, germany）"
    )
):
    """主流程（支持卫星选择、时间过滤和国家边界筛选）"""
    try:
        # 构建日志信息
        log_info = [
            f"启动下载任务 | 并发数: {concurrency}",
            f"卫星: {satellites or '全部'}",
            f"时间范围: {hours}小时",
            f"国家: {country or '全球'}"
        ]
        logger.info(" | ".join(log_info))
        
        batch_download(
            concurrency=concurrency,
            satellites=satellites,
            hours=hours,
            zoom=zoom,
            country=country
        )
        print(Panel("[bold green]所有任务完成![/]", title="完成通知"))
    except ValueError as e:
        # 处理国家参数错误
        logger.error(f"参数错误: {str(e)}")
        traceback.print_exc()
    except Exception as e:
        logger.error(f"严重错误: {str(e)}")
        logger.debug(traceback.format_exc())
        print(Panel(f"[bold red]API 处理错误: {str(e)}[/]", title="严重错误"))


@app.command(name="test")
def test():
    x_range, y_range = get_satellite_tile_range(zoom=4, satellite="himawari")
    print(f"X Range: {x_range}")
    print(f"Y Range: {y_range}")


if __name__ == "__main__":
    app()
