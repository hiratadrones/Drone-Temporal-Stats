"""
Script: rgb_vi_rasters.py
Author: Thiago Hirata dos Anjos

"""

import os
import time
import numpy as np
from osgeo import gdal
from tkinter import Tk, filedialog


# Open a dialog, so the user must select the folder where the orthomosaics is/are and where they'll be saved
def select_ortho_folder_rgb(title="Select the folder containing the orthomosaics"):
    Tk().withdraw()
    return filedialog.askdirectory(title=title)

# Asks the user to select the desired indices
def indices_selection_terminal_rgb(options_rgb):
    print("Available indices:", ", ".join(options_rgb))
    selected_indices_input_rgb = input("Type in the selected indices separated by comma: ")

    if not selected_indices_input_rgb.strip():
        print("No indices selected. The script has terminated.")
        return None

    selected_indices_rgb = [i.strip().upper() for i in selected_indices_input_rgb.split(",") if i.strip().upper() in options_rgb]

    if not selected_indices_rgb:
        print("No valid index informed. The script has terminated.")
        return None

    return selected_indices_rgb

# RGB VI formulas - allows the user to set the minimum valid denominator, to avoid infinity number
def indices_formulas_rgb(index, R, G, B):

    def safe_divide(numerator, denominator):
        return np.where(
            np.abs(denominator) > 1e-6,
            numerator / denominator,
            np.nan
        )

    if index == 'VARI':
        return safe_divide(G - R, G + R - B)

    elif index == 'GLI':
        return safe_divide(2 * G - R - B, 2 * G + R + B)

    elif index == 'GRVI':
        return safe_divide(G - R, G + R)

    elif index == 'GRRI':
        return safe_divide(G, R)

    elif index == 'EXG':
        return 2 * G - R - B

    elif index == 'EXR':
        return 1.4 * R - G

    return None

# Open the RGB orthomosaic bands, calculate the selected indices, set no data value and save the VI orthomsaics
def calculate_indices_rgb(input_path, output_path, selected_indices_rgb):
    dataset = gdal.Open(input_path)
    if dataset is None:
        print(f"Error opening {input_path}")
        return

    R = dataset.GetRasterBand(1).ReadAsArray().astype(np.float32)
    G = dataset.GetRasterBand(2).ReadAsArray().astype(np.float32)
    B = dataset.GetRasterBand(3).ReadAsArray().astype(np.float32)

    indices_array_rgb = indices_formulas_rgb(selected_indices_rgb,R, G, B)

    if indices_array_rgb is None:
        print(f"Index {selected_indices_rgb} not found.")
        return

    driver = gdal.GetDriverByName('GTiff')
    vi_raster = driver.Create(output_path, dataset.RasterXSize, dataset.RasterYSize, 1, gdal.GDT_Float32,
                              ['COMPRESS=LZW'])
    vi_raster.SetGeoTransform(dataset.GetGeoTransform())
    vi_raster.SetProjection(dataset.GetProjection())
    vi_band = vi_raster.GetRasterBand(1)
    vi_band.WriteArray(indices_array_rgb)
    vi_band.SetNoDataValue(-9999)
    vi_raster.FlushCache()
    vi_raster = None

    print(f"Index {selected_indices_rgb} saved in: {output_path}")

# Access the main folder and iterates for each RGB orthomosaic found there. Joins the index name and archive name as the archive final name
def process_orthomosaics_rgb(main_folder_rgb, selected_indices_rgb):
    start_time = time.time()
    processed_orthomosaics = 0
    generated_rasters = 0

    for root, _, archives in os.walk(main_folder_rgb):

        experiment_name = os.path.basename(os.path.dirname(root))

        experiment_start = time.time()

        print(f"\nProcessing {experiment_name}...")

        for archive in archives:

            if archive.lower().endswith("_rgb.tif"):

                processed_orthomosaics += 1

                input_path = os.path.join(root, archive)

                for index in selected_indices_rgb:
                    parent_folder = os.path.dirname(root)

                    index_folder = os.path.join(parent_folder, index)

                    os.makedirs(index_folder, exist_ok=True)

                    output_name = f"{os.path.splitext(archive)[0]}_{index}.tif"

                    output_path = os.path.join(index_folder, output_name) # Aqui define-se onde sai os resultados

                    # 🛑 evita sobrescrever
                    if os.path.exists(output_path):
                        print(f"File already exists, skipping: {output_path}")
                        continue

                    calculate_indices_rgb(input_path, output_path, index)
                    generated_rasters += 1

        experiment_end = time.time()
        print(f"{experiment_name} finished in "f"{experiment_end - experiment_start:.2f} seconds")
        end_time = time.time()

        indices_text = ", ".join(selected_indices_rgb)
        print(f"\nProcessed {processed_orthomosaics} multispectral orthomosaics "f"and generated {generated_rasters} VI rasters "f"({indices_text}) " f"in {end_time - start_time:.2f} seconds.")


# Logical workflow function with the other functions of the script, since folder selecting until processing. This def is also used in main.py
def generate_rasters_rgb():
    main_folder_rgb = select_ortho_folder_rgb("Select the folder containing the orthomosaics:")
    if main_folder_rgb:
        available_indices_rgb = ['VARI', 'GLI', 'GRVI', 'GRRI', 'EXG', 'EXR']
        selected_indices_rgb = indices_selection_terminal_rgb(available_indices_rgb)
        if not selected_indices_rgb:
            print("No indices selected. The script has terminated.")
            return
        print("Processing...")
        process_orthomosaics_rgb(main_folder_rgb, selected_indices_rgb)
    else:
        print("No main folder selected. The script has terminated.")


if __name__ == "__main__":
    generate_rasters_rgb()
