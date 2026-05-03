"""Swap the M1 ROM in the built jukebox with patched v1.7"""
import zipfile, os, sys

m1_path = "/home/bruno/Downloads/neo-soccer/soccerfury_patched.m1"
m1_data = open(m1_path, "rb").read()
print(f"M1 ROM: {len(m1_data)} bytes ({len(m1_data)//1024} KB)")

zip_path = "jukebox.zip"
zin = zipfile.ZipFile(zip_path, "r")
zout = zipfile.ZipFile("jukebox_v17.zip", "w")

for name in zin.namelist():
    if name.endswith("-m1.m1"):
        zout.writestr(name, m1_data)
        print(f"  Replaced {name} with patched v1.7")
    else:
        zout.writestr(name, zin.read(name))

zin.close()
zout.close()
os.rename("jukebox_v17.zip", zip_path)

# Also update roms dir
roms_m1 = "roms/jukebox/999-m1.m1"
with open(roms_m1, "wb") as f:
    f.write(m1_data)
print(f"  Updated {roms_m1}")
