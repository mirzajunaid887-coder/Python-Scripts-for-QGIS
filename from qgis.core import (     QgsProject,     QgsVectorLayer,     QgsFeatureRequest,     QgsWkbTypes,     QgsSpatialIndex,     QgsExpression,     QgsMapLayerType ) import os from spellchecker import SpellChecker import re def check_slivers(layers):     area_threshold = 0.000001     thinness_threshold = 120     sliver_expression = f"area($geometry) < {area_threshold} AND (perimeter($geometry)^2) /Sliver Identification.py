from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeatureRequest,
    QgsWkbTypes,
    QgsSpatialIndex,
    QgsExpression,
    QgsMapLayerType
)
import os
from spellchecker import SpellChecker
import re
def check_slivers(layers):
    area_threshold = 0.000001
    thinness_threshold = 120
    sliver_expression = f"area($geometry) < {area_threshold} AND (perimeter($geometry)^2) / area($geometry) > {thinness_threshold}"
    
    for layer in layers:
        if isinstance(layer, QgsVectorLayer) and layer.isValid():
            print(f"\nChecking for slivers in layer '{layer.name()}'...")
            # Step 1: Find potential slivers
            layer.startEditing()
            request = QgsFeatureRequest().setFilterExpression(sliver_expression)
            potential_sliver_ids = [f.id() for f in layer.getFeatures(request)]
            print(f"Layer '{layer.name()}': Found {len(potential_sliver_ids)} potential slivers based on expression.")

            # Step 2: Filter for true slivers (overlapping larger polygons)
            true_sliver_ids = []
            sliver_features = []
            for sliver_id in potential_sliver_ids:
                sliver_feature = layer.getFeature(sliver_id)
                sliver_geom = sliver_feature.geometry()
                for main_feature in layer.getFeatures():
                    if main_feature.id() != sliver_id:
                        main_geom = main_feature.geometry()
                        if (main_geom.area() > area_threshold * 10 and 
                            main_geom.intersects(sliver_geom) and 
                            sliver_geom.area() < main_geom.area() * 0.01):  # Sliver is much smaller
                            true_sliver_ids.append(sliver_id)
                            sliver_features.append(sliver_feature)
                            print(f"  - Sliver ID {sliver_id} overlaps main polygon ID {main_feature.id()}")
                            break
            
            # Step 3: Report and select true slivers in original layer
            if true_sliver_ids:
                print(f"WARNING: Layer '{layer.name()}' contains {len(true_sliver_ids)} slivers!")
                layer.selectByIds(true_sliver_ids)
                print(f"Slivers selected in layer '{layer.name()}' for review (IDs: {true_sliver_ids}).")
                
                # Step 4: Create an extra layer for slivers
                sliver_layer = QgsVectorLayer(f"Polygon?crs={layer.crs().authid()}", f"Slivers_{layer.name()}", "memory")
                dp = sliver_layer.dataProvider()
                dp.addAttributes(layer.fields())
                sliver_layer.updateFields()
                for feature in sliver_features:
                    dp.addFeature(feature)
                QgsProject.instance().addMapLayer(sliver_layer)
                print(f"Created extra layer 'Slivers_{layer.name()}' with {len(sliver_features)} slivers.")
            else:
                print(f"Layer '{layer.name()}': No slivers found after overlap check.")
            layer.commitChanges()

layers = QgsProject.instance().mapLayers().values()
check_slivers(layers)
