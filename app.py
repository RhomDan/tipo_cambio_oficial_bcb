# import sys
# import subprocess

# # Fuerza la instalación en el entorno exacto que ejecuta este archivo
# try:
#     import pandas as pd
#     import dash
#     import dash2html
#     from bs4 import BeautifulSoup
# except ModuleNotFoundError:
#     print("Detectando librerías faltantes... Instalando en el entorno activo.", ModuleNotFoundError)
#     subprocess.check_call([sys.executable, "-m", "pip", "install", "bs4"])
#     print("¡Instalación completada! Reejecuta el script ahora.")
#     sys.exit(0)

import pandas as pd
import requests
import numpy as np
import time
from bs4 import BeautifulSoup
import dash
from dash import dcc, html
import plotly.express as px
import json



headers = {'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36'}

app = dash.Dash(__name__)

def formato_tabla(data):
    data = data.droplevel(1, axis = 1)
    data = data.drop(data.iloc[[-2, -1],:].index.tolist(), axis = 0)
    data['TC (En Bs/USD)'] = data['TC (En Bs/USD)'].astype(float)
    data = data.replace('-', 0)
    data['Monto'] = data['Monto'].astype(float)
    return data

url = 'https://www.bcb.gob.bo/tco_reporte_detalle_historico.php?'
session = requests.Session()
response = session.get(url)
soup = BeautifulSoup(response.text, 'html.parser')
input_fechas = soup.find('input')
fechas = [item.replace('[','').replace(']','').replace('"','') for item in input_fechas['data-fechas'].split(',')]
tco = pd.read_csv('tco_diario.csv')
tco_fechas = tco.fecha.iloc[-1]
informacion_anterior = pd.read_csv('df_canasta_bancos_operaciones_usd.csv')
if len(fechas[fechas.index(tco_fechas) + 1:]) != 0:
    url_base = 'https://www.bcb.gob.bo/tco_reporte_detalle_historico.php?fecha='
    url_tco = [url_base + i for i in fechas[fechas.index(tco_fechas) + 1:]]
    df = pd.DataFrame()
    for url in url_tco:
        try:
            request = requests.post(url, headers = headers)
            tablas = pd.read_html(url, encoding = 'utf-8', thousands = '.', decimal = ',')
            tabla = tablas[0]
            tabla_formato = tabla.copy()
            tabla_formato = tabla_formato.swaplevel(1,0, axis = 1)
            i = 1
            for contador in range(int(tabla_formato.shape[1] / 2)):
                tabla_temp = tabla_formato.iloc[:,[0] + list(range(i ,i + 2))]
                level_0 = tabla_temp.columns[1][1]
                tabla_temp['banco'] = level_0
                tabla_temp['fecha'] = url.split('=')[-1]
                tabla_temp = formato_tabla(tabla_temp)
                df = pd.concat(objs = [df, tabla_temp], axis = 0, ignore_index = True)
                i += 2
            time.sleep(3)
        except:
            pass

try:
    df_consolidado = pd.concat(objs = [informacion_anterior, df], axis = 0, ignore_index = True)
    df_consolidado.to_csv('df_canasta_bancos_operaciones_usd.csv', index = False)
    tco_promedio_pronderado = df[df['banco'] != 'TOTAL BANCOS'].groupby('fecha').apply(lambda x: round(np.average(x['TC (En Bs/USD)'], weights = x['Monto']), 2)).reset_index()
    tco_promedio_pronderado.columns = ['fecha', 'tco']
    tco_promedio_pronderado.to_csv('tco_diario.csv', index = False)
except:
    pass

grap = px.line(
    tco,
    x = 'fecha',
    y = 'tco',
    markers = 'o',
    template = 'plotly_white',
)

bancos_montos = informacion_anterior[informacion_anterior['banco'] != 'TOTAL BANCOS'].groupby(['banco']).agg({'Monto':'sum'}).reset_index()
grap2 = px.bar(
    bancos_montos.sort_values(by = 'Monto'),
    y = 'banco',
    x = 'Monto',
    color = 'banco'
)

bancos_operaciones = informacion_anterior[informacion_anterior['banco'] != 'TOTAL BANCOS'].groupby(['fecha','banco']).agg({'Monto':'sum', 'N°':'sum'}).reset_index()
grap3 = px.scatter(
    bancos_operaciones.query('banco.isin(["BANCO BISA", "BANCO GANADERO", "BANCO MERCANTIL SANTA CRUZ", "BANCO NACIONAL DE BOLIVIA", "BANCO UNION"])'),
    x = 'N°',
    y = 'Monto',
    color = 'banco',
    size="Monto",
    size_max = 30
)
grap3.update_layout(
    legend = dict(yanchor = 'bottom', y = -0.3, orientation = 'h'),
    xaxis = dict(title = 'Cantidad Operaciones'),
    width = 850
)

datos_graficos = {
    "grafico1": json.loads(grap.to_json()),
    "grafico2": json.loads(grap2.to_json()),
    "grafico3": json.loads(grap3.to_json())
}

with open("graficos_data.json", "w", encoding="utf-8") as f:
    json.dump(datos_graficos, f, ensure_ascii=False, indent=4)