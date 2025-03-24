import logging
import os
import datetime
import subprocess
from pathlib import Path

def generate_timelapse(
    input_dir: str,
    output_file: str,
    duration_hours: int = 24,
    start_time: str = None,
    framerate: int = 30
):
    """
    生成卫星图像延时视频
    
    参数:
    input_dir: 输入目录 (如 mosaics/himawari)
    output_file: 输出视频文件路径 (如 output.mp4)
    duration_hours: 视频时长（小时），默认24
    start_time: 起始时间 (格式: YYYY-MM-DDTHH:MM)，默认使用最新时间
    framerate: 输出视频帧率，默认30
    """
    
    # 解析时间参数
    if start_time:
        start_dt = datetime.datetime.fromisoformat(start_time)
    else:
        start_dt = get_latest_image_time(input_dir)
    
    end_dt = start_dt - datetime.timedelta(hours=duration_hours)
    
    # 收集符合条件的图像路径
    image_files = []
    for date_dir in sorted(Path(input_dir).iterdir(), reverse=True):
        if not date_dir.is_dir():
            continue
            
        date_str = date_dir.name
        try:
            current_date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue
            
        # 处理跨日情况
        if current_date.date() > start_dt.date():
            continue
        if current_date.date() < (start_dt - datetime.timedelta(hours=duration_hours)).date():
            break
            
        for img_file in sorted(date_dir.glob("*.png"), reverse=True):
            time_str = img_file.stem
            try:
                img_time = datetime.datetime.strptime(time_str, "%H%M")
            except ValueError:
                continue
                
            full_dt = current_date.replace(
                hour=img_time.hour,
                minute=img_time.minute
            )
            
            if end_dt <= full_dt <= start_dt:
                image_files.append((full_dt, str(img_file)))
                
    # 按时间顺序排序
    image_files.sort(key=lambda x: x[0])
    
    if not image_files:
        print("未找到符合时间范围的图像")
        return
    
    # 在生成输入列表前添加验证
    valid_files = []
    for dt, path in image_files:
        if not Path(path).exists():
            logging.warning(f"文件不存在: {path}")
            continue
        if os.path.getsize(path) == 0:
            logging.warning(f"空文件: {path}")
            continue
        valid_files.append((dt, path))

    if len(valid_files) != len(image_files):
        logging.error(f"发现 {len(image_files)-len(valid_files)} 个无效文件")
    
    # 计算实际帧率
    total_frames = len(image_files)
    target_duration = duration_hours * 3600  # 目标视频时长（秒）
    actual_framerate = total_frames / target_duration
    
    # 生成FFmpeg输入列表（增加duration配置）
    temp_list = Path("input_list.txt")
    with temp_list.open("w") as f:
        for _, path in image_files:
            # 添加每张图片的持续时间（单位秒）
            duration = 1 / actual_framerate
            f.write(f"file '{path}'\n")
            f.write(f"duration {duration:.5f}\n")
    
    
    # 修改后的FFmpeg命令
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(temp_list),
        "-fps_mode", "cfr",          # 替代旧的 -vsync 参数
        "-r", str(framerate),        # 输出帧率
        "-vf", "format=yuv420p,setpts=N/FRAME_RATE/TB",  # 正确的时间戳处理
        "-c:v", "libx264",
        "-crf", "23",
        "-preset", "medium",
        "-x264-params", "keyint=60:min-keyint=30",
        "-movflags", "+faststart",
        "-loglevel", "debug",        # 开启详细日志
        str(output_file)
    ]
    
    # 执行命令（增加错误处理）
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"FFmpeg执行失败，保留输入文件 {temp_list} 用于调试")
        print("错误输出：")
        print(e.stderr)
        raise
    finally:
      # 清理临时文件
      temp_list.unlink()

def get_latest_image_time(input_dir: str) -> datetime.datetime:
    """获取目录中最新的图像时间"""
    latest = None
    for date_dir in sorted(Path(input_dir).iterdir(), reverse=True):
        if not date_dir.is_dir():
            continue
            
        date_str = date_dir.name
        try:
            current_date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue
            
        for img_file in sorted(date_dir.glob("*.png"), reverse=True):
            time_str = img_file.stem
            try:
                img_time = datetime.datetime.strptime(time_str, "%H%M")
                full_dt = current_date.replace(
                    hour=img_time.hour,
                    minute=img_time.minute
                )
                if latest is None or full_dt > latest:
                    latest = full_dt
                return latest  # 找到最新立即返回
            except ValueError:
                continue
                
    raise ValueError("目录中没有有效图像")