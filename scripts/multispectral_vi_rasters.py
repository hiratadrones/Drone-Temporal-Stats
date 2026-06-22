"""
Script: multispectral_vi_rasters.py
Author: Thiago Hirata dos Anjos

"""

import os
import time
import numpy as np
from osgeo import gdal
from tkinter import Tk, filedialog

def select_ortho_folder_multispectral(titulo="Select the folder containing the orthomosaics"):
    Tk().withdraw()
    return filedialog.askdirectory(title=titulo)

def indices_selection_terminal_multispectral(options_multispectral):
    print("Available indices:", ", ".join(options_multispectral))
    selected_indices_input_multispectral = input("Type in the selected indices separated by comma: ")

    if not selected_indices_input_multispectral.strip():
        print("No indices selected. The script has terminated.")
        return None

    selected_indices_multispectral = [
        option
        for i in selected_indices_input_multispectral.split(",")
        for option in options_multispectral
        if i.strip().upper() == option.upper()
    ]

    if not selected_indices_multispectral:
        print("No valid index informed. The script has terminated.")
        return None

    return selected_indices_multispectral

def indices_formulas_multispectral(index, G, R, RE, NIR):

    def safe_divide(numerator, denominator):
        return np.where(np.abs(denominator) > 1e-6,
                        numerator / denominator,
                        np.nan)

    if index == 'NDVI':
        return safe_divide(NIR - R, NIR + R)

    elif index == 'GNDVI':
        return safe_divide(NIR - G, NIR + G)

    elif index == 'NDRE':
        return safe_divide(NIR - RE, NIR + RE)

    elif index == 'OSAVI':
        return safe_divide(NIR - R, NIR + R + 0.16) * 1.16

    elif index == 'SAVI':
        return safe_divide(NIR - R, NIR + R + 0.5) * 1.5

    elif index == 'MSAVI':
        return (2 * NIR + 1 - np.sqrt((2 * NIR + 1) ** 2 - 8 * (NIR - R))) / 2

    elif index == 'CIgreen':
        return safe_divide(NIR, G) - 1

    elif index == 'CIrededge':
        return safe_divide(NIR, RE) - 1

    elif index == 'CVI':
        return safe_divide(NIR * R, G ** 2)

    elif index == 'SR':
        return safe_divide(NIR, R)

    elif index == 'SRRE':
        return safe_divide(NIR, RE)

    elif index == 'GRVI':
        return safe_divide(G - R, G + R)

    return None


def calculate_indices_multispectral(input_path, output_path, selected_indices_multispectral):
    dataset = gdal.Open(input_path)
    if dataset is None:
        print(f"Error opening {input_path}")
        return

    G = dataset.GetRasterBand(1).ReadAsArray().astype(np.float32)
    R = dataset.GetRasterBand(2).ReadAsArray().astype(np.float32)
    RE = dataset.GetRasterBand(3).ReadAsArray().astype(np.float32)
    NIR = dataset.GetRasterBand(4).ReadAsArray().astype(np.float32)

    indice_array = indices_formulas_multispectral(
        selected_indices_multispectral,
        G, R, RE, NIR
    )

    if indice_array is None:
        print(f"Index {selected_indices_multispectral} not found.")
        return

    driver = gdal.GetDriverByName('GTiff')
    iv_raster = driver.Create(output_path, dataset.RasterXSize, dataset.RasterYSize, 1, gdal.GDT_Float32,
                              ['COMPRESS=LZW'])
    iv_raster.SetGeoTransform(dataset.GetGeoTransform())
    iv_raster.SetProjection(dataset.GetProjection())
    iv_band = iv_raster.GetRasterBand(1)
    iv_band.WriteArray(indice_array)
    iv_band.SetNoDataValue(-9999)
    iv_raster.FlushCache()
    iv_raster = None

    print(f"Index {selected_indices_multispectral} saved in: {output_path}")

def process_orthomosaics_multispectral(main_folder_multispectral, selected_indices_multispectral):
    start_time = time.time()
    processed_orthomosaics = 0
    generated_rasters = 0

    for root, _, archives in os.walk(main_folder_multispectral):

        experiment_name = os.path.basename(os.path.dirname(root))

        experiment_start = time.time()

        print(f"\nProcessing {experiment_name}...")

        for archive in archives:
            if archive.lower().endswith("_multi.tif"):

                processed_orthomosaics += 1

                input_path = os.path.join(root, archive)

                for index in selected_indices_multispectral:
                    parent_folder = os.path.dirname(root)

                    index_folder = os.path.join(parent_folder, index)

                    os.makedirs(index_folder, exist_ok=True)

                    output_name = f"{os.path.splitext(archive)[0]}_{index}.tif"

                    output_path = os.path.join(index_folder, output_name)  # Aqui define-se onde sai os resultados

                    # 🛑 evita sobrescrever
                    if os.path.exists(output_path):
                        print(f"File already exists, skipping: {output_path}")
                        continue

                    calculate_indices_multispectral(input_path, output_path, index)
                    generated_rasters += 1

        experiment_end = time.time()
        print(f"{experiment_name} finished in "f"{experiment_end - experiment_start:.2f} seconds")
        end_time = time.time()

        indices_text = ", ".join(selected_indices_multispectral)
        print(f"\nProcessed {processed_orthomosaics} RGB orthomosaics "f"and generated {generated_rasters} VI rasters "f"({indices_text}) " f"in {end_time - start_time:.2f} seconds.")

# Executar o script
def generate_multispectral_rasters():
        main_folder_multispectral = select_ortho_folder_multispectral("Selecione a pasta contendo os ortomosaicos")
        if main_folder_multispectral:
            available_indices_multispectral = ['NDVI', 'GNDVI', 'NDRE', 'OSAVI', 'SAVI', 'MSAVI', 'CIgreen', 'CIrededge', 'CVI', 'SR', 'SRRE', 'GRVI']
            selected_indices_multispectral = indices_selection_terminal_multispectral(available_indices_multispectral)
            if not selected_indices_multispectral:
                print("No indices selected. The script has terminated.")
                return
            print("Processing...")
            process_orthomosaics_multispectral(main_folder_multispectral, selected_indices_multispectral)
        else:
            print("No main folder selected. The script has terminated.")

if __name__ == "__main__":
    generate_multispectral_rasters()