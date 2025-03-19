import typer
from rich import print
from rich.panel import Panel
import logging
import traceback
from typing import Dict

from zoom_earth_cli.api_client import get_latest_times, download_tile

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

@app.command(name="process-api")
def process_from_api():
    """主流程"""
    try:
        batch_download()
    except Exception as e:
        logger.error(f"严重错误: {str(e)}")
        logger.debug(traceback.format_exc())  # 调试模式记录完整堆栈
        print(Panel(f"[bold red]API 处理错误: {str(e)}[/]", title="严重错误"))

def batch_download():
    """批量下载主逻辑"""
    latest_times: Dict = get_latest_times()
    
    if not latest_times:
        logger.error("获取卫星时间数据失败")
        return

    # 定义下载范围
    x_range = range(4, 12)
    y_range = range(0, 16)

    for satellite, timestamp in latest_times.items():
        logger.info(f"开始处理卫星: {satellite}")
        
        success = 0
        skipped = 0
        
        for x in x_range:
            for y in y_range:
                if download_tile(satellite, timestamp, x, y):
                    logger.debug(f"下载成功 - X:{x} Y:{y}")  # 详细下载记录
                    success += 1
                else:
                    logger.warning(f"下载失败 - X:{x} Y:{y}")  # 警告级日志
                    skipped += 1
        
        # 汇总使用 INFO 级别
        logger.info(
            f"完成 {satellite} - "
            f"成功: {success} / 失败: {skipped} "
            f"总数: {success + skipped}"
        )

@app.command(name="legacy-process-api")
def legacy_process_from_api():
    """兼容旧版计算命令"""
    process_from_api()


if __name__ == "__main__":
    app()