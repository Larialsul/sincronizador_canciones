# Sincronizador de canciones v5

Requisitos: Windows 10/11 y Python 3.12 de 64 bits.

1. Descomprime el ZIP.
2. Ejecuta INICIAR.bat.
3. Sube el audio y pega la letra, una línea por verso.
4. Ajusta el adelanto de inicio si es necesario y genera el JSON.

## Mejora de esta versión
- Adelanta ligeramente la marca respecto a la primera palabra detectada (por defecto 0,18 s).
- Si el reconocedor no detecta la primera palabra de un verso, estima la duración del prefijo omitido usando la duración media local por carácter.
- Permite desactivar esa estimación y ajustar el adelanto entre 0 y 0,70 segundos.

Estas operaciones mejoran la estimación, pero no constituyen una alineación acústica forzada. El resultado debe revisarse escuchando los comienzos, especialmente en canciones con coros, pausas expresivas o palabras omitidas.
