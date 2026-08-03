from pathlib import Path

direccion = Path(__file__).parent
direccion_archivo = direccion / 'reporte_tco_limpi.csv'
if direccion_archivo.exists():
    print('archivo_existe')
else:
    print('archivo_inexistente')
