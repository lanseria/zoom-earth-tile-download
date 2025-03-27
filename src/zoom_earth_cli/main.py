import typer
from rich import print
from rich.panel import Panel
import logging
from pathlib import Path
from typing import List, Optional
import traceback
from datetime import datetime, timezone
from PIL import Image, ImageChops

from zoom_earth_cli.ffmpeg import generate_timelapse
from zoom_earth_cli.api_client import batch_download
from zoom_earth_cli.utils import concat_tiles, smart_feather_alpha


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
def process_blend(): 
    # 输入文件列表
    paths = [
        "mosaics/goes-east/2025-03-21/0200.png",
        "mosaics/goes-west/2025-03-21/0200.png",
        "mosaics/himawari/2025-03-21/0130.png",
        "mosaics/msg-iodc/2025-03-21/0145.png",
        # "mosaics/msg-zero/2025-03-21/0145.png",
        "mosaics/mtg-zero/2025-03-21/0150.png"
    ]
    # 每个卫星图的参数
    BOUNDARY_CONFIG = {
        "goes-east": {"left": 512, "right": 1921 },
        "goes-west": {"left": 0, "right": 512},
        "himawari": {"left": 3008, "right": 4096},
        "msg-iodc": {"left": 2496, "right": 3008},
        # "msg-zero": {"left": 1728, "right": 2496},
        "mtg-zero": {"left": 1921, "right": 2496},
    }
    # 初始化合成画布（带透明通道）
    composite = Image.new("RGBA", (4096, 2048), (0, 0, 0, 0))
    
    for path in paths:
        satellite = path.split("/")[1]  
        config = BOUNDARY_CONFIG.get(satellite, {"left":0, "right":4096})
        with Image.open(path) as img:
            # 应用智能羽化
            feathered = smart_feather_alpha(
                img,
                left_margin=config["left"],
                right_margin=config["right"],
                feather_width=0,  # 可根据需要调整
                debug=True, # 启用调试模式
                debug_dir=f"debug_output/"
            )
            # 使用"lighten"混合模式（取像素最大值）
            composite = ImageChops.lighter(composite, feathered.convert("RGBA"))
    
    # 最终保存为不透明格式
    composite.convert("RGBA").resize([8192, 4096]).save("combined_output.png")


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
        1,
        "--hours", "-h", 
        min=0,
        help="仅处理最新N小时内的数据（0表示不限制），默认1小时"
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

        # 遍历日期目录
        for zoom_dir in satellite.glob("*"):
            if not zoom_dir.is_dir():
                continue

            # 遍历zoom目录
            for date_dir in zoom_dir.glob("*"):
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
                        / satellite.name 
                        / zoom_dir.name
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


@app.command(name="legacy-process-api")
def legacy_process_from_api():
    """兼容旧版计算命令"""
    process_from_api()

if __name__ == "__main__":
    app()
