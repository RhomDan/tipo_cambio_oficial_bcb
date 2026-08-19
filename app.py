import pandas as pd
import requests
import numpy as np
import time
from bs4 import BeautifulSoup
import dash
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import plotly.utils as putils
from datetime import timedelta

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
date = pd.read_csv('df_canasta_bancos_operaciones_usd.csv')
tco_fechas = date.fecha.max()
informacion_anterior = pd.read_csv('df_canasta_bancos_operaciones_usd.csv')
if len(fechas[fechas.index(tco_fechas) + 1:]) != 0:
    url_base = 'https://www.bcb.gob.bo/tco_reporte_detalle_historico.php?fecha='
    url_tco = [url_base + i for i in fechas[fechas.index(tco_fechas) + 1:]]
    df = pd.DataFrame()
    for url in url_tco:
        try:
            request = requests.post(url, headers = headers)
            tablas = pd.read_html(url, thousands = '.', decimal = ',', flavor='html5lib')
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
            print('Archivo consolidado con las fechas', fechas[fechas.index(tco_fechas) + 1:])
            time.sleep(3)
        except:
            print('NO hay fechas a incorporar', ValueError)

try:
    df_consolidado = pd.concat(objs = [informacion_anterior, df], axis = 0, ignore_index = True)
    df_consolidado['fecha'] = pd.to_datetime(df_consolidado['fecha'])
    df_consolidado.to_csv('df_canasta_bancos_operaciones_usd.csv', index = False)
    dates = pd.date_range(start = df_consolidado['fecha'].min(), end = df_consolidado['fecha'].max() + timedelta(days = 1), freq = 'D')
    dates = pd.DataFrame(dates, columns = ['fecha'])
    tco = df_consolidado[df_consolidado['banco'] != 'TOTAL BANCOS'].groupby('fecha').apply(lambda x: round(np.average(x['TC (En Bs/USD)'], weights = x['Monto']), 2)).reset_index()
    tco.columns = ['fecha', 'tco']
    tco = dates.merge(right = tco, how = 'left', on = 'fecha')
    tco = tco.ffill()
    tco['tco'] = tco['tco'].shift(1)
    tco = tco.bfill()
    tco.to_csv('tco_diario.csv', index = False)
except:
    pass

df_consolidado = pd.read_csv('df_canasta_bancos_operaciones_usd.csv')
df_consolidado['banco'] = df_consolidado['banco'].apply(lambda x:  ' '.join([nombre[0] + nombre[1:].lower() for nombre in x.split(' ')]))
df_consolidado['banco'] = df_consolidado['banco'].str.replace('De', 'de').str.replace('La', 'la')
tco = pd.read_csv('tco_diario.csv')
montos = df_consolidado.query('banco != "Total Bancos"').groupby('fecha').agg({'Monto':'sum'})
tipo_cambio = df_consolidado.query('banco != "Total Bancos"').groupby('fecha').apply(lambda x: round(np.average(x['TC (En Bs/USD)'], weights = x['Monto']), 2)).rename('tco')
df_tco_montos = pd.concat(objs = [tipo_cambio, montos], axis = 1, join = 'inner')

grap = make_subplots(specs = [[{'secondary_y': True}]])
grap.add_trace(go.Scatter(
    x = tco['fecha'],
    y = tco['tco'],
    mode = 'lines',
    line = dict(
    shape = 'spline',
    smoothing = 1.3,
    width = 2,
    color = 'royalblue'
    ),
    name = 'TCO'
), secondary_y = False)
grap.add_trace(go.Bar(
    x = df_tco_montos.index,
    y = df_tco_montos['Monto'],
    opacity = 0.75,
    name = 'Volumen'
), secondary_y = True)

grap.update_layout(template = 'plotly_white',
                  legend = dict(yanchor = 'bottom',y = -0.25, x = 0.35, orientation = 'h', visible = False),
                  title = dict(text = 'Tipo de Cambio Oficial', xanchor = 'center', x = 0.5),
                  hovermode = 'x', hoverlabel=dict(namelength=-1))
grap.update_yaxes(range = [0, 500000000], secondary_y = True, showgrid = False, showticklabels=False)
grap.update_yaxes(range = [8, 13], secondary_y = False)
grap.update_traces(hovertemplate = '<b>TCO:</b> %{y}<extra></extra>', secondary_y = False)
grap.update_traces(hovertemplate = '<b>Monto:</b> %{y:,.0f}<extra></extra>', secondary_y = True)

bancos_montos = df_consolidado[df_consolidado['banco'] != 'Total Bancos'].groupby(['fecha','banco']).agg({'Monto':'sum'}).reset_index()
bancos_montos['fecha'] = pd.to_datetime(bancos_montos['fecha'])
bancos_montos['fecha_formato'] = bancos_montos['fecha'].dt.strftime('%d-%m')
grap2 = px.bar(
    bancos_montos,
    y = 'banco',
    x = 'Monto',
    color = 'banco',
    animation_frame = 'fecha_formato',
    range_x = [0, bancos_montos['Monto'].max() * 1.1],
    hover_data = ['Monto'],
    title = 'Montos transaccionados por bancos'
)
grap2.update_layout(legend = dict(visible = False),
                    yaxis=dict(tickmode = 'linear', title = '', tickfont = dict(size = 9)),
                    updatemenus = [dict(visible = False)],
                    xaxis = dict(title = 'Montos Transaccionados'),
                    title = dict(xanchor = 'center', x = 0.5),
                    margin = dict(l=150, r=20, t=50, b=80),
                    sliders = [dict(currentvalue = dict(prefix = 'Fecha: ',
                        visible = True,
                        xanchor = 'center'
        )
    )])

mi_plantilla = "<b>Monto:</b> %{x:,.0f}<extra></extra>"

grap2.update_traces(hovertemplate=mi_plantilla)

if grap2.frames:
    for frame in grap2.frames:
        for data in frame.data:
            data.hovertemplate = mi_plantilla

df_consolidado['N°'] = df_consolidado['N°'].astype(float)
bancos_operaciones = df_consolidado[df_consolidado['banco'] != 'Total Bancos'].groupby(['fecha','banco']).agg({'Monto':'sum', 'N°':'sum'}).reset_index()
grap3 = px.scatter(
    bancos_operaciones.query('banco.isin(["Banco Bisa", "Banco Ganadero", "Banco Mercantil Santa Cruz", "Banco Nacional de Bolivia", "Banco Union"])'),
    x = 'N°',
    y = 'Monto',
    color = 'banco',
    size="Monto",
    size_max = 30,
    title = 'Gráfico dispersión montos transaccionados y cantidad de transacciones (Bancos Seleccionados)'
)
grap3.update_layout(
    legend = dict(yanchor = 'bottom', y = -0.3, orientation = 'h'),
    xaxis = dict(title = 'Cantidad Operaciones'),
    title = dict(xanchor = 'center', x = 0.5)
)

datos_graficos = {
    "grafico1": json.loads(grap.to_json()),
    "grafico2": json.loads(grap2.to_json()),
    "grafico3": json.loads(grap3.to_json())
}

fig_dict = grap2.to_dict()

with open("grafico_animado.json", "w") as f:
    json.dump(fig_dict, f, cls=putils.PlotlyJSONEncoder)

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(datos_graficos, f, ensure_ascii=False, indent=4)
