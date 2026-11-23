#!/usr/bin/env python3
"""Compare ACTUAL Qt icon pixels with an immutable, run-attributed golden.

Users locked Calendar, Photos and Music. Their exact 54x54 RGBA8 pixels
from a successful real Qt build must never change. The five production
goldens are added only after successful native Qt output is inspected.
No synthesized, rescaled, or model-generated images are accepted here.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

try:
    from .check_classic_icon_frame_diff import CENTERS, APPS, ComparisonError, _read_png
except ImportError:
    from check_classic_icon_frame_diff import CENTERS, APPS, ComparisonError, _read_png

FROZEN=("calendar","photos","music")
TARGET=("browser","mail","files","terminal","settings")


def extract_hashes(path:Path,size:str):
    width,height,rgba,_=_read_png(path,size)
    result={}
    for name,(cx,cy) in zip(APPS,CENTERS[size]["desktop"]):
        region=bytearray()
        for y in range(cy-27,cy+27):
            region.extend(rgba[4*(y*width+cx-27):4*(y*width+cx+27)])
        if len(region)!=54*54*4:
            raise ComparisonError("invalid actual Qt pixel crop size")
        result[name.lower()]=hashlib.sha256(region).hexdigest()
    return result


def validate(golden_path:Path,screens_dir:Path,
             image_prefix="dock-five-center-",require_complete=False):
    gold=json.loads(golden_path.read_text(encoding="utf-8"))
    if gold.get("schema_version")!=1 or gold.get("frozen_names")!=list(FROZEN):
        raise ComparisonError("untrusted icon golden schema or freeze set")
    protected=gold["fixed_resolution_hashes"]
    five=gold.get("five_production_goldens",{})
    if set(protected)!=set(CENTERS):
        raise ComparisonError("golden resolutions incomplete")
    if require_complete and set(five)!=set(CENTERS):
        raise ComparisonError("five production goldens not yet recorded from final Qt")
    for size in CENTERS:
        expected=protected[size]
        if set(expected)!=set(FROZEN):
            raise ComparisonError("frozen icon golden count changed")
        actual=extract_hashes(screens_dir/(image_prefix+size+".png"),size)
        for name in FROZEN:
            if actual[name]!=expected[name]:
                raise ComparisonError(
                    f"golden pixel mismatch: FROZEN {name} at {size}")
        if size in five:
            if set(five[size])!=set(TARGET):
                raise ComparisonError("five production golden inventory mismatch")
            for name in TARGET:
                if actual[name]!=five[size][name]:
                    raise ComparisonError(
                        f"golden pixel mismatch: production {name} at {size}")
    return {
        "source_run":gold["source_run_url"],
        "frozen_icon_names":FROZEN,
        "verified_resolutions":tuple(CENTERS),
        "frozen_icon_54px_pixels_unchanged":True,
        "five_production_golden_available":set(five)==set(CENTERS),
        "owner_appearance_approval_inferred":False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--golden",type=Path,
                   default=Path("docs/CLASSIC_FIVE_DOCK_GOLDEN.json"))
    p.add_argument("--screens-dir",type=Path,required=True)
    p.add_argument("--image-prefix",default="dock-five-center-")
    p.add_argument("--require-complete",action="store_true")
    p.add_argument("--output",type=Path)
    args=p.parse_args(argv)
    try:
        report=validate(args.golden,args.screens_dir,
                        args.image_prefix,args.require_complete)
        serialized=json.dumps(report,indent=2)+"\n"
        if args.output:
            args.output.write_text(serialized,encoding="utf-8")
        else:
            print(serialized,end="")
        print("CANOPY_FIVE_QT_GOLDEN_PASS: Calendar/Photos/Music pixel-perfect")
        return 0
    except (OSError,KeyError,ValueError,TypeError,ComparisonError) as exc:
        print("CANOPY_FIVE_QT_GOLDEN_FAIL:",exc,file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
