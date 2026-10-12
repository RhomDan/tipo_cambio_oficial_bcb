import pandas as pd
from curl_cffi import requests
import requests as req
import numpy as np
import time
from bs4 import BeautifulSoup
import re
import dash
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import plotly.utils as putils
from datetime import timedelta, datetime
import warnings

warnings.filterwarnings('ignore')

headers = {'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36'}

app = dash.Dash(__name__)

def formato_tabla(data):
    data = data.droplevel(1, axis = 1)
    data = data.drop(data.iloc[[-2, -1],:].index.tolist(), axis = 0)
    data['TC (En Bs/USD)'] = data['TC (En Bs/USD)'].astype(float)
    data = data.replace('-', 0)
    data['Monto'] = data['Monto'].astype(float)
    return data

def mediana_ponderada (group):
    datos = group['TC (En Bs/USD)'].to_numpy()
    pesos = group['Monto'].to_numpy()
    indices = np.argsort(datos)
    datos_ordenados = datos[indices]
    pesos_ordenados = pesos[indices]
    pesos_acumulados = np.cumsum(pesos_ordenados)
    mitad_peso = np.sum(pesos) / 2.0
    return datos_ordenados[pesos_acumulados >= mitad_peso][0]

url_bancos = ['https://www.bisa.com/home', 'https://bancounion.com.bo/', 'https://www.bancosol.com.bo/',
              'https://www.bcp.com.bo/', 'https://www.bg.com.bo/personas/', 'https://www.bnb.com.bo/PortalBNB/Principal/BancaPersonas']
bancos = ['BISA', 'BUN', 'BancoSol', 'BCP', 'Banco Ganadero', 'BNB']
url_bancos_api = ['https://backportal.bmsc.com.bo:1443/api/bmscservices/tipotre',
                  'https://www.baneco.com.bo/GetTipoCambio',
                  'https://www.bancofortaleza.com.bo/proxy-exchange.php',
                  ]
bancos_api = ['BMSC', 'Banco Económico', 'Banco Fortaleza']

