# US Stock Factor Model — Dashboard

## 美股因子选股 · 多空双向 · 云部署

基于 Yahoo Finance 实时数据的量化选股仪表盘。

**Live Demo →** https://us-factor-model.streamlit.app (创建后填入你的URL)

## 功能

- 🎯 **实时信号** — 多空双向，Top 3 Long + Bottom 3 Short
- 🔥 **因子热力图** — 6因子截面表现一目了然
- 📈 **回测曲线** — 22日回测权益曲线
- 📊 **全排行** — 19只美股评分排名
- ⚡ **自动刷新** — 每5分钟自动更新

## 一键部署到云

### 方式1: Streamlit Cloud (免费，推荐)

```bash
# 1. 在 GitHub 创建仓库
# 2. 上传 dashboard/ 目录下的所有文件
# 3. 访问 https://streamlit.io/cloud
# 4. Connect → 选择你的仓库 → Deploy
```

要求:
- 文件: `app.py` + `requirements.txt` (已就绪)
- 免费额度: 每月 1000 小时运行时间

### 方式2: Railway / Render (免费)

```bash
# Railway: 连 GitHub 仓库，自动检测 Python/Streamlit
# Render: 同，选 Web Service → Start Command: streamlit run app.py --server.port $PORT
```

### 方式3: 自有服务器

```bash
pip install -r requirements.txt
streamlit run app.py --server.port 8501
# 用 nginx/caddy 反代到域名
```

## 本地预览

```bash
cd dashboard
pip install -r requirements.txt
streamlit run app.py
# → http://localhost:8501
```

## 数据源

- **Yahoo Finance API** (direct, no rate limit issues)
- **Gate.io** (执行层, 可选)
- 刷新频率: 5分钟缓存

## 技术栈

- Python 3.9+
- Streamlit
- Plotly
- Pandas + NumPy
- Requests

## 文件结构

```
dashboard/
├── app.py            # Streamlit 仪表盘
├── requirements.txt  # 依赖
└── README.md         # 本文件
```
