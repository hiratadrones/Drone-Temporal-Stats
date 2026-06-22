"""
Script: height_stats.py
Author: Thiago Hirata dos Anjos

"""

from osgeo import gdal, ogr
gdal.DontUseExceptions()
import pandas as pd
import numpy as np
import time
import geopandas as gpd
import glob
import os
import tkinter as tk
from tkinter import filedialog
import rasterio

# Open dialogs, so the user must select the folder where the orthomosaics is/are and where they'll be saved;
# the .shp/.gpkg plots archive; an optional .xlsx sheet to join to the final table; and the output path
def select_archives():
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    root.update()

    base_dir = filedialog.askdirectory(title="Select the folder containing the orthomosaics (.tif)")
    if not base_dir:
        raise Exception("No orthomosaics directory selected!")

   # Experiments organization
    experiments = []
    for exp_name in next(os.walk(base_dir))[1]:

        exp_path = os.path.join(base_dir, exp_name)

        tifs = glob.glob(
            os.path.join(exp_path, "**", "*_DSM.tif"),
            recursive=True
        )

        shp_gpkg = (
                glob.glob(
                    os.path.join(exp_path, "**", "*_plots.shp"),
                    recursive=True
                ) +
                glob.glob(
                    os.path.join(exp_path, "**", "*_plots.gpkg"),
                    recursive=True
                )
        )
        extra = glob.glob(os.path.join(exp_path, "*_extra.xlsx"))

        if not tifs or not shp_gpkg:
            print(f"Skipping {exp_path}: missing tif or plots")
            continue

        plots_path = shp_gpkg[0]

        optional_sheet_path = (
            extra[0]
            if extra
            else None
        )

        output_sheet_path = os.path.join(
            exp_path,
            f"{os.path.basename(exp_path)}_stats.xlsx"
        )

        experiments.append((
            exp_path,
            plots_path,
            optional_sheet_path,
            output_sheet_path
        ))

    if not experiments:
        raise Exception("No experiments found!")

    return experiments

# =========================
# Safe divide
# =========================

def safe_divide(numerator, denominator):
    return np.where(
        np.abs(denominator) > 1e-6,
        numerator / denominator,
        np.nan
    ).astype(np.float32)



# =========================
# Statistics
# =========================

def compute_stats(values):

    if values.size == 0:
        return {
            "mean": np.nan,
            "var": np.nan,
            "std": np.nan,
            "min": np.nan,
            "q1": np.nan,
            "median": np.nan,
            "q3": np.nan,
            "max": np.nan,
            "iqr": np.nan,
            "cv": np.nan,
            "range": np.nan,
            "count": 0
        }

    mean = np.mean(values)
    std = np.std(values)

    q1 = np.percentile(values, 25)
    q3 = np.percentile(values, 75)

    return {
        "mean": mean,
        "var": np.var(values),
        "std": std,
        "min": np.min(values),
        "q1": q1,
        "median": np.median(values),
        "q3": q3,
        "max": np.max(values),
        "iqr": q3 - q1,
        "cv": std / mean if mean != 0 else np.nan,
        "range": np.max(values) - np.min(values),
        "count": values.size
    }
# =========================
# Main processing
# =========================

