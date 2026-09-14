import requests
from qgis.core import *
from qgis.utils import *
from qgis.PyQt.QtGui import *
import processing
import re
import os
from console.console import _console
import inspect
zone_code_old = ''
zone_name_old = ''
print(os.path.abspath(inspect.getfile(inspect.currentframe())))
file_path = os.path.abspath(inspect.getfile(inspect.currentframe()))
layer = iface.activeLayer()
errors = []

def print_line(text):
    print(' ' * 5 + '=' * len(text))
    print(' ' * 5 + text)
    print(' ' * 5 + '=' * len(text))

def print_space(text):
    print(' ' * 5 + text)

def add_error(name, status):
    errors.append({"Name": name, "Status": status}) 

def print_errors(error_list, status):
    if status == "Successful":
        print_line(f"{status} Operations \U0001f642 \U0001f600")
    else:
        print_line(f"{status} Operations \U0001f621 \U0001f620")
    for i, error in enumerate(error_list, start=1):
        if error["Status"] == status:
            print_space(f"{error['Name']}\n")

def checkCRS(layer):
    if layer.crs() != QgsCoordinateReferenceSystem(f'EPSG:{4326}'): # Check if the CRS transformation is required
        parameters = {'INPUT': layer,'TARGET_CRS': QgsCoordinateReferenceSystem(f'EPSG:{4326}'),'OUTPUT': 'memory:'}  # Define the new CRS using the EPSG code and other parameters
        result = processing.run("native:reprojectlayer", parameters, feedback=QgsProcessingFeedback()) # Reproject the layer using the "native:reprojectlayer" algorithm
        if result and result['OUTPUT']:
            QgsProject.instance().addMapLayer(result['OUTPUT']).setName(layer.name() + "") # Add the reprojected layer to the map
            QgsProject.instance().removeMapLayer(layer)
            QgsProject.instance().setCrs(QgsCoordinateReferenceSystem('EPSG:4326'))
            iface.mapCanvas().refresh()
            iface.zoomToActiveLayer()
            add_error(f"'CRS' Changed to 'EPSG:4326'", "Successful")
        else:
            add_error(f"'Fix CRS First!' Change it to 'EPSG:4326'.", "Unsuccessful")
    else:
        add_error(f"Layer is Already in the Desired 'CRS: (EPSG:4326)'.", "Successful")

checkCRS(iface.activeLayer())
print_errors(errors,"Successful")
print_errors(errors,"Unsuccessful")

