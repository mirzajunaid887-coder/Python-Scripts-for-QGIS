import random
from qgis.core import (
    QgsProject, QgsRasterLayer, QgsVectorLayer, QgsPointXY, QgsCoordinateTransform, QgsCoordinateReferenceSystem, QgsFillSymbol,
    QgsRendererCategory, QgsCategorizedSymbolRenderer, QgsGeometry, QgsRaster
)
from PyQt5.QtGui import QColor
from collections import Counter
import statistics

def get_layer_by_name(layer_name):
    layers = QgsProject.instance().mapLayersByName(layer_name)
    if not layers:
        raise Exception(f"Layer {layer_name} not found!")
    return layers[0]

def extract_color_from_raster(raster_layer, point):
    identify_result = raster_layer.dataProvider().identify(point, QgsRaster.IdentifyFormatValue)
    if identify_result.isValid():
        return identify_result.results()
    return None

def rgb_to_hex(rgb):
    if None not in rgb:
        return '#{:02x}{:02x}{:02x}'.format(int(rgb[0]), int(rgb[1]), int(rgb[2]))
    return None

def get_dominant_color(colors):
    r_values = [color[0] for color in colors]
    g_values = [color[1] for color in colors]
    b_values = [color[2] for color in colors]
    
    r_dominant = Counter(r_values).most_common(1)[0][0]
    g_dominant = Counter(g_values).most_common(1)[0][0]
    b_dominant = Counter(b_values).most_common(1)[0][0]
    
    return (r_dominant, g_dominant, b_dominant)

def sample_points_within_polygon(polygon, n_points=10):
    bbox = polygon.boundingBox()
    min_x, min_y, max_x, max_y = bbox.xMinimum(), bbox.yMinimum(), bbox.xMaximum(), bbox.yMaximum()
    points = []
    while len(points) < n_points:
        random_x = random.uniform(min_x, max_x)
        random_y = random.uniform(min_y, max_y)
        random_point = QgsPointXY(random_x, random_y)
        if polygon.contains(QgsGeometry.fromPointXY(random_point)):
            points.append(random_point)
    return points

# Names of your raster and vector layers in the TOC
raster_layer_name = "Copy_the_name_of_layer_from_table_of_content_and_paste_here"
vector_layer_name = "Copy_the_name_of_layer_from_table_of_content_and_paste_here"

# Load layers by name
raster_layer = get_layer_by_name(raster_layer_name)
vector_layer = get_layer_by_name(vector_layer_name)

# Log raster layer information
print(f"Raster Layer: {raster_layer.name()}")
print(f"Raster Extent: {raster_layer.extent()}")
print(f"Raster CRS: {raster_layer.crs()}")
print(f"Raster Band Count: {raster_layer.bandCount()}")

# Check if vector and raster CRS match
if vector_layer.crs() != raster_layer.crs():
    print("CRS mismatch detected. Reprojecting vector layer to match raster layer CRS.")
    transform = QgsCoordinateTransform(vector_layer.crs(), raster_layer.crs(), QgsProject.instance())
else:
    transform = None

zone_colors = {}

if raster_layer and vector_layer:
    for feature in vector_layer.getFeatures():
        geom = feature.geometry()
        sample_points = sample_points_within_polygon(geom)

        if transform:
            sample_points = [transform.transform(point) for point in sample_points]

        colors = []
        for point in sample_points:
            if raster_layer.extent().contains(point):
                color = extract_color_from_raster(raster_layer, point)
                if color and 1 in color and 2 in color and 3 in color:
                    rgb = (color[1], color[2], color[3])
                    colors.append(rgb)

        if colors:
            dominant_color = get_dominant_color(colors)
            hex_color = rgb_to_hex(dominant_color)
            if hex_color:
                zone_code = feature['zone_code']
                if zone_code not in zone_colors:
                    zone_colors[zone_code] = hex_color
                print(f"Feature ID {feature.id()}: Dominant RGB={dominant_color}, Hex={hex_color}")
            else:
                print(f"Feature ID {feature.id()}: Invalid RGB values {dominant_color}")
        else:
            print(f"Feature ID {feature.id()}: No valid color found within sampled points.")
else:
    print("Raster or vector layer failed to load.")

# Debugging: Print all detected colors for review
print("Detected colors for each zone:")
for zone_code, hex_color in zone_colors.items():
    print(f"Zone Code: {zone_code}, Hex Color: {hex_color}")

# Update the symbology of the vector layer
categories = []
for zone_code, hex_color in zone_colors.items():
    symbol = QgsFillSymbol.createSimple({'color': hex_color})
    category = QgsRendererCategory(zone_code, symbol, str(zone_code))
    categories.append(category)

renderer = QgsCategorizedSymbolRenderer('zone_code', categories)
vector_layer.setRenderer(renderer)
vector_layer.triggerRepaint()

print("Symbology updated based on raster colors.")
