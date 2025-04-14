import platform
import subprocess
import wmi

# # Windows version
# def get_gpus_windows():
#     w = wmi.WMI()
#     gpus = w.Win32_VideoController()
#     return [{'name': gpu.Name, 'driver': gpu.DriverVersion} for gpu in gpus]

# if platform.system() == 'Windows':
#     print(get_gpus_windows())

# def get_glxinfo_gpu():
#     try:
#         output = subprocess.check_output("glxinfo | grep -i 'device\|vendor'", shell=True).decode()
#         return output
#     except Exception as e:
#         return f"Error: {e}"

# if platform.system() == 'Linux':
#     print(get_glxinfo_gpu())

# # Install pyopencl with pip if not already installed: pip install pyopencl
# import pyopencl as cl

# def get_opencl_gpus():
#     platforms = cl.get_platforms()
#     gpu_info = []
#     for platform in platforms:
#         devices = platform.get_devices(device_type=cl.device_type.GPU)
#         for device in devices:
#             gpu_info.append({
#                 'name': device.name,
#                 'vendor': device.vendor,
#                 'version': device.version,
#                 'global_mem_size': device.global_mem_size,
#                 'max_compute_units': device.max_compute_units
#             })
#     return gpu_info

# print(get_opencl_gpus())

from pyadl import *
devices = ADLManager.getInstance().getDevices()
for device in devices:
    print("{0}. {1}".format(device.adapterIndex, device.adapterName))