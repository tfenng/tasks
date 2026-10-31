import pyproj
from shapely.ops import transform


class CrsTransfer(object):

    def __init__(self, src_epsg=2326, tgt_epsg=4326):
        self.project = pyproj.Transformer.from_proj(
            pyproj.Proj('epsg:{}'.format(src_epsg)),  # source coordinate system
            pyproj.Proj('epsg:{}'.format(tgt_epsg)),
            always_xy=True)

    def trans(self, geo):
        return transform(self.project.transform, geo)





