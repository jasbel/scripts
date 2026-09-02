#!/bin/bash
# Obtener lista y convertir a WebP

DIRECTORIO="/home/asbel/projects/appium/barik-testing/docs/resources/examples"

echo "Archivos encontrados y conversión:"
echo "----------------------------------"

for archivo in "$DIRECTORIO"/*.{jpeg,jpg,png,JPEG,JPG,PNG}; do
    if [ -f "$archivo" ]; then
        nombre=$(basename "$archivo")
        extension="${nombre##*.}"
        nombre_sin_ext="${nombre%.*}"
        output="$DIRECTORIO/${nombre_sin_ext}.webp"
        
        echo "Nombre: $nombre_sin_ext | Extensión: $extension -> Convirtiendo a WebP..."
        cwebp -q 85 -m 6 "$archivo" -o "$output"
    fi
done
