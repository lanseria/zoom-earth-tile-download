# const.py
import math
from typing import Tuple

SATELLITE_BOUNDS = {
    "goes-west":  (-180, -60, -112.5, 60),  # 实际覆盖西经165至105
    "goes-east":  (-135, -60, 0, 60),   # 调整以匹配切片
    "mtg-zero":   (-45, -60, 45, 60),
    "msg-zero":   (-45, -60, 45, 60),
    "msg-iodc":   (22.5, -60, 90, 60),
    "himawari":   (67.5, -60, 180, 60),     # 结束经度修正为180
}

COUNTRY_BOUNDS = {
    "usa": (-125.0, 24.0, -66.0, 50.0),       # 美国本土（不含阿拉斯加和夏威夷）
    "canada": (-141.0, 41.7, -52.6, 83.1),    # 加拿大
    "china": (73.6, 18.2, 135.1, 53.6),       # 中国（含台湾地区）
    "india": (68.2, 6.8, 97.4, 35.7),         # 印度
    "brazil": (-74.0, -33.8, -34.7, 5.3),     # 巴西
    "australia": (112.9, -43.6, 153.6, -10.7), # 澳大利亚
    "russia": (19.6, 41.2, 180.0, 82.4),      # 俄罗斯（西经部分调整到180）
    "japan": (122.9, 24.2, 153.9, 45.5),      # 日本
    "france": (-5.0, 41.3, 9.6, 51.1),        # 法国（本土）
    "germany": (5.9, 47.3, 15.0, 54.9),       # 德国
}

def range_intersection(a_range, b_range):
    """返回两个闭区间的交集，若无交集返回 None"""
    a_min, a_max = a_range
    b_min, b_max = b_range
    left = max(a_min, b_min)
    right = min(a_max, b_max)
    if left > right:
        return None
    return (left, right)

def lonlat_to_tile_xy(lon, lat, zoom):
    n = 2.0 ** zoom
    x = (lon + 180.0) / 360.0 * n
    lat_rad = math.radians(lat)
    y = (1.0 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2.0 * n
    return x, y

def get_tile_range_by_bound(zoom, min_lon, min_lat, max_lon, max_lat):
    # 注意：最大纬度对应最小Y（北边），最小纬度对应最大Y（南边）
    x_min, y_min = lonlat_to_tile_xy(min_lon, max_lat, zoom)
    x_max, y_max = lonlat_to_tile_xy(max_lon, min_lat, zoom)
    # 取整到瓦片编号，确保顺序正确
    x_range = range(int(x_min), int(x_max))
    y_range = range(int(y_min), int(y_max) + 1)
    return y_range, x_range

def get_satellite_tile_range(zoom, satellite):
    bound = SATELLITE_BOUNDS[satellite]
    min_lon, min_lat, max_lon, max_lat = bound
    return get_tile_range_by_bound(zoom, min_lon, min_lat, max_lon, max_lat)

def get_bound_tile_range(zoom, bound):
    min_lon, min_lat, max_lon, max_lat = bound
    return get_tile_range_by_bound(zoom, min_lon, min_lat, max_lon, max_lat)

def calculate_canvas_size(x_range: range, y_range: range, tile_size: int = 256) -> tuple[int, int]:
    """计算拼接后的画布尺寸（宽度、高度）"""
    width = (x_range.stop - x_range.start) * tile_size
    height = (y_range.stop - y_range.start) * tile_size
    return width, height

# 定义拼接范围常量
X_RANGE_CONCAT = range(0, 16)
Y_RANGE_CONCAT = range(0, 16)
