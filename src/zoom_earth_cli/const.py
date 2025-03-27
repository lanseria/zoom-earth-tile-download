# const.py
# 定义下载范围常量
def get_ranges_for_zoom(zoom: int):
    """根据zoom级别计算X和Y的范围"""
    if zoom == 4:
        return range(4, 12), range(0, 16)
    elif zoom == 5:
        return range(8, 24), range(0, 32)
    else:
        raise ValueError(f"不支持的zoom级别: {zoom}")

# 默认使用zoom=4的范围
X_RANGE, Y_RANGE = get_ranges_for_zoom(4)
BLACKLIST_PATH = 'blacklist.json'
# 定义拼接范围常量
X_RANGE_CONCAT = range(0, 16)
Y_RANGE_CONCAT = range(0, 16)
