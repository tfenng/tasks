import os
import tempfile
import zipfile
from io import BytesIO

import shapefile


def loadZipInMem(source_dir):
    """
    通过BytesIO打包文件成zip, 打包成功后并没有生成实际的zip文件而是以BytesIO的形式返回
    :param source_dir: 需要打包的绝对路径
    :return: BytesIO形式的文件
    """
    memory_file = BytesIO()
    with zipfile.ZipFile(memory_file, 'w') as zf:
        pre_len = len(os.path.dirname(source_dir))
        for parent, dirnames, filenames in os.walk(source_dir):
            for filename in filenames:
                pathfile = os.path.join(parent, filename)
                arcname = pathfile[pre_len:].strip(os.path.sep)  # 相对路径
                zf.write(pathfile, arcname)
    memory_file.seek(0)
    return memory_file


def create_zip_in_mem(shape_type_list, shapesname, epsg) -> bytes:
    with tempfile.TemporaryDirectory() as tmpdirname:
        with shapefile.Writer(target=f"{tmpdirname}/{shapesname}",
                              shapeType=shapefile.POLYGON, autoBalance=1) as writeShp:
            writeShp.field('type', 'C', 50, 0)
            for _shape_type in shape_type_list:
                writeShp.shape(_shape_type[0])
                writeShp.record(_shape_type[1])
        with open(f"{tmpdirname}/{shapesname}.prj", "w") as fprj:
            import pyproj
            from pyproj.enums import WktVersion
            fprj.write(pyproj.CRS.from_epsg(epsg).to_wkt(version=WktVersion.WKT1_ESRI))
        memory_file = BytesIO()
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED, allowZip64=False) as zf:
            pre_len = len(tmpdirname)
            for parent, dirnames, filenames in os.walk(tmpdirname):
                for filename in filenames:
                    pathfile = os.path.join(parent, filename)
                    arcname = pathfile[pre_len:].strip(os.path.sep)  # 相对路径
                    zf.write(pathfile, arcname)
        return memory_file.getvalue()


def create_empty_in_mem() -> bytes:
    memory_file = BytesIO()
    with zipfile.ZipFile(memory_file, 'w') as zipf:
        pass
    memory_file.seek(0)
    return memory_file.getvalue()
