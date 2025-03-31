# const.py
# 定义下载范围常量
def get_ranges_for_zoom(zoom: int, satellite: str):
    """根据zoom级别计算X和Y的范围"""
    if zoom == 4:
        # ["goes-east", "goes-west", "himawari", "msg-iodc", "msg-zero", "mtg-zero"]
        if (satellite == 'goes-west'):
            return range(4, 12), range(0, 3) 
        if (satellite == 'goes-east'):
            return range(4, 12), range(2, 8) 
        if (satellite == 'mtg-zero'):
            return range(4, 12), range(6, 10) 
        if (satellite == 'msg-zero'):
            return range(4, 12), range(6, 10) 
        if (satellite == 'msg-iodc'):
            return range(4, 12), range(9, 12)
        if (satellite == 'himawari'):
            return range(4, 12), range(11, 16) 
    elif zoom == 5:
        return range(8, 24), range(0, 32)
    else:
        raise ValueError(f"不支持的zoom级别: {zoom}")

# 默认使用zoom=4的范围
BLACKLIST_PATH = 'blacklist.json'
# 定义拼接范围常量
X_RANGE_CONCAT = range(0, 16)
Y_RANGE_CONCAT = range(0, 16)
