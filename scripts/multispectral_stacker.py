"""
Script: multispectral_stacker.py
Author: Thiago Hirata dos Anjos

"""

import os
import tkinter as tk
from tkinter import filedialog
import rasterio
import numpy as np
import time

def select_drone_gui():
    choice = {"value": None}

    def select_m3m():
        choice["value"] = ["G", "R", "RE", "NIR"]
        window.destroy()

    def select_p4m():
        choice["value"] = ["B", "G", "R", "RE", "NIR"]
        window.destroy()

    window = tk.Tk()
    window.title("Drone model selection")
    window.geometry("300x150")
    window.resizable(False, False)

    label = tk.Label(window, text="Select your drone:", font=("Arial", 12))
    label.pack(pady=10)

    btn_mavic = tk.Button(window, text="DJI Mavic 3M", width=20, height=2, command=select_m3m)
    btn_mavic.pack(pady=5)

    btn_phantom = tk.Button(window, text="DJI Phantom 4M", width=20, height=2, command=select_p4m)
    btn_phantom.pack(pady=5)

    window.mainloop()
    return choice["value"]

def select_folder(title):
    root = tk.Tk()
    root.withdraw()
    return filedialog.askdirectory(title=title)


expected_bands = select_drone_gui()
if not expected_bands:
    print("No drone selected. Finishing process.")
    exit()
print(f"Drone selected. Expected bands: {expected_bands}")


main_folder = select_folder("Select the root folder with the subfolder of the flights")
if not main_folder:
    print("Cancelled folder.")
    exit()

# Create the folder to save stacked orthos
output_root = os.path.join(main_folder, "multispectral_stacked")
os.makedirs(output_root, exist_ok=True)

# Mark the start time
start_time = time.time()

# Search for the bands in each subfolder
for subfolder_path, dirs, files in os.walk(main_folder):

    tif_archives = files

    if len(tif_archives) == 0:
        continue

    subfolder = os.path.basename(subfolder_path)

    print(f"Processing subfolder: {subfolder}")

    tif_archives = os.listdir(subfolder_path)
    found_bands = {b: None for b in expected_bands}

    for arq in tif_archives:
        if arq.lower().endswith(".tif"):
            for b in expected_bands:
                if arq.upper().endswith(f"_{b}.TIF") or arq.upper().endswith(f"_{b}.tif"):
                    found_bands[b] = os.path.join(subfolder_path, arq)

    # Checks if all bands were found
    if None in found_bands.values():
        missing_bands = [b for b, path in found_bands.items() if path is None]
        print(f"Subfolder '{subfolder}' ignored. Missing bands: {missing_bands}")
        continue

    # Read and stack bands
    perfil = None

    for b in expected_bands:
        with rasterio.open(found_bands[b]) as src:
            if perfil is None:
                perfil = src.profile.copy()
                perfil.update(
                    count=len(expected_bands),
                    compress='lzw',
                    tiled=False
                )

    # Creates output names
    base_name = os.path.basename(found_bands[expected_bands[0]])
    base_name = base_name.rsplit("_", 1)[0]  # remove the band suffix
    output_name = f"{base_name}_MULTI.tif"
    output_path = os.path.join(output_root, output_name)

    # Check if multi already exists
    if os.path.exists(output_path):
        print(f" Skipping (already exists): {output_name}")
        continue

    # Saves orthomosaic
    with rasterio.open(output_path, "w", **perfil) as dst:

        for i, b in enumerate(expected_bands, start=1):
            with rasterio.open(found_bands[b]) as src:
                dst.write(src.read(1), i)

    print(f"Mosaic created: {output_path}")
    # Total time of execution
    print(f" {output_path} execution time: {time.time() - start_time:.2f} seconds")

print("Process finished!")

# Total time of execution
print(f"Execution time: {time.time() - start_time:.2f} seconds")
