#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打包平台可上传的 zip(manifest.json + 入口脚本 放在包根)。

平台要求: zip 根目录必须有 manifest.json, 入口脚本与 manifest 同级。
回填脚本 dajia_feature_extract_backfill.py 是内网手动工具, 不进平台包。

用法:
  python3 build_zip.py [版本号]      # 默认 v1.0.0, 产物输出到当前目录
"""
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))


def build(version: str = "v1.0.0") -> str:
    out = os.path.join(HERE, f"dajia_feature_extract_{version}.zip")
    files = {
        os.path.join(HERE, "config", "manifest.json"): "manifest.json",
        os.path.join(HERE, "scripts", "dajia_feature_extract.py"): "dajia_feature_extract.py",
    }
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for src, arc in files.items():
            z.write(src, arc)
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert "manifest.json" in names, "manifest.json 必须在包根"
    print(f"已生成: {out}")
    print(f"包内文件: {names}")
    return out


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "v1.0.0")