url = 'https://www.bcb.gob.bo/bcb_tco_publico_detalle_historico.php'
session = req.Session()
response = session.get(url)
soup = BeautifulSoup(response.text, 'html.parser')
input_fechas = soup.find('input')
fechas = [item.replace('[','').replace(']','').replace('"','') for item in input_fechas['data-fechas'].split(',')]
date = pd.read_csv('df_canasta_bancos_operaciones_usd.csv')
tco_fechas = date.fecha.max()
informacion_anterior = pd.read_csv('df_canasta_bancos_operaciones_usd.csv')
if len(fechas[fechas.index(tco_fechas) + 1:]) != 0:
    url_base = 'https://www.bcb.gob.bo/bcb_tco_publico_detalle_historico.php?fecha='
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
                tabla_temp = tabla_formato.iloc[:,[0] + list(range(i ,i + 2))].copy()
                level_0 = tabla_temp.columns[1][1]
                tabla_temp['banco'] = level_0
                tabla_temp['fecha'] = url.split('=')[-1]
                tabla_temp = formato_tabla(tabla_temp)
                df = pd.concat(objs = [df, tabla_temp], axis = 0, ignore_index = True)
                i += 2
            print('Archivo consolidado con las fechas', fechas[fechas.index(tco_fechas) + 1:])
            cotizacion = {}
            for i, url in enumerate(url_bancos):
                response = requests.get(url, impersonate="chrome", verify = False, timeout = 15)
                soup = BeautifulSoup(response.text, 'html.parser')
                encontrar_compra = re.findall(r'(?:Dól?ar\s+Compra|Compra|Compra BOB|compra:)[:\s]*([\d.,]+)',soup.get_text(), flags = re.IGNORECASE)
                encontrar_venta = re.findall(r'(?:Dól?ar\s+Venta|Venta|venta:|Venta USD)[:\s]*([\d.,]+)',soup.get_text(), flags = re.IGNORECASE)
                encontrar_compra = [elemento for elemento in encontrar_compra if any(char.isdigit() for char in elemento)]
                encontrar_venta = [elemento for elemento in encontrar_venta if any(char.isdigit() for char in elemento)]
                cotizacion[bancos[i]] = {'dolar_compra':np.nan if len(encontrar_compra) < 1 else encontrar_compra[0], 
                                        'dolar_venta':np.nan if len(encontrar_venta) < 1 else encontrar_venta[0]}
            cotizaciones_api = {}
            for i, url_api in enumerate(url_bancos_api):
                response = requests.get(url_api, timeout = 15, verify = False)
                data_api = response.json()
                if data_api.get('response') == None:
                    data_api = {k.lower():v for k, v in data_api.items()}
                    cotizaciones_api[bancos_api[i]] = {'dolar_compra':data_api['compra'],
                                                'dolar_venta':data_api['venta']}
                else:
                    data_api_response = data_api['response']
                    cotizaciones_api[bancos_api[i]] = {'dolar_compra':data_api_response['buyExchange'],
                                                'dolar_venta':data_api_response['saleExchange']}
            cotizaciones_bancos = pd.concat(
                objs = [pd.DataFrame(cotizacion).T, pd.DataFrame(cotizaciones_api).T],
                axis = 0
                ).reset_index()
            cotizaciones_bancos = cotizaciones_bancos.rename({'index':'banco'}, axis = 1)
            cotizaciones_bancos['fecha'] = datetime.now().strftime('%Y-%m-%d')
            cotizaciones_bancos['dolar_compra'] = pd.to_numeric(cotizaciones_bancos['dolar_compra'].astype(str).str.replace(',', '.', regex=False), errors='coerce')
            cotizaciones_bancos['dolar_venta'] = pd.to_numeric(cotizaciones_bancos['dolar_venta'].astype(str).str.replace(',', '.', regex=False), errors='coerce')
            time.sleep(3)
        except:
            print('NO hay fechas a incorporar', ValueError)
try:
    df_consolidado = pd.concat(objs = [informacion_anterior, df], axis = 0, ignore_index = True)
    df_consolidado['fecha'] = pd.to_datetime(df_consolidado['fecha'])
    df_consolidado.to_csv('df_canasta_bancos_operaciones_usd.csv', index = False)
    dates = pd.date_range(start = df_consolidado['fecha'].min(), end = df_consolidado['fecha'].max() + timedelta(days = 1), freq = 'D')
    dates = pd.DataFrame(dates, columns = ['fecha'])
    fecha_cambio = pd.to_datetime('2026-09-25')
    df_consolidado['fecha'] = pd.to_datetime(df_consolidado['fecha'])
    tco = df_consolidado[(df_consolidado['banco'] != 'TOTAL BANCOS') & (df_consolidado['fecha'] < fecha_cambio)].groupby('fecha').apply(lambda x: round(np.average(x['TC (En Bs/USD)'], weights = x['Monto']), 2)).reset_index()
    n_tco = df_consolidado[(df_consolidado['banco'] != 'TOTAL BANCOS') & (df_consolidado['fecha'] >= fecha_cambio)].groupby('fecha').apply(mediana_ponderada, include_groups = False)
    n_tco = n_tco.reset_index()
    tco_consolidado = pd.concat(objs = [tco, n_tco], axis = 0)
    tco_consolidado.columns = ['fecha', 'tco']
    tco_consolidado = dates.merge(right = tco_consolidado, how = 'left', on = 'fecha')
    tco_consolidado = tco_consolidado.ffill()
    tco_consolidado['tco'] = tco_consolidado['tco'].shift(1)
    tco_consolidado = tco_consolidado.bfill()
    tco_consolidado.to_csv('tco_diario.csv')
    dolares = pd.read_csv('cotizaciones_bancos_multiples.csv')
    actualizado_dolares = pd.concat(objs = [dolares, cotizaciones_bancos])
    actualizado_dolares.to_csv('cotizaciones_bancos_multiples.csv', index = False)
