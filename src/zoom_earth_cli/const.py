# const.py
import math

SATELLITE_BOUNDS = {
    "goes-west":  (-180, -60, -112.5, 60),  # 实际覆盖西经165至105
    "goes-east":  (-135, -60, 0, 60),   # 调整以匹配切片
    "mtg-zero":   (-45, -60, 45, 60),
    "msg-zero":   (-45, -60, 45, 60),
    "msg-iodc":   (22.5, -60, 90, 60),
    "himawari":   (67.5, -60, 180, 60),     # 结束经度修正为180
}

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

def get_satellite_tile_range(zoom, satellite, bound=None):
    if bound is None:
        if satellite not in SATELLITE_BOUNDS:
            raise ValueError(f"Unknown satellite: {satellite}")
        bound = SATELLITE_BOUNDS[satellite]
    min_lon, min_lat, max_lon, max_lat = bound
    return get_tile_range_by_bound(zoom, min_lon, min_lat, max_lon, max_lat)

# 定义下载范围常量
# def get_ranges_for_zoom(zoom: int, satellite: str):
#     """根据zoom级别计算X和Y的范围"""
#     if zoom == 4:
#         # ["goes-east", "goes-west", "himawari", "msg-iodc", "msg-zero", "mtg-zero"]
#         if (satellite == 'goes-west'):
#             return range(4, 12), range(0, 3) 
#         if (satellite == 'goes-east'):
#             return range(4, 12), range(2, 8) 
#         if (satellite == 'mtg-zero'):
#             return range(4, 12), range(6, 10) 
#         if (satellite == 'msg-zero'):
#             return range(4, 12), range(6, 10) 
#         if (satellite == 'msg-iodc'):
#             return range(4, 12), range(9, 12)
#         if (satellite == 'himawari'):
#             return range(4, 12), range(11, 16) 
#     elif zoom == 5:
#         return range(8, 24), range(0, 32)
#     else:
#         raise ValueError(f"不支持的zoom级别: {zoom}")

# 默认使用zoom=4的范围
BLACKLIST_PATH = 'blacklist.json'
# 定义拼接范围常量
X_RANGE_CONCAT = range(0, 16)
Y_RANGE_CONCAT = range(0, 16)