def canopy_height_stats(
        base_dir,
        plots_path,
        optional_sheet_path,
        output_sheet_path
):

    start_time_exp = time.time()

    dsm_files = glob.glob(
        os.path.join(base_dir, "**", "*_DSM.tif"),
        recursive=True
    )

    if len(dsm_files) < 2:
        raise Exception(
            "At least two DSMs are required "
            "(ground + one flight)."
        )

    dsm_files.sort()

    print(f"Found {len(dsm_files)} DSMs")

    ground_path = dsm_files[0]
    ground_name = os.path.basename(ground_path)

    print(f"Ground DSM: {ground_name}")

    ground_ds = gdal.Open(ground_path)

    raster_srs = ogr.osr.SpatialReference()
    raster_srs.ImportFromWkt(
        ground_ds.GetProjection()
    )

    gt = ground_ds.GetGeoTransform()
    inv_gt = gdal.InvGeoTransform(gt)

    plots_ds = ogr.Open(plots_path)
    layer = plots_ds.GetLayer()

    plot_srs = layer.GetSpatialRef()

    coord_transform = None

    if not plot_srs.IsSame(raster_srs):

        coord_transform = ogr.osr.CoordinateTransformation(
            plot_srs,
            raster_srs
        )

    gdf = gpd.read_file(plots_path)

    if optional_sheet_path:
        df_extra = pd.read_excel(
            optional_sheet_path
        )
    else:
        df_extra = None

    all_results = []

    # ==========================
    # flight loop
    # ==========================

    for dsm_path in dsm_files[1:]:

        dsm_name = os.path.basename(
            dsm_path
        ).replace(".tif", "")

        print(f"\nProcessing {dsm_name}")

        current_ds = gdal.Open(dsm_path)

        layer.ResetReading()

        # ==========================
        # plot loop
        # ==========================

        for feature in layer:

            geometry = (
                feature
                .GetGeometryRef()
                .Clone()
            )

            if coord_transform is not None:
                geometry.Transform(
                    coord_transform
                )

            plot = feature.GetField(
                "plot"
            )

            minx, maxx, miny, maxy = (
                geometry.GetEnvelope()
            )

            px_min, py_min = map(
                int,
                gdal.ApplyGeoTransform(
                    inv_gt,
                    minx,
                    maxy
                )
            )

            px_max, py_max = map(
                int,
                gdal.ApplyGeoTransform(
                    inv_gt,
                    maxx,
                    miny
                )
            )

            xsize = px_max - px_min
            ysize = py_max - py_min

            if (
                xsize <= 0
                or
                ysize <= 0
            ):
                continue

            ground = ground_ds.GetRasterBand(1).ReadAsArray(
                px_min,
                py_min,
                xsize,
                ysize
            )

            current = current_ds.GetRasterBand(1).ReadAsArray(
                px_min,
                py_min,
                xsize,
                ysize
            )

            if ground is None or current is None:
                print(
                    f"Skipping plot {plot}: "
                    "window outside raster"
                )
                continue

            ground = ground.astype(np.float32)
            current = current.astype(np.float32)

            # ==========================
            # local mask
            # ==========================

            mem_driver = gdal.GetDriverByName(
                "MEM"
            )

            mask_ds = mem_driver.Create(
                "",
                xsize,
                ysize,
                1,
                gdal.GDT_Byte
            )

            new_gt = (
                gt[0] + px_min * gt[1],
                gt[1],
                0,
                gt[3] + py_min * gt[5],
                0,
                gt[5]
            )

            mask_ds.SetGeoTransform(
                new_gt
            )

            mask_ds.SetProjection(
                ground_ds.GetProjection()
            )

            temp_ds = (
                ogr
                .GetDriverByName("Memory")
                .CreateDataSource("")
            )

            temp_layer = temp_ds.CreateLayer(
                "temp",
                srs=layer.GetSpatialRef(),
                geom_type=ogr.wkbPolygon
            )

            temp_layer.CreateFeature(
                feature.Clone()
            )

            gdal.RasterizeLayer(
                mask_ds,
                [1],
                temp_layer,
                burn_values=[1]
            )

            mask = (
                mask_ds
                .GetRasterBand(1)
                .ReadAsArray()
            )

            # ==========================
            # canopy height
            # ==========================

            height = current - ground

            valid_mask = (
                    (mask == 1)
                    &
                    np.isfinite(height)
                    &
                    (height >= 0)
            )

            height_values = (
                height[valid_mask]
            )

            s = compute_stats(
                height_values
            )

            stats = {

                "plot": plot,

                "flight": dsm_name,

                "height_mean":
                    s["mean"],

                "height_var":
                    s["var"],

                "height_std":
                    s["std"],

                "height_min":
                    s["min"],

                "height_q1":
                    s["q1"],

                "height_median":
                    s["median"],

                "height_q3":
                    s["q3"],

                "height_max":
                    s["max"],

                "height_iqr":
                    s["iqr"],

                "height_cv":
                    s["cv"],

                "height_range":
                    s["range"],

                "height_count":
                    s["count"]
            }

            all_results.append(
                stats
            )

            del ground
            del current
            del height
            del height_values
            del mask

            mask_ds = None
            temp_ds = None

        current_ds = None

    plots_ds = None
    ground_ds = None

    df_final = pd.DataFrame(
        all_results
    )

    if df_extra is not None:

        df_final = df_final.merge(
            df_extra,
            on="plot",
            how="left"
        )

    df_final.to_excel(
        output_sheet_path,
        index=False,
        engine="openpyxl"
    )

    print(
        f"\nSaved: {output_sheet_path}"
    )

    print(
        f"Execution time: "
        f"{time.time()-start_time_exp:.2f}s"
    )

def generate_height_stats():

    experiments = select_archives()

    start_time_total = time.time()

    processed_orthos = 0
    processed_experiments = 0

    for (
            base_dir,
            plots_path,
            optional_sheet_path,
            output_sheet_path
    ) in experiments:

        if os.path.exists(output_sheet_path):
            print(
                f"Skipping "
                f"{os.path.basename(base_dir)}"
                f"'{os.path.basename(output_sheet_path)}' already exists"
            )
            continue

        print(
            f"\n--- Processing "
            f"{os.path.basename(base_dir)} ---"
        )

        ortho_count = len(
            glob.glob(
                os.path.join(
                    base_dir,
                    "DSM",
                    "*_DSM.tif"
                )
            )
        )

        processed_orthos += ortho_count
        processed_experiments += 1

    elapsed = time.time() - start_time_total

    canopy_height_stats(
        base_dir,
        plots_path,
        optional_sheet_path,
        output_sheet_path
    )

    print("\n==============================")
    print("PROCESSING FINISHED")
    print("==============================")
    print(f"Experiments processed: {processed_experiments}")
    print(f"DSMs processed: {processed_orthos}")
    print(f"Total execution time: {elapsed:.2f} seconds")
    print("==============================")


# =========================
# Main
# =========================

if __name__ == "__main__":
    generate_height_stats()

