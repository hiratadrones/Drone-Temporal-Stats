"""
Script: canopy_cover.py
Author: Thiago Hirata dos Anjos

"""

import numpy as np
import rasterio
from rasterio.mask import mask as rio_mask
import geopandas as gpd
import pandas as pd
import tkinter as tk
from tkinter import filedialog
import os
import glob
import time
from osgeo import gdal, ogr
gdal.DontUseExceptions()


def select_archives():
    root = tk.Tk()
    root.withdraw()

    base_dir = filedialog.askdirectory(title="Select the folder containing the orthomosaics (.tif)")
    if not base_dir:
        raise Exception("No orthomosaics directory selected!")

    # Experiments organization
    experiments = []
    for subdir in next(os.walk(base_dir))[1]:
        exp_path = os.path.join(base_dir, subdir)

        # Search for the files
        tifs = glob.glob(os.path.join(exp_path, "**", "*_RGB.tif"), recursive=True)

        shp_gpkg = (
                glob.glob(os.path.join(exp_path, "**", "*_plots.shp"), recursive=True)
                + glob.glob(os.path.join(exp_path, "**", "*_plots.gpkg"), recursive=True)
        )
        extra = glob.glob(os.path.join(exp_path, "*_extra.xlsx"))

        if not tifs or not shp_gpkg:
            print(f"Skipping {exp_path}: at least one .tif and one *_plot.(shp/gpkg) required")
            continue

        plots_path = shp_gpkg[0]
        optional_sheet_path = extra[0] if extra else None
        output_sheet_path = os.path.join(exp_path, f"{subdir}_canopy_cover.xlsx")

        experiments.append((exp_path, plots_path, optional_sheet_path, output_sheet_path))

    if not experiments:
        raise Exception("No experiment found in the selected folder!")

    return experiments

def raster_binaryzation(input_path, output_path):

    THRESHOLD = 0.0

    with rasterio.open(input_path) as src:

        profile = src.profile
        profile.update(dtype="uint8", count=1, nodata=255)

        with rasterio.open(output_path, "w", **profile) as dst:

            for ji, window in src.block_windows(1): # Impede RAM de estourar

                R = src.read(1, window=window).astype("float32")
                G = src.read(2, window=window).astype("float32")
                B = src.read(3, window=window).astype("float32")

                np.seterr(divide='ignore', invalid='ignore')

                exg = (2*G - R - B)

                binary = (exg > THRESHOLD).astype("uint8")

                valid_mask = src.read_masks(1, window=window) > 0
                binary[~valid_mask] = 255

                dst.write(binary, 1, window=window)

    return output_path

def canopy_cover_table(binary_raster, plots_path):

    gdf = gpd.read_file(plots_path)
    resultados = []

    with rasterio.open(binary_raster) as dataset:

        if gdf.crs != dataset.crs:
            gdf = gdf.to_crs(dataset.crs)

        for idx, row in gdf.iterrows():
            geom = [row.geometry]

            try:
                clip, _ = rio_mask(dataset, geom, crop=True)
                clip = clip[0]

                valid = clip != 255
                total = np.count_nonzero(valid)
                veg = np.count_nonzero((clip == 1) & valid)

                perc = (veg / total) * 100 if total > 0 else np.nan

            except:
                perc = np.nan
                total = 0
                veg = 0

            resultados.append({
                "plot": row["plot"],
                "pixels_total": total,
                "pixels_veg": veg,
                "canopy_%": perc
            })

    return pd.DataFrame(resultados)

def workflow():
    experiments = select_archives()

    for exp_path, plots_path, optional_sheet_path, output_excel in experiments:

        print(f"\nProcessando experimento: {exp_path}")

        start_time = time.time()  # ⬅️ INÍCIO

        tifs = glob.glob(os.path.join(exp_path, "**", "*_RGB.tif"), recursive=True)

        dfs = []

        for tif in tifs:
            binary_path = tif.replace("_RGB.tif", "_binary.tif")

            raster_binaryzation(tif, binary_path)

            df = canopy_cover_table(binary_path, plots_path)
            df["raster"] = os.path.basename(tif)

            dfs.append(df)

        final_df = pd.concat(dfs)
        final_df.to_excel(output_excel, index=False)

        print(f"Saved: {output_excel}")
        end_time = time.time()  # ⬅️ FIM

        print(f"Time of experiment {os.path.basename(exp_path)}: {end_time - start_time:.2f} seconds")

# Only executes if run directly
if __name__ == "__main__":
    workflow()