import typer
from rich import print
from rich.panel import Panel
import logging
from pathlib import Path
import traceback
from zoom_earth_cli.utils import batch_download, concat_tiles

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


@app.command(name="process-concat")
def process_concat(
    input_dir: str = typer.Option("downloads", help="原始瓦片目录"),
    output_dir: str = typer.Option("mosaics", help="拼接结果目录"),
    tile_size: int = typer.Option(256, min=128, max=512, help="瓦片像素尺寸"),
    rotate: int = typer.Option(
        0,
        help="瓦片旋转角度 (0/90/180/270)"
    ),
    show_coords: bool = typer.Option(
        False,
        "--show-coords/--no-coords",
        help="是否显示瓦片坐标信息"
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

    # 遍历目录结构：卫星/日期/时间
    for satellite in base_path.iterdir():
        if not satellite.is_dir():
            continue
            
        for date_dir in satellite.glob("*"):
            if not date_dir.is_dir():
                continue
                
            for time_dir in date_dir.glob("*"):
                if not time_dir.is_dir():
                    continue
                
                # 生成输出路径
                output_path = Path(output_dir) / satellite.name / date_dir.name / f"{time_dir.name}.png"
                
                # 执行拼接
                concat_tiles(
                    tile_dir=time_dir,
                    output_path=output_path,
                    tile_size=tile_size,
                    rotate_deg=rotate,
                    show_coords=show_coords
                )

    logger.info("所有拼接任务已完成")


@app.command(name="process-api")
def process_from_api(
    concurrency: int = typer.Option(
        5, 
        "--concurrency", "-c",
        min=1, max=20,
        help="并发下载线程数 (1-20)"
    )
):
    """主流程"""
    try:
        logger.info(f"启动下载任务，并发数: {concurrency}")
        batch_download(concurrency=concurrency)
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