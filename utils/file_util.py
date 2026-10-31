# -*- coding: utf-8 -*-
import codecs
import json
import os

from utils import log


def file2dict(file_path):
    with open(file_path, "r") as file:
        return json.load(file)


def dict2file(the_dict, path="output.json"):
    with codecs.open(path, "w", encoding="utf8") as target_file:
        target_file.write(json.dumps(the_dict, ensure_ascii=False, indent=4))


def count_files_in(dir):
    return len(list_files_in(dir))


def list_files_in(dir, exts=('.tif', '.tiff', '.geotif', '.geotiff', '.jpg')):
    all_files = os.listdir(dir)
    # path, dirs, files = next(os.walk(dir))
    files = [file for file in all_files if file.endswith(exts)]
    files.sort()
    return files


def list_dirs_in(dir):
    path, dirs, files = next(os.walk(dir))
    return dirs


def is_required_exts(fname, exts=['.tif', '.tiff', '.geotiff', '.jpg']):
    log().info(os.path.splitext(fname))
    ext = os.path.splitext(fname)[1]
    return True if ext in exts else False


if __name__ == '__main__':
    files = list_files_in('/xmap/demo13')
    print(files)
    # print(is_required_exts('/home/tony/data/02.tif'))
