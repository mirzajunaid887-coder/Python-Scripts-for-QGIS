import os
from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsField, QgsFields, QgsProject,
    QgsSpatialIndex, QgsMessageLog, Qgis, QgsApplication, QgsWkbTypes,
    QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsSymbol
)
from qgis.utils import iface
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QMessageBox, QProgressBar, QInputDialog

# ==============================================================================
# CONFIGURATION
# ==============================================================================
COMPARE_FIELD = "zone_code"
UNIQUE_ID_FIELD = None 

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def get_loaded_polygon_layers():
    """Retrieves all active Vector Polygon layers currently loaded in QGIS."""
    layers = QgsProject.instance().mapLayers().values()
    polygon_layers = {}
    for layer in layers:
        if isinstance(layer, QgsVectorLayer) and layer.geometryType() == QgsWkbTypes.PolygonGeometry:
            polygon_layers[layer.name()] = layer
    return polygon_layers

def create_memory_layer(name, crs_auth_id, qgs_fields, geometry_type="MultiPolygon"):
    """Instantiates an isolated, empty multi-polygon map layer in volatile system RAM."""
    uri = f"{geometry_type}?crs={crs_auth_id}"
    layer = QgsVectorLayer(uri, name, "memory")
    layer.startEditing()
    layer.dataProvider().addAttributes(qgs_fields)
    layer.updateFields()
    layer.commitChanges()
    return layer

def extract_polygon_coords(geom):
    """Fallback safe coordinate parser compatible across multiple QGIS API releases."""
    try:
        if hasattr(geom, 'asPolygonXY'):
            return geom.asPolygonXY()
        elif hasattr(geom, 'asPolygon'):
            return geom.asPolygon()
    except Exception:
        pass
    return None

def ensure_multipolygon(geom):
    """Safely extracts polygon data structures without breaking on API naming variations."""
    if geom.isEmpty():
        return geom
    if geom.isMultipart():
        return geom
        
    flat_type = QgsWkbTypes.flatType(geom.wkbType())
    
    if flat_type == QgsWkbTypes.Polygon:
        coords = extract_polygon_coords(geom)
        if coords:
            return QgsGeometry.fromMultiPolygonXY([coords])
            
    elif flat_type == QgsWkbTypes.GeometryCollection:
        poly_parts = []
        for part in geom.asGeometryCollection():
            if QgsWkbTypes.flatType(part.wkbType()) == QgsWkbTypes.Polygon:
                coords = extract_polygon_coords(part)
                if coords:
                    poly_parts.append(coords)
        if poly_parts:
            return QgsGeometry.fromMultiPolygonXY(poly_parts)
            
    coords = extract_polygon_coords(geom)
    if coords:
        return QgsGeometry.fromMultiPolygonXY([coords])
    return geom

def get_safe_overlap(geom1, geom2):
    """Calculates intersection area after guaranteeing topological validity."""
    v_geom1 = geom1.makeValid()
    v_geom2 = geom2.makeValid()
    if not v_geom1.intersects(v_geom2):
        return 0.0
    inter = v_geom1.intersection(v_geom2)
    if inter.isEmpty():
        return 0.0
    return inter.makeValid().area()

# ==============================================================================
# MAIN PROCESSING WRAPPER
# ==============================================================================