except:
    pass

df_consolidado = pd.read_csv('df_canasta_bancos_operaciones_usd.csv')
df_consolidado['banco'] = df_consolidado['banco'].apply(lambda x:  ' '.join([nombre[0] + nombre[1:].lower() for nombre in x.split(' ')]))
df_consolidado['banco'] = df_consolidado['banco'].str.replace('De', 'de').str.replace('La', 'la')
tco = pd.read_csv('tco_diario.csv')
montos = df_consolidado.query('banco != "Total Bancos"').groupby('fecha').agg({'Monto':'sum'}).reset_index()
df_tco_montos = tco.merge(right = montos, on = 'fecha', how = 'outer')
cuartil1 = df_consolidado.query('banco != "Total Bancos"').groupby('fecha').apply(lambda x: round(np.quantile(a = x['TC (En Bs/USD)'], q = 0.25), 2)).reset_index(name = 'q1')
cuartil3 = df_consolidado.query('banco != "Total Bancos"').groupby('fecha').apply(lambda x: round(np.quantile(a = x['TC (En Bs/USD)'], q = 0.75), 2)).reset_index(name = 'q3')
df_tco_total = df_tco_montos.merge(right = cuartil1, how = 'left', on = 'fecha')
df_tco_total = df_tco_total.merge(right = cuartil3, how = 'left', on = 'fecha')
df_tco_total['q1'] = df_tco_total['q1'].ffill()
df_tco_total['q3'] = df_tco_total['q3'].ffill()
etiqueta_ric = [f'{q_1:.2f} -{q_3:.2f}' for q_1, q_3 in zip(df_tco_total['q1'], df_tco_total['q3'])]
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
    x = df_tco_montos['fecha'],
    y = df_tco_montos['Monto'],
    opacity = 0.75,
    name = 'Volumen'
), secondary_y = True)
grap.add_trace(go.Scatter(
    x = df_tco_total['fecha'],
    y = df_tco_total['q3'],
    mode = 'lines',
    line = dict( width = 0),
    hoverinfo = 'skip',
    name = 'Q1 - Q3'
), secondary_y = False)
grap.add_trace(go.Scatter(
    x = df_tco_total['fecha'],
    y = df_tco_total['q1'],
    mode = 'lines',
    line = dict( width = 0),
    fill = 'tonexty',
    fillcolor = 'rgba(0, 86, 179, 0.15)',
    showlegend = False,
    hoverinfo = 'skip',
    name = 'Q1 - Q3'
), secondary_y = False)

grap.update_layout(template = 'plotly_white',
                  legend = dict(yanchor = 'bottom',y = -0.25, x = 0.35, orientation = 'h', visible = True),
                  title = dict(text = 'Tipo de Cambio Oficial', xanchor = 'center', x = 0.5),
                  hovermode = 'x',
                  hoverlabel=dict(namelength=-1))
grap.update_yaxes(range = [0, 500000000], secondary_y = True, showgrid = False, showticklabels=False)
grap.update_yaxes(range = [8, 13], secondary_y = False)
grap.update_traces(text = etiqueta_ric, hovertemplate = '<b>TCO:</b> %{y:,.2f}<br><b>Q1 - Q3:</b> %{text}<extra></extra>', secondary_y = False)
grap.update_traces(hovertemplate = '<b>Monto:</b> %{y:,.0f}<extra></extra>', secondary_y = True)
grap.update_traces(
    hoverinfo='skip',
    hovertemplate=None,
    selector = lambda trace: trace.name not in ['TCO', 'Volumen']
)

