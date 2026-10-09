
import os
from qgis.core import (
    QgsVectorLayer,
    QgsVectorFileWriter,
    QgsProject,
    QgsField,
    QgsFeature,
    QgsWkbTypes
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QInputDialog, QMessageBox

# ==========================================================
# SET YOUR INPUT AND OUTPUT FOLDERS HERE
# ==========================================================
input_folder = r"Input_Folder"
output_folder = r"Output_Folder"
# ==========================================================


def ask_choice(title, label, options, default_index=0):
    """Display a selection dialog."""
    choice, accepted = QInputDialog.getItem(
        None, title, label, options, default_index, False
    )
    return choice if accepted else None


def find_field(layer, field_name):
    """Find a field without case sensitivity."""
    for field in layer.fields():
        if field.name().lower() == field_name.lower():
            return field.name()
    return None


def main():

    # ------------------------------------------------------
    # STEP 1: ASK WHICH INPUT FILES TO PROCESS
    # ------------------------------------------------------
    input_options = [
        "Shapefile only",
        "GeoJSON only",
        "Both Shapefile and GeoJSON"
    ]

    input_choice = ask_choice(
        "Input Selection",
        "Which input files do you want to process?",
        input_options,
        2
    )

    if input_choice is None:
        print("Cancelled. No files processed.")
        return

    # ------------------------------------------------------
    # STEP 2: ASK WHICH OUTPUT FORMAT TO CREATE
    # ------------------------------------------------------
    output_options = [
        "GeoJSON only",
        "Shapefile only",
        "Both GeoJSON and Shapefile"
    ]

    output_choice = ask_choice(
        "Output Selection",
        "Which output format do you want?",
        output_options,
        0
    )

    if output_choice is None:
        print("Cancelled. No files processed.")
        return

    # ------------------------------------------------------
    # STEP 3: VALIDATE FOLDERS
    # ------------------------------------------------------
    if not os.path.isdir(input_folder):
        QMessageBox.critical(
            None,
            "Input Folder Error",
            f"Input folder does not exist:\n{input_folder}"
        )
        return

    # Prevent outputs from being reprocessed on future runs.
    input_abs = os.path.abspath(input_folder)
    output_abs = os.path.abspath(output_folder)

    if input_abs == output_abs:
        QMessageBox.critical(
            None,
            "Folder Error",
            "Please use a separate output folder to avoid "
            "processing your own generated files."
        )
        return

    os.makedirs(output_folder, exist_ok=True)

    # ------------------------------------------------------
    # STEP 4: DETERMINE INPUT AND OUTPUT FORMATS
    # ------------------------------------------------------
    if input_choice == "Shapefile only":
        extensions = (".shp",)
    elif input_choice == "GeoJSON only":
        extensions = (".geojson", ".json")
    else:
        extensions = (".shp", ".geojson", ".json")

    if output_choice == "GeoJSON only":
        output_formats = [("GeoJSON", ".geojson")]
    elif output_choice == "Shapefile only":
        output_formats = [("ESRI Shapefile", ".shp")]
    else:
        output_formats = [
            ("GeoJSON", ".geojson"),
            ("ESRI Shapefile", ".shp")
        ]

    input_files = sorted(
        filename
        for filename in os.listdir(input_folder)
        if filename.lower().endswith(extensions)
        and os.path.isfile(os.path.join(input_folder, filename))
    )

    if not input_files:
        QMessageBox.information(
            None,
            "No Files Found",
            "No matching Shapefile or GeoJSON files were found."
        )
        return

    # ------------------------------------------------------
    # STEP 5: CHECK FOR OUTPUT FILENAME COLLISIONS
    # ------------------------------------------------------
    # Different input formats may have the same base filename.
    # For example, roads.shp and roads.geojson would both produce
    # roads.geojson if GeoJSON output is selected.
    #
    # Stop before exporting rather than silently overwriting data.
    planned_outputs = {}

    for filename in input_files:
        stem = os.path.splitext(filename)[0]

        for driver, out_ext in output_formats:
            output_name = stem + out_ext
            output_path = os.path.normcase(
                os.path.abspath(os.path.join(output_folder, output_name))
            )

            planned_outputs.setdefault(output_path, []).append(filename)

    collisions = {
        path: sources
        for path, sources in planned_outputs.items()
        if len(sources) > 1
    }

    if collisions:
        details = "\n".join(
            f"{os.path.basename(path)} <- {', '.join(sources)}"
            for path, sources in collisions.items()
        )

        QMessageBox.warning(
            None,
            "Duplicate Output Names",
            "Multiple input files would produce the same output name.\n"
            "No files have been processed.\n\n"
            f"{details}\n\n"
            "Use separate input folders or process one source format "
            "at a time to preserve filenames."
        )
        print("Filename collisions detected:")
        print(details)
        return

    # ------------------------------------------------------
    # STEP 6: PROCESS FILES
    # ------------------------------------------------------
    exported = 0
    skipped = 0
    errors = 0

    print("\n" + "=" * 60)
    print("BATCH CONVERSION STARTED")
    print("Input selection:", input_choice)
    print("Output selection:", output_choice)
    print("Files found:", len(input_files))
    print("Output folder:", output_folder)
    print("=" * 60)

    for filename in input_files:

        input_path = os.path.join(input_folder, filename)
        print(f"\nProcessing: {filename}")

        layer = QgsVectorLayer(input_path, filename, "ogr")

        if not layer.isValid():
            print("  SKIPPED: Could not load input file.")
            skipped += 1
            continue

        code_field = find_field(layer, "zone_code")
        name_field = find_field(layer, "zone_name")

        if not code_field or not name_field:
            missing = []
            if not code_field:
                missing.append("zone_code")
            if not name_field:
                missing.append("zone_name")

            print("  SKIPPED: Missing " + ", ".join(missing))
            skipped += 1
            continue

        try:
            # Create temporary layer using the original geometry and CRS.
            geometry_name = QgsWkbTypes.displayString(layer.wkbType())
            crs_id = layer.crs().authid()

            uri = (
                f"{geometry_name}?crs={crs_id}"
                if crs_id
                else geometry_name
            )

            temp_layer = QgsVectorLayer(
                uri, "overlay_temp", "memory"
            )

            if not temp_layer.isValid():
                raise RuntimeError("Could not create temporary layer.")

            provider = temp_layer.dataProvider()

            provider.addAttributes([
                QgsField("overlay_code", QVariant.String, len=254),
                QgsField("overlay_name", QVariant.String, len=254)
            ])
            temp_layer.updateFields()

            # Copy geometry and required attributes.
            new_features = []

            for source_feature in layer.getFeatures():
                feature = QgsFeature(temp_layer.fields())

                if source_feature.hasGeometry():
                    feature.setGeometry(source_feature.geometry())

                code_value = source_feature[code_field]
                name_value = source_feature[name_field]

                feature.setAttribute(
                    "overlay_code",
                    None if code_value is None else str(code_value)
                )
                feature.setAttribute(
                    "overlay_name",
                    None if name_value is None else str(name_value)
                )

                new_features.append(feature)

            success, _ = provider.addFeatures(new_features)

            if not success:
                raise RuntimeError("Could not copy features.")

            temp_layer.updateExtents()

            # Keep the original base filename.
            # Example: Aurora.shp -> Aurora.geojson / Aurora.shp
            stem = os.path.splitext(filename)[0]

            for driver_name, output_extension in output_formats:

                output_name = stem + output_extension
                output_path = os.path.join(
                    output_folder, output_name
                )

                # Never silently overwrite an existing output.
                if os.path.exists(output_path):
                    print(
                        f"  SKIPPED OUTPUT: {output_name} already exists. "
                        "Remove it or choose another output folder."
                    )
                    errors += 1
                    continue

                options = QgsVectorFileWriter.SaveVectorOptions()
                options.driverName = driver_name
                options.fileEncoding = "UTF-8"

                result = QgsVectorFileWriter.writeAsVectorFormatV3(
                    temp_layer,
                    output_path,
                    QgsProject.instance().transformContext(),
                    options
                )

                if result[0] == QgsVectorFileWriter.NoError:
                    print(
                        f"  EXPORTED: {output_name} "
                        f"({len(new_features)} features)"
                    )
                    exported += 1
                else:
                    print(
                        f"  EXPORT ERROR: {output_name}: {result[1]}"
                    )
                    errors += 1

        except Exception as exc:
            print(f"  PROCESSING ERROR: {exc}")
            errors += 1

    # ------------------------------------------------------
    # STEP 7: SUMMARY
    # ------------------------------------------------------
    summary = (
        "Conversion finished!\n\n"
        f"Input files found: {len(input_files)}\n"
        f"Outputs exported: {exported}\n"
        f"Inputs skipped: {skipped}\n"
        f"Errors: {errors}\n\n"
        f"Output folder:\n{output_folder}"
    )

    print("\n" + "=" * 60)
    print(summary)
    print("=" * 60)

    QMessageBox.information(
        None, "Conversion Complete", summary
    )


main()