def analyze_zoning_changes_hybrid():
    loaded_layers = get_loaded_polygon_layers()
    if len(loaded_layers) < 2:
        QMessageBox.warning(None, "Insufficient Layers", "Please ensure at least two Polygon layers are loaded in your QGIS project panel.")
        return
        
    layer_names = sorted(list(loaded_layers.keys()))
    
    old_layer_name, ok1 = QInputDialog.getItem(
        None, "Select Reference Layer", "Select the OLD Zoning Layer:", layer_names, 0, False
    )
    if not ok1 or not old_layer_name: return
    
    new_layer_name, ok2 = QInputDialog.getItem(
        None, "Select Updated Layer", "Select the NEW Zoning Layer:", layer_names, 0, False
    )
    if not ok2 or not new_layer_name: return
    
    if old_layer_name == new_layer_name:
        QMessageBox.critical(None, "Selection Error", "The Old Layer and New Layer cannot be the same.")
        return

    old_layer = loaded_layers[old_layer_name]
    new_layer = loaded_layers[new_layer_name]

    # Prompts for EPSG:4326 Layer Units
    tolerance_val, ok3 = QInputDialog.getDouble(
        None, "Set Buffer Shift Tolerance", 
        "Safety zone buffer radius to absorb shift distortions (Degrees):", 
        0.00001, 0.0, 1.0, 6
    )
    if not ok3: return

    sq_ft_cutoff, ok4 = QInputDialog.getDouble(
        None, "Minimum Change Size", 
        "Ignore any exterior change components smaller than (Square Feet):", 
        25.0, 0.0, 100000.0, 2
    )
    if not ok4: return

    area_cutoff_degrees = sq_ft_cutoff * 8.36127e-12

    progress_message_bar = iface.messageBar() if iface else None
    progress_bar = QProgressBar()
    progress_bar.setMaximum(100)
    if progress_message_bar:
        progress_message_bar.pushWidget(progress_bar)
        
    try:
        print("Caching workspace features and generating spatial index mappings...")
        old_features = {f.id(): f for f in old_layer.getFeatures()}
        old_index = QgsSpatialIndex(old_layer.getFeatures())
        new_features = {f.id(): f for f in new_layer.getFeatures()}
        
        # Unique Global Codes tracking
        old_global_codes = set(str(f.attribute(COMPARE_FIELD)) for f in old_features.values())

        output_fields = QgsFields()
        output_fields.append(QgsField(COMPARE_FIELD, QVariant.String, len=100))
        output_fields.append(QgsField("change_type", QVariant.String, len=50))
        output_fields.append(QgsField("Delta_Area", QVariant.Double, prec=12))

        changed_data = []
        total_new_features = len(new_features)

        for step, (new_id, new_feat) in enumerate(new_features.items()):
            if progress_bar:
                progress_bar.setValue(int((step / total_new_features) * 100))
            QgsApplication.processEvents()

            new_geom = new_feat.geometry().makeValid()
            z_code = str(new_feat.attribute(COMPARE_FIELD))
            
            # Find all overlapping old polygons under this new feature's footprint
            candidate_ids = old_index.intersects(new_geom.boundingBox())
            overlapping_old_feats = []
            
            for c_id in candidate_ids:
                o_feat = old_features[c_id]
                if get_safe_overlap(new_geom, o_feat.geometry()) > 0.0:
                    overlapping_old_feats.append(o_feat)
            
            # --- DETECT SPLITS & NEW CODES ---
            # If there are overlapping old zones, check if any of them share the exact same zoning code
            has_locally_matching_code = any(str(o.attribute(COMPARE_FIELD)) == z_code for o in overlapping_old_feats)
            
            if not has_locally_matching_code and len(overlapping_old_feats) > 0:
                # The code doesn't exist locally, but did the code exist elsewhere in the old layer?
                # If yes, it's a structural 'Zone Split' variation. If no, it's a completely brand new classification.
                if z_code in old_global_codes:
                    changed_data.append((new_geom, z_code, 'Zone Split', new_geom.area()))
                else:
                    changed_data.append((new_geom, z_code, 'New Zone Created', new_geom.area()))
                continue
                
            # If it has no overlapping old feature at all, it's a brand new boundary entry entirely
            if len(overlapping_old_feats) == 0:
                if z_code in old_global_codes:
                    changed_data.append((new_geom, z_code, 'Zone Split', new_geom.area()))
                else:
                    changed_data.append((new_geom, z_code, 'New Zone Created', new_geom.area()))
                continue

            # --- DETECT STANDARD GEOMETRY ADJUSTMENTS ---
            # Isolate the standard counterpart piece with the strongest local spatial correlation match
            target_old_feat = None
            max_overlap = 0.0
            for o_feat in overlapping_old_feats:
                if str(o_feat.attribute(COMPARE_FIELD)) == z_code:
                    overlap = get_safe_overlap(new_geom, o_feat.geometry())
                    if overlap > max_overlap:
                        max_overlap = overlap
                        target_old_feat = o_feat
                        
            if target_old_feat is None:
                continue

            old_geom = target_old_feat.geometry().makeValid()
            tolerance_buffer = old_geom.buffer(tolerance_val, 5).makeValid()
            
            if not tolerance_buffer.contains(new_geom):
                diff = new_geom.difference(tolerance_buffer).makeValid()
                if diff.area() > area_cutoff_degrees:
                    changed_data.append((new_geom, z_code, 'Geometry Updated', diff.area()))

        if progress_message_bar:
            progress_message_bar.clearWidgets()

        if not changed_data:
            summary_msg = f"Analysis complete. No significant zoning modifications found using selected parameters."
            QMessageBox.information(None, "Success Summary", summary_msg)
            print(summary_msg)
            return

        crs_auth_id = new_layer.crs().authid()
        result_layer = create_memory_layer("Confirmed_Changes", crs_auth_id, output_fields, "MultiPolygon")
        
        features_to_add = []
        for geom, code_val, change_type_str, delta_area_val in changed_data:
            f = QgsFeature(result_layer.fields())
            f.setGeometry(ensure_multipolygon(geom))
            f.setAttributes([code_val, change_type_str, delta_area_val])
            features_to_add.append(f)
            
        result_layer.startEditing()
        result_layer.dataProvider().addFeatures(features_to_add)
        result_layer.commitChanges()

        # Symbology Rules Setup
        categories = []
        
        # New Zone Created: Red Color Fill
        sym_new = QgsSymbol.defaultSymbol(result_layer.geometryType())
        if sym_new:
            sym_new.setColor(QColor(255, 0, 0, 180))
            categories.append(QgsRendererCategory('New Zone Created', sym_new, 'New Zone Created'))
            
        # Geometry Updated: Orange Color Fill
        sym_upd = QgsSymbol.defaultSymbol(result_layer.geometryType())
        if sym_upd:
            sym_upd.setColor(QColor(255, 165, 0, 180))
            categories.append(QgsRendererCategory('Geometry Updated', sym_upd, 'Geometry Updated'))
            
        # Zone Split: Purple Color Fill
        sym_split = QgsSymbol.defaultSymbol(result_layer.geometryType())
        if sym_split:
            sym_split.setColor(QColor(148, 0, 211, 180)) 
            categories.append(QgsRendererCategory('Zone Split', sym_split, 'Zone Split'))
            
        result_layer.setRenderer(QgsCategorizedSymbolRenderer('change_type', categories))
        QgsProject.instance().addMapLayer(result_layer)
        
        if iface:
            iface.mapCanvas().setExtent(result_layer.extent())
            iface.mapCanvas().refresh()

        summary_msg = f"Done! Core analysis compiled successfully.\nTotal changes categorized: {len(changed_data)}"
        QMessageBox.information(None, "Analysis Complete", summary_msg)
        print(summary_msg)

    except Exception as e:
        if progress_message_bar:
            progress_message_bar.clearWidgets()
        QMessageBox.critical(None, "Critical Execution Error", f"Details: {str(e)}")
        import traceback
        traceback.print_exc()

analyze_zoning_changes_hybrid()
