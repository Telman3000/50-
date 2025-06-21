# -*- coding: utf-8 -*-
"""
main.py ― FastAPI-приложение:
 • /                  – кнопка «Create» (старый root)
 • /metrics           – HTML-таблица
 • /api/metrics       – JSON для фронтенда
 • /index_front.html  – Chart.js-дашборд   ← новый
 • /dashboard         – то же самое, но короче
 • /static/*          – style.css, script.js и прочее
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pymongo import MongoClient
import pandas as pd
from collections import defaultdict
from datetime import datetime
import os, platform, sys

# ------------------------------------------------------------------
#  MongoDB ― подключение
# ------------------------------------------------------------------
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
DB_NAME   = 'namaz_db'
client    = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5_000)
db        = client[DB_NAME]

col_learners = db['users_learners']
col_logs     = db['users_logs']
col_outcomes = db['outcomes']
col_raw      = db['users_raw']
col_grouped  = db['users_grouped']

# ------------------------------------------------------------------
#  FastAPI + Jinja2
# ------------------------------------------------------------------
app       = FastAPI(title="Dynamic Metrics + API")
templates = Jinja2Templates(directory="templates")

# отдаём /static/*
app.mount("/static", StaticFiles(directory="static"), name="static")

def log(tag: str, msg: str) -> None:
    print(f"[{tag} {datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", file=sys.stderr)

# ------------------------------------------------------------------
#  Вспомогательные функции загрузки + расчёта метрик
#  (ничего не менял по сравнению с предыдущей версией)
# ------------------------------------------------------------------
def load_learners() -> pd.DataFrame:
    df = pd.DataFrame(list(col_learners.find()))
    if df.empty:
        raise RuntimeError("Коллекция users_learners пуста")
    df['_id'] = df['_id'].astype(str)
    df['recommendation_method'] = df['recommendation_method'].astype(str)
    if 'selected' in df.columns:
        df['selected'] = pd.to_numeric(df['selected'], errors='coerce').fillna(0)
        df = df[df['selected'] == 0]
    df['launch_count'] = pd.to_numeric(df.get('launch_count', 0), errors='coerce').fillna(0)
    return df

def load_logs() -> pd.DataFrame:
    df = pd.DataFrame(list(col_logs.find()))
    if df.empty:
        raise RuntimeError("Коллекция users_logs пуста")
    df['learner_id'] = df['learner_id'].astype(str)
    return df

def load_outcome_map() -> dict[str, list[str]]:
    outcome_map = defaultdict(list)
    for doc in col_outcomes.find():
        key = doc.get('Outcome ID') or doc.get('Outcome_ID') or doc.get('OutcomeID')
        for it in map(str.strip, str(doc.get('Assesses', '')).split(',')):
            if it:
                outcome_map[key].append(it)
    return outcome_map

# ---- расчёт метрик (group_size, retention, engagement, ctr, mastery) ----
def grouped_size(df):           return df.groupby('recommendation_method').agg(group_size=('_id','count')).reset_index()
def retention(logs,learn):      return (logs[logs['activity_id']=='launch'].groupby('learner_id').size()
                                       .reset_index(name='launch_count')
                                       .merge(learn[['_id','recommendation_method']], left_on='learner_id', right_on='_id')
                                       .groupby('recommendation_method')['launch_count'].mean().reset_index(name='retention'))
def engagement(logs,learn):     return (logs.groupby('learner_id').size()
                                       .reset_index(name='log_count')
                                       .merge(learn[['_id','recommendation_method']], left_on='learner_id', right_on='_id')
                                       .groupby('recommendation_method')['log_count'].mean().reset_index(name='engagement'))
def ctr(logs,learn):            return (logs[logs['activity_id']=='recommended_item_selected'].groupby('learner_id').size()
                                       .reset_index(name='ctr_clicks')
                                       .merge(learn[['_id','recommendation_method']], left_on='learner_id', right_on='_id')
                                       .groupby('recommendation_method')['ctr_clicks'].sum().reset_index())
def mastery(logs,learn,map_):   # упрощённо: считаем mastery_score как среднее число закрытых outcomes
    if 'value' not in logs.columns:
        out = learn[['recommendation_method']].copy(); out['mastery_rate']=0.0; return out
    numeric = logs[logs['value'].apply(lambda x:str(x).replace('.','',1).isdigit())].copy()
    numeric['score'] = numeric['value'].astype(float)
    item = numeric.groupby(['learner_id','activity_id'])['score'].max().unstack(fill_value=0)
    item['mastery_score'] = item.apply(lambda row: sum(
            1 for items in map_.values() if any(row.get(i,0)>0 for i in items)
        ), axis=1)
    return (item[['mastery_score']].reset_index()
            .merge(learn[['_id','recommendation_method']], left_on='learner_id', right_on='_id')
            .groupby('recommendation_method')['mastery_score'].mean().reset_index(name='mastery_rate'))

def build_metrics_df() -> pd.DataFrame:
    learners, logs, o_map = load_learners(), load_logs(), load_outcome_map()
    col_raw.delete_many({})
    if not learners.empty:
        col_raw.insert_many(learners.to_dict('records'))
    df = (grouped_size(learners)
          .merge(retention(logs, learners))
          .merge(engagement(logs, learners))
          .merge(ctr(logs, learners))
          .merge(mastery(logs, learners, o_map))
          .fillna(0))
    df['CTR'] = df['ctr_clicks'] / df['group_size']
    df = df.round(6).sort_values('recommendation_method')
    col_grouped.delete_many({})
    if not df.empty:
        col_grouped.insert_many(df.to_dict('records'))
    return df

# ------------------------------------------------------------------
#  Роуты
# ------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/metrics", response_class=HTMLResponse)
def metrics_table(request: Request):
    try:
        table_html = build_metrics_df().to_html(classes="table table-striped", index=False)
        return templates.TemplateResponse("metrics.html", {"request": request, "table": table_html})
    except Exception as exc:
        log("ERROR", str(exc))
        return HTMLResponse(f"Ошибка: {exc}", status_code=500)

@app.get("/api/metrics", response_class=JSONResponse)
def api_metrics():
    try:
        return JSONResponse(build_metrics_df().to_dict('records'))
    except Exception as exc:
        log("ERROR", str(exc))
        return JSONResponse({"error": str(exc)}, status_code=500)

# --- НОВЫЕ РОУТЫ ---------------------------------------------------
@app.get("/index_front.html", response_class=HTMLResponse)
@app.get("/dashboard",        response_class=HTMLResponse)
def dashboard(request: Request):
    """
    Страница с графиками Chart.js.
    Два адреса: /index_front.html (чтобы не менять ссылки)
               и /dashboard      (коротко и понятно)
    """
    return templates.TemplateResponse("index_front.html", {"request": request})

# ------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    if platform.system() == "Windows":
        import uvicorn
        uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
    else:
        from gunicorn.app.base import Application
        class FastAPIApp(Application):
            def init(self, parser, opts, args): return {"bind": f"0.0.0.0:{port}", "workers": 2}
            def load(self): return app
        FastAPIApp().run()