bancos_montos = df_consolidado[df_consolidado['banco'] != 'Total Bancos'].groupby(['fecha','banco']).agg({'Monto':'sum'}).reset_index()
bancos_montos['fecha'] = pd.to_datetime(bancos_montos['fecha'])
bancos_montos['fecha_formato'] = bancos_montos['fecha'].dt.strftime('%d-%m')
bancos_orden = bancos_montos.groupby('banco')['Monto'].sum().sort_values(ascending=False).index.tolist()
banco_posicion = {banco: posicion for posicion, banco in enumerate(bancos_orden)}
bancos_montos['posicion_banco'] = bancos_montos['banco'].map(banco_posicion)
altura_grap2 = max(420, len(bancos_orden) * 22 + 90)
grap2 = px.bar(
    bancos_montos,
    y = 'posicion_banco',
    x = 'Monto',
    orientation = 'h',
    animation_frame = 'fecha_formato',
    range_x = [0, bancos_montos['Monto'].max() * 1.1],
    hover_data = ['banco'],
    # title = 'Montos transaccionados por bancos'
)
grap2.update_layout(legend = dict(visible = False),
                    yaxis=dict(type = 'linear',
                               tickmode = 'array',
                               tickvals = list(range(len(bancos_orden))),
                               ticktext = bancos_orden,
                               range = [len(bancos_orden) - 0.5, -0.5],
                               automargin = True,
                               title = '',
                               tickfont = dict(size = 10)),
                    updatemenus = [dict(visible = False)],
                    xaxis = dict(title = 'Montos Transaccionados'),
                    title = dict(xanchor = 'center', x = 0.5),
                    margin = dict(l=230, r=30, t=65, b=90),
                    bargap = 0.15,
                    barmode = 'overlay',
                    height = altura_grap2,
                    sliders = [dict(currentvalue = dict(prefix = 'Fecha: ',
                        visible = True,
                        xanchor = 'center'
        )
    )])

colores_bancos = px.colors.qualitative.Dark24
mi_plantilla = "<b>Banco:</b> %{customdata[0]}<br><b>Monto:</b> %{x:,.0f}<extra></extra>"
ancho_barra = 0.75

for trace in grap2.data:
    trace.marker.color = [
        colores_bancos[int(posicion) % len(colores_bancos)]
        for posicion in trace.y
    ]
    trace.hovertemplate = mi_plantilla
    trace.width = ancho_barra

for frame in grap2.frames:
    frame.layout.bargap = 0.15
    frame.layout.barmode = 'overlay'
    for data in frame.data:
        data.marker.color = [
            colores_bancos[int(posicion) % len(colores_bancos)]
            for posicion in data.y
        ]
        data.hovertemplate = mi_plantilla
        data.width = ancho_barra



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

tarjetas = make_subplots(rows = 1, cols = 2,
                         specs = [[{"type": "indicator"}, {"type": "indicator"}]],
                         vertical_spacing = 0.1)
tarjetas.add_trace(
    go.Indicator(
        mode = 'delta+number',
        value = df_tco_montos['tco'].iloc[-1],
        delta={"reference": df_tco_montos['tco'].iloc[-2]},
        title={"text": f"T.C.O. para el {pd.to_datetime(tco['fecha'].iloc[-1]).strftime('%d-%b')}", "align": "center"},
        number={"font": {"size": 48}},
    ),
    row = 1,
    col = 1
)
tarjetas.add_trace(
    go.Indicator(
        mode = 'delta+number',
        value = montos['Monto'].iloc[-1],
        delta={"reference": montos['Monto'].iloc[-2]},
        title={"text": f"Total transaccionado<br><span style='font-size:1.0em;color:gray'>{pd.to_datetime(tco['fecha'].iloc[-2]).strftime('%d-%b')}</span>", "align": "center"},
        number={"font": {"size": 48}},
    ),
    row = 1,
    col = 2
)

