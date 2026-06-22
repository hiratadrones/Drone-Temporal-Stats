"""
Script: multispectral_vi_stats.py
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


# =========================
# Folder selection
# =========================

def select_archives(mode):
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    root.update()

    base_dir = filedialog.askdirectory(
        title="Select the folder containing the orthomosaics (.tif)"
    )

    if not base_dir:
        raise Exception("No orthomosaics directory selected!")

    mode_name = (
        "whole_plot"
        if mode == "1"
        else "vegetation_only"
    )

    experiments = []

    for exp_name in next(os.walk(base_dir))[1]:

        exp_path = os.path.join(base_dir, exp_name)

        tifs = glob.glob(
            os.path.join(exp_path, "**", "*_MULTI.tif"),
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
            f"{os.path.basename(exp_path)}_{mode_name}_stats.xlsx"
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
# Compute VIs locally
# =========================

def compute_indices_multispectral(G, R, RE, NIR):

    msavi_term = (2 * NIR + 1) ** 2 - 8 * (NIR - R)

    # Avoid sqrt negatives from numeric noise
    msavi_term = np.where(msavi_term < 0, 0, msavi_term)

    indices = {

        'NDVI':
            safe_divide((NIR - R), (NIR + R)),

        'GNDVI':
            safe_divide((NIR - G), (NIR + G)),

        'NDRE':
            safe_divide((NIR - RE), (NIR + RE)),

        'OSAVI':
            safe_divide((NIR - R), (NIR + R + 0.16)) * 1.16,

        'SAVI':
            safe_divide((NIR - R), (NIR + R + 0.5)) * 1.5,

        'MSAVI':
            (
                2 * NIR + 1 -
                np.sqrt(msavi_term)
            ) / 2,

        'CIgreen':
            safe_divide(NIR, G) - 1,

        'CIrededge':
            safe_divide(NIR, RE) - 1,

        'CVI':
            safe_divide(NIR * R, G ** 2),

        'SR':
            safe_divide(NIR, R),

        'SRRE':
            safe_divide(NIR, RE),

        'GRVI':
            safe_divide((G - R), (G + R))
    }

    # Force float32
    for key in indices:
        indices[key] = indices[key].astype(np.float32)

    return indices


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

def multispectral_stats(
    base_dir,
    plots_path,
    optional_sheet_path,
    output_sheet_path,
    mode
):

    start_time_exp = time.time()

    multispectral_orthomosaics = glob.glob(
        os.path.join(base_dir, "**", "*_MULTI.tif"),
        recursive=True
    )

    if not multispectral_orthomosaics:
        raise Exception("No orthomosaics found!")

    print(f"Found {len(multispectral_orthomosaics)} orthomosaics")

    gdf = gpd.read_file(plots_path)

    if optional_sheet_path:
        df_extra = pd.read_excel(optional_sheet_path)
    else:
        df_extra = None

    all_results = []

    # =========================
    # Orthomosaic loop
    # =========================

    for ortho_path in multispectral_orthomosaics:

        ortho_name = os.path.basename(ortho_path).replace(".tif", "")

        print(f"\nProcessing: {ortho_name}")

        dataset = gdal.Open(ortho_path)

        gt = dataset.GetGeoTransform()

        inv_gt = gdal.InvGeoTransform(gt)

        plots_ds = ogr.Open(plots_path)
        layer = plots_ds.GetLayer()

        # =========================
        # Plot loop
        # =========================

        for feature in layer:

            geometry = feature.GetGeometryRef()

            plot = feature.GetField("plot")

            # ---------------------------------
            # Bounding box
            # ---------------------------------

            minx, maxx, miny, maxy = geometry.GetEnvelope()

            px_min, py_min = map(
                int,
                gdal.ApplyGeoTransform(inv_gt, minx, maxy)
            )

            px_max, py_max = map(
                int,
                gdal.ApplyGeoTransform(inv_gt, maxx, miny)
            )

            xsize = px_max - px_min
            ysize = py_max - py_min

            if xsize <= 0 or ysize <= 0:
                continue

            # ---------------------------------
            # Read ONLY plot window
            # ---------------------------------

            G = dataset.GetRasterBand(1).ReadAsArray(
                px_min,
                py_min,
                xsize,
                ysize
            ).astype(np.float32)

            R = dataset.GetRasterBand(2).ReadAsArray(
                px_min,
                py_min,
                xsize,
                ysize
            ).astype(np.float32)

            RE = dataset.GetRasterBand(3).ReadAsArray(
                px_min,
                py_min,
                xsize,
                ysize
            ).astype(np.float32)

            NIR = dataset.GetRasterBand(4).ReadAsArray(
                px_min,
                py_min,
                xsize,
                ysize
            ).astype(np.float32)

            # ---------------------------------
            # Create LOCAL mask raster
            # ---------------------------------

            mem_driver = gdal.GetDriverByName('MEM')

            mask_ds = mem_driver.Create(
                '',
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

            mask_ds.SetGeoTransform(new_gt)
            mask_ds.SetProjection(dataset.GetProjection())

            temp_ds = ogr.GetDriverByName(
                'Memory'
            ).CreateDataSource('')

            temp_layer = temp_ds.CreateLayer(
                'temp',
                srs=layer.GetSpatialRef(),
                geom_type=ogr.wkbPolygon
            )

            temp_layer.CreateFeature(feature.Clone())

            gdal.RasterizeLayer(
                mask_ds,
                [1],
                temp_layer,
                burn_values=[1]
            )

            mask = mask_ds.GetRasterBand(1).ReadAsArray()

            # ---------------------------------
            # NDVI vegetation mask
            # ---------------------------------

            ndvi_raw = safe_divide(
                (NIR - R),
                (NIR + R)
            )

            if mode == "1":
                valid_mask = (mask == 1)

            else:
                valid_mask = (
                    (mask == 1) &
                    (ndvi_raw > 0.3)
                )

            total_pixels = np.sum(valid_mask)

            # ---------------------------------
            # Extract ONLY valid pixels
            # ---------------------------------

            Gv = G[valid_mask]
            Rv = R[valid_mask]
            REv = RE[valid_mask]
            NIRv = NIR[valid_mask]

            # ---------------------------------
            # Compute indices ONLY locally
            # ---------------------------------

            indices = compute_indices_multispectral(
                Gv,
                Rv,
                REv,
                NIRv
            )

            variables = {
                "G": Gv,
                "R": Rv,
                "RE": REv,
                "NIR": NIRv
            }

            variables.update(indices)

            stats = {
                "plot": plot,
                "flight": ortho_name,
                "processing_mode": (
                    "whole_plot"
                    if mode == "1"
                    else "vegetation_only"
                )
            }

            # ---------------------------------
            # Stats loop
            # ---------------------------------

            for key, values in variables.items():

                values = values[np.isfinite(values)]

                s = compute_stats(values)

                stats[f"{key}_mean"] = s["mean"]
                stats[f"{key}_var"] = s["var"]
                stats[f"{key}_std"] = s["std"]
                stats[f"{key}_min"] = s["min"]
                stats[f"{key}_q1"] = s["q1"]
                stats[f"{key}_median"] = s["median"]
                stats[f"{key}_q3"] = s["q3"]
                stats[f"{key}_max"] = s["max"]
                stats[f"{key}_iqr"] = s["iqr"]
                stats[f"{key}_cv"] = s["cv"]
                stats[f"{key}_range"] = s["range"]
                stats[f"{key}_count"] = s["count"]

                stats[f"{key}_valid_pct"] = (
                    (s["count"] / total_pixels) * 100
                    if total_pixels > 0
                    else np.nan
                )

            all_results.append(stats)

            # ---------------------------------
            # Free RAM aggressively
            # ---------------------------------

            del G
            del R
            del RE
            del NIR

            del Gv
            del Rv
            del REv
            del NIRv

            del indices
            del mask
            del ndvi_raw

            mask_ds = None
            temp_ds = None

        layer = None
        plots_ds = None
        dataset = None

    # =========================
    # Final DataFrame
    # =========================

    df_final = pd.DataFrame(all_results)

    if df_extra is not None:
        df_final = df_final.merge(
            df_extra,
            on='plot',
            how='left'
        )

    # =========================
    # Save
    # =========================

    df_final.to_excel(
        output_sheet_path,
        index=False,
        engine='openpyxl'
    )

    print(f"\nSaved: {output_sheet_path}")

    print(
        f"Execution time: "
        f"{time.time() - start_time_exp:.2f} seconds"
    )


# =========================
# Runner
# =========================

def generate_multispectral_stats():

    print("\nChoose processing mode:")
    print("1 = Whole plot (soil + vegetation)")
    print("2 = Vegetation only (NDVI mask)\n")

    mode = input(
        "Type 1 or 2 and press ENTER: "
    ).strip()

    if mode not in ["1", "2"]:
        raise Exception("Invalid option! Choose 1 or 2.")

    if mode == "2":
        print(
            "\nVegetation-only mode selected."
            "\nSoil and vegetation are separated using "
            "NDVI > 0.3 as threshold."
            "\nYou can change this value in the "
            "'ndvi_raw > 0.3' condition inside the script.\n"
        )

    experiments = select_archives(mode)

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
                    "multispectral_stacked",
                    "*_MULTI.tif"
                )
            )
        )

        processed_orthos += ortho_count
        processed_experiments += 1

        multispectral_stats(
            base_dir,
            plots_path,
            optional_sheet_path,
            output_sheet_path,
            mode
        )

    elapsed = time.time() - start_time_total

    total_indices = processed_orthos * len(compute_indices_multispectral(
        np.array([1]),
        np.array([1]),
        np.array([1]),
        np.array([1])
    ))

    print("\n==============================")
    print("PROCESSING FINISHED")
    print("==============================")
    print(f"Experiments processed: {processed_experiments}")
    print(f"Orthomosaics processed: {processed_orthos}")
    print(f"Indices generated: {total_indices}")
    print(f"Total execution time: {elapsed:.2f} seconds")
    print("==============================")

# =========================
# Main
# =========================

if __name__ == "__main__":
    generate_multispectral_stats()