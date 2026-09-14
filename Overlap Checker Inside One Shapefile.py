def find_overlapping_geometries(layer):
    spatial_index = QgsSpatialIndex(layer.getFeatures())
    overlaps = []
    overlap_points = []
    overlap_threshold = 0.00000009  # Threshold for finding non-snapped vertices
    checked_pairs = set()

    for feature in layer.getFeatures():
        fid = feature.id()
        candidates = spatial_index.intersects(feature.geometry().boundingBox())
        for cid in candidates:
            if cid != fid and (fid, cid) not in checked_pairs and (cid, fid) not in checked_pairs:
                candidate_feature = layer.getFeature(cid)
                if feature.geometry().intersects(candidate_feature.geometry()):
                    intersection = feature.geometry().intersection(candidate_feature.geometry())
                    overlap_area = intersection.area()
                    smaller_area = min(feature.geometry().area(), candidate_feature.geometry().area())
                    if overlap_area / smaller_area > overlap_threshold:
                        overlaps.append(feature)
                        overlaps.append(candidate_feature)

                        # Find overlapping points (vertices that are not snapped)
                        geom1_vertices = [vertex for vertex in feature.geometry().vertices()]
                        geom2_vertices = [vertex for vertex in candidate_feature.geometry().vertices()]
                        
                        # Compare each vertex in geom1 with each vertex in geom2
                        for v1 in geom1_vertices:
                            for v2 in geom2_vertices:
                                if v1.distance(v2) < overlap_threshold:  # Use 'distance' for vertex comparison
                                    overlap_points.append(QgsGeometry.fromPointXY(QgsPointXY(v1)))

                checked_pairs.add((fid, cid))

    # Removing duplicates from overlaps and overlap points
    unique_overlaps = {f.id(): f for f in overlaps}.values()
    unique_overlap_points = {str(p.asPoint()): p for p in overlap_points}.values()

    return list(unique_overlaps), list(unique_overlap_points)

# Function to process layers in the TOC for duplicate geometries
def process_qgis_script(overlap_threshold=0.00000009):
    layers = QgsProject.instance().mapLayers().values()
    for layer in layers:
        if isinstance(layer, QgsVectorLayer) and layer.isValid():
            overlapping_geometries, overlapping_points = find_overlapping_geometries(layer)
            if overlapping_geometries:
                print(f"Found {len(overlapping_geometries)} geometries with significant overlap in layer '{layer.name()}'.")

                # Create Polygon Layer for Overlapping Geometries
                overlap_layer = QgsVectorLayer("Polygon?crs=epsg:4326", f"Overlapping Geometries in {layer.name()}", "memory")
                dp_polygon = overlap_layer.dataProvider()
                dp_polygon.addAttributes(layer.fields())
                overlap_layer.updateFields()

                # Add overlapping polygon features
                for feature in overlapping_geometries:
                    dp_polygon.addFeature(feature)

                QgsProject.instance().addMapLayer(overlap_layer)

                # Create Point Layer for Overlapping Vertices (non-snapped points)
                overlap_points_layer = QgsVectorLayer("Point?crs=epsg:4326", f"Overlap Points in {layer.name()}", "memory")
                dp_points = overlap_points_layer.dataProvider()
                dp_points.addAttributes([QgsField("id", QVariant.Int)])  # Simple ID field for points
                overlap_points_layer.updateFields()

                # Add point features where geometries overlap
                for i, point_geom in enumerate(overlapping_points):
                    point_feature = QgsFeature()
                    point_feature.setGeometry(point_geom)
                    point_feature.setAttributes([i])
                    dp_points.addFeature(point_feature)

                QgsProject.instance().addMapLayer(overlap_points_layer)

# Run the process
process_qgis_script()