monto_ultimo = montos['Monto'].iloc[-1]
tco_ultimo = df_tco_montos['tco'].iloc[-1]
fecha_ultimo_monto = pd.to_datetime(tco['fecha'].iloc[-2]).strftime('%d-%b')
fecha_tco_ultimo = pd.to_datetime(tco['fecha'].iloc[-1]).strftime('%d-%b')
banco_lider_ultimo = bancos_montos[bancos_montos['fecha']==bancos_montos['fecha'].max()].sort_values(by = 'Monto', ascending = False).iloc[0,1]
q1_ultimo = df_tco_total[df_tco_total['fecha'] == df_tco_total['fecha'].max()].iloc[0,4]
q3_ultimo = df_tco_total[df_tco_total['fecha'] == df_tco_total['fecha'].max()].iloc[0,5]

df = df_consolidado.query('banco != "Total Bancos"').groupby('fecha').agg({'TC (En Bs/USD)':['min', 'max']}).sort_index(ascending = False).reset_index()
tc_min_ultimo = df.iloc[0,1]
tc_max_ultimo = df.iloc[0,2]

df_dolares = pd.read_csv('cotizaciones_bancos_multiples.csv')
df_dolares['fecha_fmt'] = pd.to_datetime(df_dolares['fecha'], format = '%Y-%m-%d')
df_dolares['dolar_compra_formato'] = -df_dolares['dolar_compra'].abs()

df_grafico = df_dolares.copy()
fecha_maxima = df_grafico["fecha"].max()
df_filtrado = df_grafico[df_grafico["fecha"] == fecha_maxima].copy()

df_filtrado["dolar_compra_formato"] = df_filtrado["dolar_compra_formato"].replace(
    0, float("nan"))

fig_cotizaciones_bancos = go.Figure()

fig_cotizaciones_bancos.add_trace(
    go.Bar(
        y=df_filtrado["banco"],
        x=df_filtrado["dolar_compra_formato"],
        orientation="h",
        name="Dólar Compra",
        hoverinfo='skip',
        marker_color="#1f77b4",
        text=df_filtrado["dolar_compra"].map(
            lambda x: f"{x:.2f}" if pd.notna(x) else ""
        ),
        textposition="inside",
    )
)

fig_cotizaciones_bancos.add_trace(
    go.Bar(
        y=df_filtrado["banco"],
        x=df_filtrado["dolar_venta"],
        orientation="h",
        name="Dólar Venta",
        hoverinfo='skip',
        marker_color="#d62728",
        text=df_filtrado["dolar_venta"].map(
            lambda x: f"{x:.2f}" if pd.notna(x) else ""
        ),
        textposition="inside",
    )
)

fig_cotizaciones_bancos.update_layout(
    title={
        "text": f"<b>Tipo de Cambio por Banco en Bolivia <br> ({fecha_maxima})</b>",
        "y": 0.95,
        "x": 0.5,
        "xanchor": "center",
    },
    barmode="relative", 
    template="plotly_white",
    bargap=0.3,
    xaxis=dict(
        visible = False
    ),
    width = 450,
    legend = dict(yanchor = 'auto', orientation = 'h', visible = True)
)

datos_graficos = {
    'tarjeta1': json.loads(tarjetas.to_json()),
    "grafico1": json.loads(grap.to_json()),
    "grafico2": json.loads(grap2.to_json()),
    "grafico3": json.loads(grap3.to_json()),
    'cotizacion': json.loads(fig_cotizaciones_bancos.to_json()),
    'metricas': {
        'monto_total': monto_ultimo,
        'fecha_monto_transaccionado': fecha_ultimo_monto,
        'tco_promedio': tco_ultimo,
        'fecha_tco': fecha_tco_ultimo,
        'val_q1': q1_ultimo,
        'val_q3': q3_ultimo,
        'banco_lider': banco_lider_ultimo,
        'tc_min': tc_min_ultimo,
        'tc_max': tc_max_ultimo
    }
}


fig_dict = grap2.to_dict()

with open("grafico_animado.json", "w") as f:
    json.dump(fig_dict, f, cls=putils.PlotlyJSONEncoder)

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(datos_graficos, f, ensure_ascii=False, indent=4)