import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
from portfolio_utils import PortfolioAnalyzer, FundScreener
from portfolio_charts import render_profile_detail, _donut_svg, _badge
import io
import hashlib
import json
import time

# ページ設定
st.set_page_config(
    page_title="投資信託ポートフォリオ最適化 Pro",
    page_icon="📊",
    layout="wide"
)

# ─── デザインシステム定数 ────────────────────────────────────
# 仕様書 Section 2.2 に準拠したプロファイル別テーマカラー
_PROFILE_META = {
    "積極型":     {"color": "#9b2c2c", "grad": "linear-gradient(135deg,#9b2c2c,#7b1f1f)", "label_en": "Aggressive",   "icon": "▲▲"},
    "やや積極型": {"color": "#c05621", "grad": "linear-gradient(135deg,#c05621,#9a4218)", "label_en": "Growth",       "icon": "▲"},
    "バランス型": {"color": "#2f855a", "grad": "linear-gradient(135deg,#2f855a,#236644)", "label_en": "Balanced",     "icon": "◆"},
    "やや保守型": {"color": "#2b6cb0", "grad": "linear-gradient(135deg,#2b6cb0,#1e4f8a)", "label_en": "Moderate",     "icon": "▼"},
    "保守型":     {"color": "#2c5282", "grad": "linear-gradient(135deg,#2c5282,#1e3a63)", "label_en": "Conservative", "icon": "▼▼"},
}
_BRAND_NAVY  = "#0f172a"
_BRAND_GOLD  = "#b3904a"
_BRAND_LIGHT = "#f8fafc"

# カスタムCSS
st.markdown("""
<style>
    /* ── ブランドヘッダー ── */
    .hfd-header {
        background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 60%, #1f4e79 100%);
        padding: 22px 32px 18px;
        border-bottom: 3px solid #b3904a;
        margin: -1rem -1rem 1.2rem -1rem;
        color: #fff;
    }
    .hfd-header-eyebrow {
        font-size: 0.65rem;
        letter-spacing: 0.18em;
        opacity: 0.6;
        margin-bottom: 4px;
        font-weight: 600;
    }
    .hfd-header-title {
        font-size: 1.45rem;
        font-weight: 800;
        letter-spacing: 0.04em;
        line-height: 1.2;
    }
    .hfd-header-sub {
        font-size: 0.75rem;
        opacity: 0.6;
        margin-top: 6px;
    }
    /* ── コアファンド情報バー ── */
    .core-bar {
        background: #fffbea;
        border: 1px solid #d4af6a;
        border-left: 4px solid #b3904a;
        border-radius: 6px;
        padding: 10px 16px;
        margin-bottom: 14px;
        display: flex;
        align-items: center;
        gap: 14px;
        flex-wrap: wrap;
        font-size: 0.82rem;
    }
    .core-bar-label { font-weight: 700; color: #7a5c00; font-size: 0.78rem; }
    .core-bar-name  { font-weight: 700; color: #0f172a; font-size: 0.88rem; }
    .core-bar-item  { color: #475569; }
    .core-bar-item b { color: #0f172a; }
    /* ── セクションヘッダー ── */
    .section-header {
        font-size: 1.05rem;
        font-weight: 800;
        color: #0f172a;
        border-left: 4px solid #b3904a;
        padding: 4px 0 4px 12px;
        margin: 1.4rem 0 0.8rem 0;
        letter-spacing: 0.03em;
    }
    /* ── プロファイルカード ── */
    .profile-cards-wrap {
        display: flex;
        gap: 10px;
        margin-bottom: 14px;
        flex-wrap: wrap;
    }
    .profile-card {
        flex: 1;
        min-width: 155px;
        border-radius: 6px;
        overflow: hidden;
        border: 2px solid #e8ecf0;
        background: #fff;
        box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    }
    .profile-card-header {
        padding: 14px 14px 10px;
        color: #fff;
    }
    .profile-card-eyebrow {
        font-size: 0.6rem;
        font-weight: 700;
        letter-spacing: 0.12em;
        opacity: 0.8;
        margin-bottom: 2px;
    }
    .profile-card-title {
        font-size: 1.0rem;
        font-weight: 800;
    }
    .profile-card-range {
        font-size: 0.65rem;
        opacity: 0.75;
        margin-top: 2px;
    }
    .profile-card-top {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-top: 8px;
    }
    .profile-card-ret {
        font-size: 1.6rem;
        font-weight: 800;
        line-height: 1;
    }
    .profile-card-ret-label {
        font-size: 0.6rem;
        opacity: 0.75;
        margin-top: 2px;
    }
    .profile-card-body {
        padding: 10px 12px;
    }
    .profile-card-row {
        display: flex;
        justify-content: space-between;
        margin-bottom: 5px;
        font-size: 0.75rem;
    }
    .profile-card-row-label { color: #2f3e4d; }
    .profile-card-row-label-sub { font-size: 0.6rem; color: #4f6270; display: block; line-height: 1.3; margin-top: 1px; }
    .profile-card-row-val   { font-weight: 700; color: #1e3a5f; text-align: right; flex-shrink: 0; margin-left: 4px; }
    .risk-bar-wrap { margin-top: 8px; }
    /* ── プロファイル解説文 ── */
    .profile-card-commentary {
        font-size: 0.7rem;
        color: #2f3e4d;
        line-height: 1.65;
        padding: 9px 12px 10px;
        border-top: 1px solid #f0ece4;
        background: #faf8f4;
    }
    /* ── 分析期間・免責ボックス ── */
    .profile-disclaimer-box {
        background: #fffbeb;
        border: 1px solid #e8c060;
        border-radius: 6px;
        padding: 8px 14px;
        font-size: 0.72rem;
        color: #6a4000;
        line-height: 1.7;
        margin-bottom: 10px;
        display: flex;
        gap: 8px;
        align-items: flex-start;
    }
    /* ── シャープレシオ凡例 ── */
    .sr-legend-wrap {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        align-items: center;
        font-size: 0.68rem;
        color: #2f3e4d;
        margin-top: 6px;
        margin-bottom: 14px;
    }
    .sr-legend-chip {
        padding: 2px 8px;
        border-radius: 4px;
        font-weight: 700;
        font-size: 0.65rem;
    }
    .risk-bar-track {
        height: 5px;
        background: #e8ecf0;
        border-radius: 99px;
        overflow: hidden;
    }
    .risk-bar-fill {
        height: 100%;
        border-radius: 99px;
    }
    /* ── メトリクスバッジ ── */
    .metric-badges-wrap {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        margin-top: 12px;
    }
    .metric-badge {
        background: #fff;
        border: 1px solid #e8ecf0;
        border-radius: 6px;
        padding: 10px 12px;
        min-width: 100px;
        flex: 1;
    }
    .metric-badge-label {
        font-size: 0.62rem;
        color: #2f3e4d;
        font-weight: 700;
        letter-spacing: 0.07em;
        text-transform: uppercase;
        margin-bottom: 3px;
    }
    .metric-badge-value {
        font-size: 1.2rem;
        font-weight: 800;
        color: #1e3a5f;
        line-height: 1.1;
    }
    .metric-badge-sub {
        font-size: 0.62rem;
        color: #445563;
        margin-top: 2px;
    }
    /* ── 健全性バナー ── */
    .health-ok {
        background: #f0fdf4;
        border: 1px solid #22c55e;
        border-left: 4px solid #22c55e;
        border-radius: 6px;
        padding: 10px 14px;
        font-size: 0.82rem;
        color: #166534;
        margin-bottom: 10px;
    }
    .health-warn {
        background: #fffbeb;
        border: 1px solid #f59e0b;
        border-left: 4px solid #f59e0b;
        border-radius: 6px;
        padding: 10px 14px;
        font-size: 0.82rem;
        color: #92400e;
        margin-bottom: 10px;
    }
    /* ── シャープ比較バー ── */
    .sr-compare-wrap { padding: 4px 0; }
    .sr-compare-row  { margin-bottom: 10px; }
    .sr-compare-header {
        display: flex;
        justify-content: space-between;
        font-size: 0.75rem;
        margin-bottom: 3px;
    }
    .sr-compare-bar-track {
        height: 6px;
        background: #e8ecf0;
        border-radius: 99px;
        overflow: hidden;
    }
    .sr-compare-bar-fill {
        height: 100%;
        border-radius: 99px;
    }
    .sr-note {
        margin-top: 12px;
        padding: 9px 12px;
        background: #f0f4f8;
        border-radius: 6px;
        font-size: 0.72rem;
        color: #556;
        line-height: 1.6;
    }
    /* ── 従来互換 ── */
    .sub-header {
        font-size: 1.1rem;
        font-weight: 800;
        color: #0f172a;
        border-left: 4px solid #b3904a;
        padding: 4px 0 4px 12px;
        margin: 1.4rem 0 0.8rem 0;
    }
    /* ── 設定パネル全体 ── */
    .settings-box {
        background: linear-gradient(160deg, #0a1929 0%, #0f172a 60%, #0d1f3c 100%);
        padding: 0;
        border-radius: 6px;
        border: 1px solid rgba(179,144,74,0.3);
        margin-bottom: 2rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 1px 0 rgba(179,144,74,0.10) inset;
        overflow: hidden;
    }
    .settings-panel-header {
        background: rgba(179,144,74,0.08);
        border-bottom: 1px solid rgba(179,144,74,0.2);
        padding: 16px 24px 14px;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .settings-panel-header-icon {
        width: 32px; height: 32px;
        background: linear-gradient(135deg, #b3904a, #8a6a30);
        border-radius: 6px;
        display: flex; align-items: center; justify-content: center;
        font-size: 16px; line-height: 1;
        flex-shrink: 0;
        box-shadow: 0 2px 8px rgba(179,144,74,0.4);
    }
    .settings-panel-header-text { flex: 1; }
    .settings-panel-header-title {
        font-size: 0.88rem;
        font-weight: 800;
        color: #d4af6a;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        line-height: 1.2;
    }
    .settings-panel-header-sub {
        font-size: 0.72rem;
        color: rgba(255,255,255,0.75);
        margin-top: 3px;
        font-weight: 500;
    }
    .settings-panel-body {
        padding: 20px 24px 24px;
    }
    /* ── 設定行ラベル（白文字対応） ── */
    .settings-box label,
    .settings-box .stSelectbox label,
    .settings-box .stFileUploader label,
    .settings-box p,
    .settings-box .stMarkdown p {
        color: rgba(255,255,255,0.85) !important;
        font-weight: 600 !important;
        font-size: 0.8rem !important;
        letter-spacing: 0.04em !important;
    }
    /* selectbox ドロップダウンの値テキスト */
    .settings-box .stSelectbox [data-baseweb="select"] span,
    .settings-box .stSelectbox [data-baseweb="select"] div {
        color: #fff !important;
    }
    /* ── アップロードゾーン ── */
    .upload-zone-wrap {
        background: rgba(255,255,255,0.04);
        border: 2px dashed rgba(179,144,74,0.4);
        border-radius: 6px;
        padding: 24px 20px;
        text-align: center;
        margin-bottom: 20px;
        transition: border-color 0.2s;
    }
    .upload-zone-wrap:hover {
        border-color: rgba(179,144,74,0.7);
    }
    .upload-zone-icon {
        font-size: 2rem;
        margin-bottom: 8px;
        display: block;
    }
    .upload-zone-title {
        font-size: 0.88rem;
        font-weight: 700;
        color: #d4af6a;
        margin-bottom: 4px;
    }
    .upload-zone-sub {
        font-size: 0.7rem;
        color: rgba(255,255,255,0.4);
    }
    /* ── 設定グリッド ── */
    .settings-grid-label {
        font-size: 0.7rem;
        font-weight: 700;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: rgba(179,144,74,0.85);
        margin-bottom: 6px;
        display: flex;
        align-items: center;
        gap: 6px;
    }
    .settings-section-divider {
        border: none;
        border-top: 1px solid rgba(179,144,74,0.15);
        margin: 18px 0;
    }
    /* ── コアファンドセクション ── */
    .core-fund-section-header {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 12px;
    }
    .core-fund-badge {
        background: linear-gradient(135deg, #b3904a, #8a6a30);
        color: #0f172a;
        font-size: 0.62rem;
        font-weight: 800;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        padding: 3px 9px;
        border-radius: 20px;
        flex-shrink: 0;
    }
    .core-fund-section-title {
        font-size: 0.85rem;
        font-weight: 700;
        color: #d4af6a;
    }
    .core-fund-hint {
        font-size: 0.7rem;
        color: rgba(255,255,255,0.45);
        line-height: 1.5;
        margin-top: 6px;
        padding: 8px 12px;
        background: rgba(255,255,255,0.04);
        border-radius: 6px;
        border-left: 3px solid rgba(179,144,74,0.3);
    }
    /* ── 実行ボタン エリア ── */
    .run-button-area {
        margin-top: 20px;
        padding-top: 18px;
        border-top: 1px solid rgba(179,144,74,0.15);
    }
    .run-button-hint {
        font-size: 0.68rem;
        color: rgba(255,255,255,0.35);
        text-align: center;
        margin-top: 8px;
    }
    /* ── 成功バナー（ダーク版） ── */
    .upload-success-bar {
        background: rgba(34,197,94,0.12);
        border: 1px solid rgba(34,197,94,0.3);
        border-left: 4px solid #22c55e;
        border-radius: 6px;
        padding: 10px 16px;
        font-size: 0.78rem;
        color: #86efac;
        margin-bottom: 16px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    /* ── Streamlit selectbox/uploader の上書き（ダーク背景対応） ── */
    .settings-box .stFileUploader > div {
        background: rgba(255,255,255,0.06) !important;
        border: 1px solid rgba(179,144,74,0.3) !important;
        border-radius: 6px !important;
    }
    .settings-box .stSelectbox > div > div {
        background: rgba(255,255,255,0.07) !important;
        border: 1px solid rgba(255,255,255,0.15) !important;
        border-radius: 4px !important;
        color: #fff !important;
    }
    /* ── 免責事項フッター ── */
    .disclaimer {
        margin-top: 24px;
        padding: 10px 14px;
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 6px;
        font-size: 0.7rem;
        color: #475569;
        line-height: 1.7;
    }
    /* ═══════════════════════════════════════════════════════════
       統合レポートパネル: 3タブ共通フレーム
       ═══════════════════════════════════════════════════════════ */
    .report-panel-header {
        background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 100%);
        border-radius: 6px 6px 0 0;
        padding: 15px 22px 13px;
        border-bottom: 3px solid #b3904a;
        display: flex;
        align-items: center;
        gap: 14px;
    }
    .report-panel-icon {
        width: 36px; height: 36px;
        background: linear-gradient(135deg, #b3904a, #8a6a30);
        border-radius: 6px;
        display: flex; align-items: center; justify-content: center;
        font-size: 18px; flex-shrink: 0;
        box-shadow: 0 2px 8px rgba(179,144,74,0.4);
    }
    .report-panel-title {
        font-size: 1.02rem;
        font-weight: 800;
        color: #d4af6a;
        letter-spacing: 0.04em;
        line-height: 1.2;
    }
    .report-panel-meta {
        font-size: 0.70rem;
        color: rgba(255,255,255,0.52);
        margin-top: 3px;
    }
    .report-panel-disclaimer {
        background: #fffbeb;
        border: 1px solid #d4af6a;
        border-top: none;
        border-radius: 0;
        padding: 7px 20px;
        font-size: 0.71rem;
        color: #92400e;
        line-height: 1.7;
        display: flex;
        gap: 8px;
        align-items: flex-start;
        margin-bottom: 0;
    }
    /* タブリスト */
    .stTabs [data-baseweb="tab-list"] {
        background: #f8fafc !important;
        border-radius: 0 !important;
        padding: 0 14px !important;
        border-bottom: 2px solid #e2e8f0 !important;
        gap: 2px !important;
        margin-top: 0 !important;
    }
    .stTabs [data-baseweb="tab"] {
        background: transparent !important;
        border-radius: 4px 4px 0 0 !important;
        padding: 8px 16px !important;
        font-weight: 600 !important;
        font-size: 0.83rem !important;
        color: #94a3b8 !important;
        border: none !important;
        margin-bottom: -2px !important;
    }
    .stTabs [aria-selected="true"] {
        background: #fff !important;
        color: #0f172a !important;
        border-bottom: 2px solid #fff !important;
        font-weight: 800 !important;
    }
    .stTabs [data-baseweb="tab-panel"] {
        background: #fff !important;
        border: 1px solid #e2e8f0 !important;
        border-top: none !important;
        border-radius: 0 0 6px 6px !important;
        padding: 18px 18px 22px !important;
    }
    /* タブ内サブヘッダー */
    .tab-sub-header {
        font-size: 0.80rem;
        font-weight: 800;
        color: #0f172a;
        border-left: 3px solid #b3904a;
        padding: 2px 0 2px 10px;
        margin: 16px 0 10px 0;
        letter-spacing: 0.03em;
    }

    /* ── ボタン（仕様書 Section 2.3）── */
    /* プライマリ：ネイビー地＋白文字 */
    div.stButton > button[kind="primary"],
    div.stButton > button:not([kind="secondary"]) {
        background: #0f172a !important;
        color: #ffffff !important;
        border: 1px solid #0f172a !important;
        border-radius: 4px !important;
        font-weight: 600;
        letter-spacing: 0.02em;
        transition: background 0.15s;
    }
    div.stButton > button[kind="primary"]:hover,
    div.stButton > button:not([kind="secondary"]):hover {
        background: #1e3a5f !important;
        border-color: #1e3a5f !important;
    }
    /* セカンダリ：ゴールドボーダー＋ネイビー文字 */
    div.stButton > button[kind="secondary"] {
        background: transparent !important;
        color: #0f172a !important;
        border: 1.5px solid #b3904a !important;
        border-radius: 4px !important;
        font-weight: 600;
        letter-spacing: 0.02em;
        transition: background 0.15s;
    }
    div.stButton > button[kind="secondary"]:hover {
        background: rgba(179,144,74,0.08) !important;
    }

</style>
""", unsafe_allow_html=True)

# ─── ヘッダー ─────────────────────────────────────────────────
st.markdown("""
<div class="hfd-header">
  <div class="hfd-header-eyebrow">HEDGE FUND DIRECT Co., Ltd.　関東財務局長（金商）第532号</div>
  <div class="hfd-header-title">コア・サテライト ポートフォリオ最適化</div>
  <div class="hfd-header-sub">月次基準価格データをアップロードして、投資家向けポートフォリオ提案を生成</div>
</div>
""", unsafe_allow_html=True)

# ── ステップインジケーター（全体共通・左揃え統一） ──
st.markdown("""
<div style="display:flex;align-items:stretch;gap:0;margin:12px 0 18px 0;
            background:rgba(15,39,68,0.06);border:1px solid rgba(179,144,74,0.18);
            border-radius:6px;overflow:hidden;">
  <div style="flex:1;padding:10px 16px;border-right:1px solid rgba(179,144,74,0.15);">
    <div style="display:flex;align-items:center;gap:7px;">
      <span style="background:linear-gradient(135deg,#b3904a,#8a6a30);color:#0f172a;
                   border-radius:4px;padding:2px 8px;font-size:0.65rem;font-weight:800;
                   letter-spacing:0.08em;flex-shrink:0;">STEP 1</span>
      <span style="font-size:0.78rem;font-weight:700;color:#1e3a5f;">📂 データアップロード</span>
    </div>
    <div style="font-size:0.65rem;color:#66788a;margin-top:3px;">月次基準価格 .xlsx</div>
  </div>
  <div style="flex:1;padding:10px 16px;border-right:1px solid rgba(179,144,74,0.15);">
    <div style="display:flex;align-items:center;gap:7px;">
      <span style="background:linear-gradient(135deg,#b3904a,#8a6a30);color:#0f172a;
                   border-radius:4px;padding:2px 8px;font-size:0.65rem;font-weight:800;
                   letter-spacing:0.08em;flex-shrink:0;">STEP 2</span>
      <span style="font-size:0.78rem;font-weight:700;color:#1e3a5f;">⚙️ 分析設定</span>
    </div>
    <div style="font-size:0.65rem;color:#66788a;margin-top:3px;">期間・ベンチマーク・コアファンド</div>
  </div>
  <div style="flex:1;padding:10px 16px;">
    <div style="display:flex;align-items:center;gap:7px;">
      <span style="background:linear-gradient(135deg,#b3904a,#8a6a30);color:#0f172a;
                   border-radius:4px;padding:2px 8px;font-size:0.65rem;font-weight:800;
                   letter-spacing:0.08em;flex-shrink:0;">STEP 3</span>
      <span style="font-size:0.78rem;font-weight:700;color:#1e3a5f;">🚀 分析実行</span>
    </div>
    <div style="font-size:0.65rem;color:#66788a;margin-top:3px;">最適化 → 5段階プロファイル生成</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── アップロードゾーン ──
st.markdown("""
<div style="margin-bottom:4px;">
  <div style="font-size:0.7rem;color:#66788a;margin-bottom:6px;">
    Date列 + 各ファンドの月次基準価格を含む .xlsx ファイル（推奨：3年以上・50本以上）
  </div>
</div>
""", unsafe_allow_html=True)

uploaded_file = st.file_uploader(
    "Excelファイルを選択",
    type=['xlsx'],
    label_visibility="collapsed",
    help="日付列（Date）と各ファンドの月次基準価格を含む .xlsx ファイルを選択してください"
)

if uploaded_file is not None:
    # ⑧ ファイル内容変化の検知: 同名・同サイズで中身だけ変わったファイルを確実に捕捉する。
    # 先頭4KBのMD5ハッシュをIDに含めることで、数値の一部修正・上書き保存も検知できる。
    _raw_peek = uploaded_file.read(4096)
    uploaded_file.seek(0)
    _file_id = f"{uploaded_file.name}_{uploaded_file.size}_{hashlib.md5(_raw_peek).hexdigest()[:8]}"
    if st.session_state.get('_last_file_id') != _file_id:
        # 新しいファイルを検知 → 下流の分析結果をすべてリセット（状態遷移ルール）
        for _key in ['run_analysis', 'optimization_results', 'selected_profile',
                     'analysis_settings', 'selected_funds_after_run',
                     'selected_card_profile', 'view_mode']:
            st.session_state.pop(_key, None)
        st.session_state['_last_file_id'] = _file_id

    # データ読み込み
    # D-03 修正：file_id を明示的なキャッシュキー引数として渡す。
    # UploadedFile オブジェクト単体ではハッシュが変わらない場合があるため、
    # ファイル名+サイズを文字列化した file_id でキャッシュを確実に無効化する。
    @st.cache_data
    def load_data(file, file_id: str):  # noqa: ARG001（file_id はキャッシュキー専用）
        df = pd.read_excel(file)
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.set_index('Date').sort_index()
        return df

    try:
        df_price = load_data(uploaded_file, _file_id)
    except Exception as _load_err:
        # Section 5: エラー種別「データ形式不正」
        st.markdown(
            f'<div class="health-warn">⚠️ <b>ファイル形式または列構成が想定と異なります</b>　'
            f'正しい列構成（Date列 + 各ファンドの月次NAV）の .xlsx ファイルを再アップロードしてください。'
            f'<br><span style="font-size:0.78rem;opacity:0.8;">詳細: {_load_err}</span></div>',
            unsafe_allow_html=True
        )
        st.stop()
    
    # ─────────────────────────────────────────────────────────────
    # 全ファンド概観テーブル計算関数
    # ─────────────────────────────────────────────────────────────
    @st.cache_data(show_spinner=False)
    def compute_fund_overview_table(cache_key: str, _df_price: pd.DataFrame,
                                    fund_cols_tuple: tuple, core_fund: str,
                                    analysis_months: int,
                                    rf_rate: float = 0.005) -> pd.DataFrame:
        """
        全ファンドの多期間リターン・リスク・相関サマリーテーブルを計算。
        
        ・マルチピリオドリターン : 1年/3年/5年/10年/設定来（年率CAGR）
        ・リスク指標             : 設定来ボラティリティ、最大DD、シャープレシオ、月次勝率
        ・コア相関               : 設定来相関、選択分析期間の相関、ローリング相関安定性
        
        Parameters
        ----------
        cache_key      : df_price の内容変化を検知するためのハッシュ文字列
        _df_price      : 基準価格DataFrame（全期間）
        fund_cols_tuple: 対象ファンド列名のタプル
        core_fund      : コアファンド名（相関計算の基準）
        analysis_months: 選択中の分析期間（月数）
        """
        fund_cols = list(fund_cols_tuple)
        
        # コアファンドの全期間リターン系列
        core_px_full = _df_price[core_fund].dropna()
        core_ret_full = core_px_full.pct_change().dropna()
        
        # コアファンドの分析期間リターン系列
        # pct_change()で1本消費されるため、必要月次リターン数+1本の価格データを取得する
        core_px_period = _df_price[core_fund].iloc[-(analysis_months + 1):].dropna()
        core_ret_period = core_px_period.pct_change().dropna()
        
        def cagr(ret_series: pd.Series, months: int):
            """指定月数の年率CAGR。データ不足はNoneを返す。"""
            if len(ret_series) < months:
                return None
            r = ret_series.iloc[-months:]
            cum = (1 + r).prod() - 1
            return (1 + cum) ** (12.0 / months) - 1
        
        rows = []
        for fund in fund_cols:
            prices = _df_price[fund].dropna()
            if len(prices) < 13:   # 最低1年分（12ヶ月リターン + 1ヶ月）
                continue
            
            ret = prices.pct_change().dropna()
            n = len(ret)
            data_years = round(n / 12.0, 1)
            
            # ── マルチピリオドリターン ──────────────────────────────
            r1y   = cagr(ret, 12)
            r3y   = cagr(ret, 36)
            r5y   = cagr(ret, 60)
            r10y  = cagr(ret, 120)
            r_all = cagr(ret, n)        # 設定来
            
            # ── 設定来リスク指標 ────────────────────────────────────
            vol   = ret.std(ddof=1) * np.sqrt(12)
            # 無リスク金利を控除したシャープレシオ（rf_rate=0.0のときは従来と同値）
            sharpe = ((r_all - rf_rate) / vol) if (r_all is not None and vol > 1e-6) else None

            # ① 最大DD: 先頭に 1.0 を付加して期初損失を正確に捕捉（_calculate_statistics と統一）
            # 旧実装 cum_ret.cummax() は第1期の損失を DD=0 と誤計上する可能性があった。
            cum_np   = np.concatenate([[1.0], (1 + ret.values).cumprod()])
            rmax_np  = np.maximum.accumulate(cum_np)
            dd_np    = (cum_np - rmax_np) / rmax_np
            max_dd   = float(dd_np[1:].min())
            
            win_rate = (ret > 0).sum() / n     # 月次勝率
            
            # ── コアファンドとの相関 ────────────────────────────────
            # 設定来相関
            idx_full = ret.index.intersection(core_ret_full.index)
            corr_full = (
                ret[idx_full].corr(core_ret_full[idx_full])
                if len(idx_full) >= 12 else None
            )
            
            # 分析期間相関
            idx_period = ret.index.intersection(core_ret_period.index)
            corr_period = (
                ret[idx_period].corr(core_ret_period[idx_period])
                if len(idx_period) >= 6 else None
            )
            
            # 相関安定性：12ヶ月ローリング相関の標準偏差
            # σが小さいほど相関が安定（分散効果が予測しやすい）
            # min_periods=12 を明示して、不完全ウィンドウによるゼロ混入を防ぐ
            if len(idx_full) >= 24:
                rolling_c = (
                    ret[idx_full]
                    .rolling(12, min_periods=12)
                    .corr(core_ret_full[idx_full])
                )
                corr_stability = rolling_c.dropna().std(ddof=1) if rolling_c.dropna().shape[0] >= 2 else None
            else:
                corr_stability = None
            
            rows.append({
                'ファンド名'           : fund,
                'データ期間(年)'       : data_years,
                '1年リターン'          : r1y,
                '3年リターン(年率)'    : r3y,
                '5年リターン(年率)'    : r5y,
                '10年リターン(年率)'   : r10y,
                '設定来リターン(年率)' : r_all,
                '設定来ボラ'           : vol,
                'シャープ(設定来)'     : sharpe,
                '最大DD(設定来)'       : max_dd,
                '月次勝率'             : win_rate,
                'コア相関(設定来)'     : corr_full,
                f'コア相関({analysis_months//12}年)'  : corr_period,
                '相関安定性(σ)'        : corr_stability,
            })
        
        return pd.DataFrame(rows).set_index('ファンド名')
    
    def _make_overview_col_config(columns) -> dict:
        """
        float の overview DataFrame 用 column_config を生成する。
        - pct列は x100 済みの値を "%.1f%%" でフォーマット（ソート可能）
        - 符号付き列（リターン/最大DD）は "+%.1f%%" でフォーマット
        - 相関・シャープ・期間は "%.2f" / "%.1f"
        """
        # \n を使わず空白で折り返しラベルを定義（dict リテラル内の改行エラー回避）
        pct_signed_label = {
            '1年リターン':        '1年 リターン(%)',
            '3年リターン(年率)':  '3年 リターン(%)',
            '5年リターン(年率)':  '5年 リターン(%)',
            '10年リターン(年率)': '10年 リターン(%)',
            '設定来リターン(年率)':'設定来 リターン(%)',
            '最大DD(設定来)':     '最大DD 設定来(%)',
        }
        pct_unsigned_label = {
            '設定来ボラ': '設定来 ボラ(%)',
            '月次勝率':   '月次 勝率(%)',
        }
        cfg = {}
        for col in columns:
            if col in pct_signed_label:
                cfg[col] = st.column_config.NumberColumn(
                    pct_signed_label[col], format="%+.1f%%")
            elif col in pct_unsigned_label:
                cfg[col] = st.column_config.NumberColumn(
                    pct_unsigned_label[col], format="%.1f%%")
            elif col == 'シャープ(設定来)':
                cfg[col] = st.column_config.NumberColumn(
                    'シャープ(設定来)', format="%.2f")
            elif col == 'データ期間(年)':
                cfg[col] = st.column_config.NumberColumn(
                    '期間(年)', format="%.1f")
            elif 'コア相関' in col or '相関安定性' in col:
                cfg[col] = st.column_config.NumberColumn(col, format="%.2f")
        return cfg

    def _prep_overview_df(df_raw: pd.DataFrame) -> pd.DataFrame:
        """
        overview_raw（小数）から表示・ソート用 DataFrame を作成する。
        % 列を ×100 した float のまま返す（文字列変換なし）。
        → st.dataframe の列ソートが正しく機能する。
        """
        pct_cols = [
            '1年リターン', '3年リターン(年率)', '5年リターン(年率)',
            '10年リターン(年率)', '設定来リターン(年率)',
            '設定来ボラ', '最大DD(設定来)', '月次勝率',
        ]
        df = df_raw.copy()
        for col in pct_cols:
            if col in df.columns:
                df[col] = df[col] * 100   # float のまま ×100（ソート有効）
        return df

    def style_overview_table(df_raw: pd.DataFrame,
                              core_fund: str,
                              selected_funds: list = None) -> "pd.io.formats.style.Styler":
        """
        選定ファンド詳細統計など小テーブル向け：Styler で行ハイライトのみ適用。
        （大テーブルは _prep_overview_df + _make_overview_col_config を使用）
        """
        df_disp = _prep_overview_df(df_raw)

        pct_signed_cols = [
            '1年リターン', '3年リターン(年率)', '5年リターン(年率)',
            '10年リターン(年率)', '設定来リターン(年率)', '最大DD(設定来)',
        ]
        pct_unsigned_cols = ['設定来ボラ', '月次勝率']
        fmt = {}
        for col in pct_signed_cols:
            if col in df_disp.columns:
                fmt[col] = lambda x: f"{x:+.1f}%" if pd.notna(x) else "—"
        for col in pct_unsigned_cols:
            if col in df_disp.columns:
                fmt[col] = lambda x: f"{x:.1f}%" if pd.notna(x) else "—"
        for col in ['シャープ(設定来)', 'データ期間(年)']:
            if col in df_disp.columns:
                fmt[col] = lambda x: f"{x:.2f}" if pd.notna(x) else "—"
        corr_cols = [c for c in df_disp.columns if 'コア相関' in c or '相関安定性' in c]
        for col in corr_cols:
            fmt[col] = lambda x: f"{x:.2f}" if pd.notna(x) else "—"

        def row_style(row):
            name = row.name
            if name == core_fund:
                return ['background-color: #dbeafe; font-weight: bold'] * len(row)
            if selected_funds and name in selected_funds and name != core_fund:
                return ['background-color: #fef9c3'] * len(row)
            return [''] * len(row)

        styled = df_disp.style.apply(row_style, axis=1)
        if fmt:
            styled = styled.format(fmt, na_rep="—")
        styled = styled.set_properties(**{'text-align': 'right'})
        styled = styled.set_table_styles([
            {'selector': 'th.col_heading', 'props': 'text-align: center; font-size: 0.82em;'},
            {'selector': 'th.row_heading', 'props': 'text-align: left; font-size: 0.82em;'},
            {'selector': 'td', 'props': 'font-size: 0.82em; padding: 3px 8px;'},
        ])
        return styled
    
    # 通貨列を除外（それ以外は全てファンド候補として扱う）
    currency_keywords = ['USD-JPY', 'EUR-JPY', 'GBP-JPY', 'CHF-JPY', 'AUD-JPY']
    fund_cols = [col for col in df_price.columns 
                 if not any(curr in col for curr in currency_keywords)]
    
    st.markdown(
        f'<div style="background:linear-gradient(135deg,#ecfdf5,#d1fae5);border:1px solid #6ee7b7;'
        f'border-left:4px solid #10b981;border-radius:6px;padding:12px 18px;margin-bottom:8px;'
        f'display:flex;align-items:center;gap:12px;">'
        f'<span style="font-size:1.2rem;">✅</span>'
        f'<div>'
        f'<div style="font-size:0.8rem;font-weight:700;color:#065f46;">データ読み込み完了</div>'
        f'<div style="font-size:0.72rem;color:#047857;margin-top:2px;">'
        f'<b>{len(fund_cols)}本</b>のファンド／ベンチマーク　·　'
        f'期間 <b>{df_price.index[0].strftime("%Y年%m月")}</b> ～ <b>{df_price.index[-1].strftime("%Y年%m月")}</b>'
        f'　·　<b>{len(df_price)}</b>ヶ月分'
        f'</div></div></div>',
        unsafe_allow_html=True
    )
    
    # セッション状態の初期化（Section 4 状態変数一覧）
    if 'run_analysis' not in st.session_state:
        st.session_state.run_analysis = False
    if 'analysis_settings' not in st.session_state:
        st.session_state.analysis_settings = {}
    if 'view_mode' not in st.session_state:
        st.session_state['view_mode'] = 'client'
    
    # メインエリアに設定セクションを配置
    st.markdown('<div class="settings-box">', unsafe_allow_html=True)
    
    # ── パネルヘッダー（インラインスタイルで確実にダーク表示） ──
    st.markdown("""
<div style="background:rgba(179,144,74,0.10);border-bottom:1px solid rgba(179,144,74,0.22);
            padding:14px 22px 12px;display:flex;align-items:center;gap:12px;
            margin:-1px -1px 0 -1px;">
  <div style="width:32px;height:32px;background:linear-gradient(135deg,#b3904a,#8a6a30);
              border-radius:6px;display:flex;align-items:center;justify-content:center;
              font-size:16px;flex-shrink:0;box-shadow:0 2px 8px rgba(179,144,74,0.4);">⚙️</div>
  <div>
    <div style="font-size:0.9rem;font-weight:800;color:#d4af6a;letter-spacing:0.05em;
                line-height:1.2;">分析設定</div>
    <div style="font-size:0.72rem;color:rgba(232,213,160,0.8);margin-top:3px;font-weight:500;">
      期間・ベンチマーク・コアファンドを選択してください
    </div>
  </div>
</div>
<div style="padding:20px 22px 22px;">
""", unsafe_allow_html=True)

    # ── 3列対等レイアウト：分析期間 ／ ベンチマーク ／ コアファンド ──
    _lbl = ('style="font-size:0.82rem;font-weight:700;color:#d4af6a;'
            'margin-bottom:6px;display:flex;align-items:center;gap:7px;line-height:1.3;"')

    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown(f'<div {_lbl}><span>📅</span> 分析期間</div>', unsafe_allow_html=True)
        period_options = {"1年": 12, "3年": 36, "5年": 60, "10年": 120, "15年": 180}
        selected_period = st.selectbox(
            "分析期間", list(period_options.keys()), index=1, label_visibility="collapsed"
        )
        months_param = period_options[selected_period]
    
    # 期間でフィルタ（一時的）
    df_temp = df_price.iloc[-(months_param + 1):].copy()
    missing_rates_temp = df_temp[fund_cols].isnull().sum() / len(df_temp)
    valid_funds_temp = missing_rates_temp[missing_rates_temp < 0.2].index.tolist()
    sorted_funds = sorted(valid_funds_temp)
    
    if len(sorted_funds) == 0:
        st.error("有効ファンドが0本です（欠損率が高い可能性があります）。期間を長くするか、データをご確認ください。")
        st.stop()
    
    with col2:
        st.markdown(f'<div {_lbl}><span>📊</span> 比較ベンチマーク</div>', unsafe_allow_html=True)
        benchmark_options = ["なし"] + fund_cols
        default_benchmark = "世界株" if "世界株" in fund_cols else "なし"
        default_index = benchmark_options.index(default_benchmark)
        benchmark_param = st.selectbox(
            "比較ベンチマーク", benchmark_options, index=default_index, label_visibility="collapsed"
        )
    
    with col3:
        st.markdown(
            f'<div {_lbl}><span>🎯</span> コアファンドを選択'
            f'<span style="margin-left:auto;font-size:0.68rem;font-weight:600;'
            f'color:rgba(179,144,74,0.85);white-space:nowrap;">{len(valid_funds_temp)}本</span></div>',
            unsafe_allow_html=True
        )
        core_fund_param = st.selectbox(
            "コアファンドを選択（ファンド名の一部を入力して絞り込み）",
            sorted_funds, index=0,
            help="キーワードを入力すると候補が絞り込まれます。アルファベット順に表示しています。",
            label_visibility="collapsed"
        )
    
    # 選択確認バー
    st.markdown(
        f'<div style="font-size:0.7rem;color:rgba(179,144,74,0.75);margin-top:4px;margin-bottom:0;'
        f'padding:6px 10px;background:rgba(179,144,74,0.06);border-radius:6px;">'
        f'🎯 <b style="color:#d4af6a;">{core_fund_param}</b>'
        f'&ensp;·&ensp; 期間 <b style="color:#d4af6a;">{selected_period}</b>'
        f'&ensp;·&ensp; ベンチマーク <b style="color:#d4af6a;">{benchmark_param}</b>'
        f'</div>',
        unsafe_allow_html=True
    )

    # ─────────────────────────────────────────────────────────────
    # 全ファンド概観テーブル（計算は常に実行・表示はサイドバーのチェックボックスで制御）
    # ─────────────────────────────────────────────────────────────
    # rf_rate_annual はサイドバー（下方）で定義されるが、ここで先行参照が必要なため
    # セッションステートから取得する（初回はデフォルト0.5%、以降は前回設定値を使用）
    rf_rate_annual = st.session_state.get('rf_rate', 0.005)

    with st.spinner("サマリーテーブルを計算中..."):
        # ⑦ キャッシュキーに先頭日も含め、データの先頭変化（古いファンド削除等）を確実に検知する
        _key_src = (
            f"{df_price.index[0].strftime('%Y%m')}_{df_price.index[-1].strftime('%Y%m')}"
            f"_{months_param}"
            f"_{rf_rate_annual:.4f}"
            f"_{','.join(sorted(df_price.columns))}"
        )
        _cache_key = hashlib.md5(_key_src.encode()).hexdigest()[:12]
        overview_raw = compute_fund_overview_table(
            _cache_key,
            df_price,
            tuple(sorted(valid_funds_temp)),
            core_fund_param,
            months_param,
            rf_rate_annual,
        )

    # ── 実行ボタン ──────────────────────────────────────────────
    st.markdown("""
<hr style="border:none;border-top:1px solid rgba(179,144,74,0.18);margin:20px 0 14px 0;">
</div><!-- /settings-panel-body -->
""", unsafe_allow_html=True)

    run_button = st.button("🚀　分析実行　— ポートフォリオ最適化を開始", type="primary", use_container_width=True)

    st.markdown("""
<div style="font-size:0.65rem;color:rgba(255,255,255,0.3);text-align:center;margin-top:6px;margin-bottom:4px;">
  スクリーニング → 最適化 → 5段階プロファイル生成まで自動実行します
</div>
""", unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # ── サイドバー ──────────────────────────────────────────────
    st.sidebar.markdown("""
<div style="padding:4px 0 8px 0;">
  <div style="font-size:0.7rem;font-weight:800;letter-spacing:0.1em;text-transform:uppercase;
              color:#b3904a;margin-bottom:2px;">🔍 詳細設定</div>
  <div style="font-size:0.65rem;color:#66788a;">スクリーニング条件をカスタマイズ</div>
</div>
""", unsafe_allow_html=True)
    n_funds_final_param = st.sidebar.slider("最終選定ファンド数", 20, 40, 30, 1)
    
    with st.sidebar.expander("⚙️ 高度なスクリーニング設定", expanded=False):
        st.markdown(
            '<div style="font-size:0.68rem;color:#66788a;margin-bottom:8px;">'
            '相関バケット別選定（v3.1）<br>'
            'コアとの相関度に応じて5つの役割に分類し、各バケットで最適な銘柄を選定します。'
            '</div>',
            unsafe_allow_html=True
        )
        st.markdown(
            '<div style="font-size:0.67rem;color:#66788a;margin-top:6px;margin-bottom:4px;">'
            '📊 バケット別割当枠（コアを除くファンド数）</div>',
            unsafe_allow_html=True
        )
        bq_neg    = st.slider("マイナス相関（ヘッジ役）",    0, 6, 2, 1)
        bq_low    = st.slider("低相関 0〜0.25（分散役）",   0, 6, 3, 1)
        bq_midlo  = st.slider("中低相関 0.25〜0.5（バランス役）", 0, 8, 5, 1)
        bq_midhi  = st.slider("中高相関 0.5〜0.75（収益補完役）", 0, 8, 5, 1)
        bq_high   = st.slider("高相関 0.75〜1.0（リターン牽引役）", 0, 6, 4, 1)
        bucket_quota_param = {
            'マイナス相関': bq_neg,
            '低相関':       bq_low,
            '中低相関':     bq_midlo,
            '中高相関':     bq_midhi,
            '高相関':       bq_high,
        }

    # ── 無リスク金利設定（シャープレシオ計算に使用） ────────────────
    # 現在の金利環境（日本国債・米国債）を踏まえてデフォルト0.5%に設定
    with st.sidebar.expander("📐 シャープレシオ設定", expanded=False):
        rf_rate_param = st.slider(
            "無リスク金利（年率%）",
            min_value=0.0, max_value=3.0, value=0.5, step=0.1,
            help="シャープレシオ計算時に控除する無リスク金利。日本国債利回りを目安に設定してください（デフォルト：0.5%）"
        )
    rf_rate_annual = rf_rate_param / 100.0  # 小数に変換
    # 次回のページトップ先行参照（overview table のキャッシュキー）で使えるよう保存
    st.session_state['rf_rate'] = rf_rate_annual

    # ── サイドバー：推定・最適化設定 ──────────────────────────────
    st.sidebar.markdown("""
<div style="margin-top:14px;padding:8px 0 6px 0;
            border-top:1px solid rgba(179,144,74,0.2);">
  <div style="font-size:0.7rem;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;
              color:#b3904a;margin-bottom:6px;">🔬 推定・最適化設定</div>
</div>
""", unsafe_allow_html=True)

    # [改善E] Ledoit-Wolf 共分散推定量の切替
    # ON（デフォルト）: 統計的に信頼性の高い推定量。ノイズを収縮させ最適化を安定化。
    # OFF: 観測値をそのまま使うサンプル共分散。説明性・透明性が高い。
    _use_lw = st.sidebar.checkbox(
        "Ledoit-Wolf 収縮共分散（推奨）",
        value=True,
        key="use_ledoit_wolf",
        help=(
            "ON（推奨）：Ledoit-Wolf収縮推定量を使用。\n"
            "観測ノイズを統計的に圧縮し最適化の安定性が向上。\n\n"
            "OFF：生データ（サンプル共分散）を使用。\n"
            "観測値をそのまま反映するため説明性・透明性が高い。\n"
            "ただし短期データでは推定誤差が大きくなる場合があります。"
        ),
    )

    # [改善F] リスクパリティ配分の表示切替
    # コアウェイト制約を維持したまま、サテライト部分の
    # リスク寄与（Risk Contribution）を均等化する配分戦略。
    _show_rp = st.sidebar.checkbox(
        "リスクパリティ配分を表示",
        value=False,
        key="show_risk_parity",
        help=(
            "バランス型のコア比率（50〜65%）を維持したまま、\n"
            "サテライト各ファンドのリスク寄与を均等化した配分を追加表示します。\n\n"
            "名目ウェイト（保有比率）ではなく「リスクの分散」を\n"
            "最大化したい場合の参考に使用してください。"
        ),
    )

    # ── サイドバー：全ファンドサマリー ──────────────────────────
    st.sidebar.markdown("""
<div style="margin-top:16px;padding:8px 0 6px 0;
            border-top:1px solid rgba(179,144,74,0.2);">
  <div style="font-size:0.7rem;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;
              color:#b3904a;margin-bottom:6px;">📊 表示オプション</div>
</div>
""", unsafe_allow_html=True)

    _show_summary = st.sidebar.checkbox(
        "全ファンド パフォーマンス・リスク・相関サマリー",
        value=False, key="show_full_summary",
        help="全ファンドのパフォーマンス・リスク・相関サマリーを表示します"
    )
    _show_fund_stats = st.sidebar.checkbox(
        "選定ファンド 詳細統計",
        value=False, key="show_fund_stats",
        help="スクリーニングで選定されたファンドの詳細統計を表示します"
    )
    _show_profile_metrics = st.sidebar.checkbox(
        "全プロファイル 詳細指標",
        value=False, key="show_profile_metrics",
        help="5プロファイル全ての詳細指標を表示します"
    )
    _show_diagnosis = st.sidebar.checkbox(
        "ポートフォリオ診断パネル",
        value=False, key="show_diagnosis",
        help="健全性チェック・コアファンド情報バーを表示します"
    )
    _show_min_adj = st.sidebar.checkbox(
        "最小組入比率 自動調整の通知",
        value=False, key="show_min_adj_warning",
        help="銘柄数増加時にmin_individualが自動調整された場合、その詳細を表示します"
    )

    if _show_summary:
        st.markdown('<div class="section-header">📊 全ファンド パフォーマンス・リスク・相関サマリー</div>', unsafe_allow_html=True)
        st.caption(
            "💡 **コアファンドとの相関**を確認しながら分析期間を選んでください。"
            "　設定来列はファンドの全期間データ。"
            "　🔵コアファンド行　🟡分析実行後：選定ファンド行"
        )

        tab_perf, tab_risk, tab_corr = st.tabs([
            "📈 マルチピリオドリターン",
            "⚠️ リスク指標",
            "🔗 コアファンド相関"
        ])

        with tab_perf:
            _perf_cols  = ['データ期間(年)', '1年リターン', '3年リターン(年率)',
                           '5年リターン(年率)', '10年リターン(年率)', '設定来リターン(年率)']
            _perf_avail = [c for c in _perf_cols if c in overview_raw.columns]
            _perf_df    = _prep_overview_df(overview_raw[_perf_avail])
            st.dataframe(
                _perf_df,
                column_config=_make_overview_col_config(_perf_df.columns),
                use_container_width=True, height=400,
            )
            st.caption("💡 列ヘッダークリックでソート可。年率CAGR表示。🔵コアファンド行は凡例のみ（ハイライトは選定後）")

        with tab_risk:
            _risk_cols  = ['データ期間(年)', '設定来リターン(年率)', '設定来ボラ',
                           'シャープ(設定来)', '最大DD(設定来)', '月次勝率']
            _risk_avail = [c for c in _risk_cols if c in overview_raw.columns]
            _risk_df    = _prep_overview_df(overview_raw[_risk_avail])
            st.dataframe(
                _risk_df,
                column_config=_make_overview_col_config(_risk_df.columns),
                use_container_width=True, height=400,
            )
            st.caption("💡 列ヘッダークリックでソート可。最大DD：-10%以内が理想、-25%超は要注意。シャープ：1.0超が優秀。")

        with tab_corr:
            _corr_cols  = ['データ期間(年)', '設定来リターン(年率)', '設定来ボラ',
                           'コア相関(設定来)', f'コア相関({months_param//12}年)', '相関安定性(σ)']
            _corr_avail = [c for c in _corr_cols if c in overview_raw.columns]
            _corr_df    = _prep_overview_df(overview_raw[_corr_avail])
            st.dataframe(
                _corr_df,
                column_config=_make_overview_col_config(_corr_df.columns),
                use_container_width=True, height=400,
            )
            st.caption(
                f"💡 列ヘッダークリックでソート可。コアファンド「{core_fund_param}」との相関。分散効果の目安：0.3〜0.7が理想ゾーン。"
            )

    if run_button:
        # Section 4: 設定変更検知 → optimization_results をリセット
        _new_settings = {
            'months': months_param, 'core_fund': core_fund_param,
            'benchmark': benchmark_param, 'n_funds_final': n_funds_final_param,
            'bucket_quota': bucket_quota_param,
            'rf_rate': rf_rate_annual,
        }
        if _new_settings != st.session_state.get('analysis_settings', {}):
            # 設定が変わった場合は最適化結果をリセット
            st.session_state.pop('optimization_results', None)
        st.session_state.analysis_settings = _new_settings
        st.session_state.run_analysis = True
        st.session_state.months = months_param
        st.session_state.core_fund = core_fund_param
        st.session_state.benchmark = benchmark_param
        st.session_state.n_funds_final = n_funds_final_param
        st.session_state.bucket_quota = bucket_quota_param
        st.session_state.rf_rate = rf_rate_annual
        st.rerun()
    
    # 分析が実行されていない場合は待機
    if not st.session_state.run_analysis:
        st.stop()
    months = st.session_state.months
    core_fund = st.session_state.core_fund
    benchmark = st.session_state.benchmark
    n_funds_final = st.session_state.n_funds_final
    bucket_quota = st.session_state.get('bucket_quota', None)
    rf_rate = st.session_state.get('rf_rate', 0.005)  # デフォルト0.5%

    # ── 実際の分析用データ準備（期間アンカー方式）────────────────────────
    # pct_change() で先頭1行が NaN になるため months+1 行の価格を取得する
    df_filtered = df_price.iloc[-(months + 1):].copy()

    # ── STEP1: コア期間を確定（アンカー）──────────────────────────────────
    # pct_change後の先頭NaN行を除去し、コアファンドがnotnaの行のみに絞ることで
    # 「選択した期間 = months ヶ月」を正確に固定する。
    # 【修正前の問題】 pct_change().dropna() は how='any'（デフォルト）のため、
    #   valid_funds の中で設定来の最も短いファンドの開始日に全体が切り詰められた。
    #   例: 15年選択でも150ヶ月しかないファンドが1本混在すれば全体が150ヶ月になる。
    _df_pct_all = df_filtered[fund_cols].pct_change().iloc[1:]   # 先頭NaN行を除去
    _core_mask  = _df_pct_all[core_fund].notna()                 # コア有効期間マスク
    _df_core    = _df_pct_all[_core_mask]                        # コア期間ベース（months行）

    # ── STEP2: コア期間内の欠損率でファンドをフィルタ ──────────────────────
    # 欠損率の計算基準を「df_filtered全体」→「コア期間(_df_core)」に変更。
    # これにより「コア期間内に欠損がないファンドのみ」を valid_funds とすることで
    # returns_selected.dropna() でも期間が切れないことを保証する。
    # 閾値: 0（コア期間内で1行でも欠損があれば除外）
    #   → 分析期間より設定来が短いファンドは明示的に除外される
    missing_rates = _df_core[fund_cols].isnull().sum() / len(_df_core)
    valid_funds   = missing_rates[missing_rates == 0].index.tolist()

    # コアファンドが除外されてしまった場合のフォールバック（安全策）
    if core_fund not in valid_funds:
        valid_funds = [core_fund] + [
            f for f in missing_rates[missing_rates < 0.2].index if f != core_fund
        ]

    df_returns = _df_core[valid_funds]   # コア期間でアンカー済み・NaN列排除済み

    # Section 5: 除外ファンド一覧を開示
    _excluded = missing_rates[missing_rates > 0]
    if len(_excluded) > 0:
        with st.expander(
            f"⚠️ 分析期間内にデータ不足のため {len(_excluded)} 本のファンドを除外しました（クリックで詳細）",
            expanded=False
        ):
            st.markdown(
                '<div class="health-warn" style="margin-bottom:8px;">'
                '選択した分析期間より設定来が短いファンドは除外しています。'
                '分析期間を短くするか、十分なデータ期間を持つファンドを追加してください。'
                '</div>',
                unsafe_allow_html=True
            )
            st.dataframe(
                _excluded.rename("欠損率").to_frame().style.format("{:.1%}"),
                use_container_width=True
            )

    # スクリーニング実行
    screener = FundScreener(df_returns)
    selected_funds = screener.screen_funds(
        core_fund,
        n_funds_final,
        bucket_quota=bucket_quota
    )

    # S-02 修正：コアファンドがキャッシュ類似と判定された場合、UIで明示的に警告を表示
    _core_cash_msg = getattr(screener, '_core_is_cash_warning', None)
    if _core_cash_msg:
        st.warning(f"⚠️ {_core_cash_msg}")

    # ── バケット別スクリーニング結果の表示 ──────────────────────────────────
    _report = getattr(screener, 'screening_report', None)
    if _report:
        with st.expander("🔍 バケット別スクリーニング結果（クリックで詳細）", expanded=False):
            st.markdown(
                '<div style="font-size:0.75rem;color:#1e3a5f;font-weight:700;margin-bottom:8px;">'
                f'事前フィルター通過: {_report["pre_filter_pool"]}本 → 最終選定: {_report["total_selected"]}本（コア除く）'
                '</div>',
                unsafe_allow_html=True
            )
            _bkt_rows = []
            for bname, bstat in _report['buckets'].items():
                _bkt_rows.append({
                    'バケット':  bname,
                    '役割':      bstat.get('role', ''),
                    '候補数':    bstat.get('pool_size', 0),
                    '割当枠':    bstat.get('quota', '補完'),
                    '選定数':    bstat.get('selected', 0),
                })
            st.dataframe(
                pd.DataFrame(_bkt_rows).set_index('バケット'),
                use_container_width=True
            )
    
    fund_stats = screener.get_statistics(selected_funds)
    
    # 選定ファンドをセッションに保存（テーブル色分け更新用）
    st.session_state['selected_funds_after_run'] = selected_funds
    
    st.success(f"✅ {len(selected_funds)}本のファンドを選定しました")
    
    # ── 選定ファンド統計（サイドバーチェックで制御）────────────
    if st.session_state.get('show_fund_stats', False):
        st.markdown('<div class="section-header">📋 選定ファンド 詳細統計</div>', unsafe_allow_html=True)
        try:
            _sel_raw = overview_raw.loc[
                [f for f in selected_funds if f in overview_raw.index]
            ].copy()
            _sel_raw['コア相関(分析期間)'] = fund_stats.get('コア相関', pd.Series(dtype=float))
            _styled_sel = style_overview_table(_sel_raw, core_fund, selected_funds)
            st.dataframe(_styled_sel, use_container_width=True)
            st.caption("🔵コアファンド　🟡選定ファンド。")
        except Exception:
            display_stats = fund_stats.copy()
            display_stats['年率リターン'] = (display_stats['年率リターン'] * 100).round(2)
            display_stats['年率ボラ'] = (display_stats['年率ボラ'] * 100).round(2)
            display_stats['最大DD'] = (display_stats['最大DD'] * 100).round(2)
            display_stats = display_stats.round(3)
            st.dataframe(display_stats, use_container_width=True)
    
    # ポートフォリオ最適化
    if st.session_state.get('show_diagnosis', False):
        st.markdown("""
<div style="background:linear-gradient(135deg,#0f172a 0%,#1e3a5f 100%);
            border-radius:6px;border:1px solid rgba(179,144,74,0.3);
            padding:14px 22px;margin:1.6rem 0 0.6rem 0;
            display:flex;align-items:center;gap:14px;
            box-shadow:0 1px 4px rgba(0,0,0,0.08);">
  <div style="background:linear-gradient(135deg,#b3904a,#8a6a30);border-radius:6px;
              width:34px;height:34px;display:flex;align-items:center;justify-content:center;
              font-size:17px;flex-shrink:0;box-shadow:0 2px 8px rgba(179,144,74,0.4);">🎯</div>
  <div style="font-size:0.95rem;font-weight:800;color:#d4af6a;letter-spacing:0.04em;line-height:1.2;">
    5段階リスクプロファイル別ポートフォリオ
  </div>
</div>
""", unsafe_allow_html=True)
    
    # 選定ファンドのリターンデータ（③ selected後に dropna で NaN行を除去）
    # selected_funds はスクリーニングで有効データが確認済みのため、
    # ここで dropna しても periods_months は months と一致するはず
    returns_selected = df_returns[selected_funds].dropna()
    analyzer = PortfolioAnalyzer(returns_selected, use_ledoit_wolf=_use_lw)
    
    # 最適化設定（各プロファイルで明確に異なる特性）
    optimization_configs = {
        "積極型": {
            "core_range": (0.20, 0.35),
            "objective": "max_cagr",      # CAGR最大化（μ-σ²/2）：複利成長率を直接最大化
            "max_individual": 0.30,
            "min_individual": 0.03,
            "target_volatility": None
        },
        "やや積極型": {
            "core_range": (0.35, 0.50),
            "objective": "sharpe",
            "max_individual": 0.25,
            "min_individual": 0.03,
            "target_volatility": None
        },
        "バランス型": {
            "core_range": (0.50, 0.65),
            "objective": "sharpe",
            "max_individual": 0.20,
            "min_individual": 0.03,
            "target_volatility": None
        },
        "やや保守型": {
            "core_range": (0.65, 0.80),
            "objective": "risk_adjusted", # λ=1.0に修正済み（旧1.5）
            "max_individual": 0.15,
            "min_individual": 0.03,
            "target_volatility": 0.08
        },
        "保守型": {
            "core_range": (0.80, 0.95),
            "objective": "volatility",
            "max_individual": 0.10,
            "min_individual": 0.02,
            "target_volatility": 0.06
        }
    }

    # O-04 修正：各プロファイルの下限可行性チェック。
    # コア最小値 + サテライト本数 × min_individual > 1.0 になると最適化が収束しない。
    # 問題がある場合は min_individual を自動調整し、警告を表示する。
    _n_satellite = len(selected_funds) - 1  # コア除いたサテライト本数
    for _pname, _pcfg in optimization_configs.items():
        _core_min = _pcfg["core_range"][0]
        _min_ind  = _pcfg["min_individual"]
        _feasibility = _core_min + _n_satellite * _min_ind
        if _feasibility > 1.0 + 1e-6:
            # 制約可行のための最大 min_individual を逆算
            _safe_min = max(0.0, (1.0 - _core_min) / _n_satellite - 1e-6)
            optimization_configs[_pname]["min_individual"] = _safe_min
            if st.session_state.get('show_min_adj_warning', False):
                st.warning(
                    f"⚠️ **{_pname}** の最小組入比率を自動調整しました。\n\n"
                    f"コア最小 {_core_min*100:.0f}% ＋ サテライト {_n_satellite} 本 × "
                    f"{_min_ind*100:.1f}% = {_feasibility*100:.1f}% > 100% となるため、"
                    f"min_individual を {_safe_min*100:.2f}% に変更しています。"
                )
    
    # 最適化関数（キャッシュ付き）
    @st.cache_data(show_spinner=False)
    def optimize_portfolios(_returns_selected, selected_funds_tuple, core_fund_name,
                            configs_key, _configs_dict, use_lw: bool = True):
        """
        各リスクプロファイルのポートフォリオを最適化

        Parameters:
        -----------
        _returns_selected : pd.DataFrame
            選定ファンドのリターンデータ（キャッシュ可能）
        selected_funds_tuple : tuple
            選定ファンドのタプル（キャッシュキー用）
        core_fund_name : str
            コアファンド名
        configs_key : str
            O-05 修正：_configs_dict はアンダースコアプレフィックスのため st.cache_data が
            ハッシュ化しない。最適化設定の変化を検知するため、設定を文字列化したキーを
            別引数として渡し、確実にキャッシュを無効化する。
        _configs_dict : dict
            プロファイル別の最適化設定
        use_lw : bool
            Ledoit-Wolf収縮共分散推定量を使用するか（キャッシュキーに含まれる）

        Returns:
        --------
        dict : プロファイル別のポートフォリオ
        """
        # 関数内でAnalyzerを作成（キャッシュ安定性のため）
        _analyzer = PortfolioAnalyzer(_returns_selected, use_ledoit_wolf=use_lw)
        
        # タプルをリストに戻す
        _selected_funds = list(selected_funds_tuple)
        _core_idx = _selected_funds.index(core_fund_name)  # 外側スコープの core_idx と区別
        
        # プロファイル定義（仕様書 Section 2.2 デザインシステムカラーと統一）
        profile_colors = {
            "積極型":     "#9b2c2c",
            "やや積極型": "#c05621",
            "バランス型": "#2f855a",
            "やや保守型": "#2b6cb0",
            "保守型":     "#2c5282",
        }
        
        portfolios = {}
        
        # 各プロファイルを最適化
        for profile_name, config in _configs_dict.items():
            weights = _analyzer.optimize_portfolio(
                _core_idx,
                config["core_range"],
                config["objective"],
                config["max_individual"],
                min_individual=config.get("min_individual", 0.03),
                target_volatility=config.get("target_volatility")
            )
            
            stats = _analyzer.calculate_portfolio_stats(weights)
            
            portfolios[profile_name] = {
                "weights": weights,
                "stats": stats,
                "config": {
                    "core_range": config["core_range"],
                    "max_individual": config["max_individual"],
                    "objective": config["objective"],
                    "color": profile_colors.get(profile_name, "#95a5a6")
                }
            }
        
        return portfolios
    
    # 最適化実行（キャッシュされるため、同じ入力では再計算されない）
    core_idx = selected_funds.index(core_fund)
    # O-05 修正：optimization_configs の内容をキー文字列化し、設定変更時にキャッシュを確実に無効化
    # rf_rate もキーに含め、無リスク金利変更時も再計算する
    _configs_cache_key = json.dumps(
        {k: {ck: str(cv) for ck, cv in v.items()} for k, v in optimization_configs.items()},
        sort_keys=True
    ) + f"|rf={rf_rate:.4f}|lw={_use_lw}"
    _opt_start = time.time()
    _opt_progress = st.empty()
    with st.spinner('各リスクプロファイルを最適化中...'):
        try:
            portfolios = optimize_portfolios(
                returns_selected,
                tuple(selected_funds),
                core_fund,
                _configs_cache_key,
                optimization_configs,
                use_lw=_use_lw,
            )
        except Exception as _opt_err:
            # Section 5: エラー種別「最適化収束失敗」
            st.markdown(
                f'<div class="health-warn">⚠️ <b>最適化が収束しませんでした</b>　'
                f'制約条件を緩和するか、分析期間を変更して再実行してください。'
                f'<br><span style="font-size:0.78rem;opacity:0.8;">詳細: {_opt_err}</span></div>',
                unsafe_allow_html=True
            )
            st.stop()

    _opt_elapsed = time.time() - _opt_start
    # Section 5: 計算時間超過の通知（30秒超）
    if _opt_elapsed > 30:
        st.markdown(
            f'<div style="background:#eff6ff;border:1px solid #93c5fd;border-left:4px solid #1d4ed8;'
            f'border-radius:6px;padding:9px 14px;font-size:0.8rem;color:#1e3a8a;margin-bottom:10px;">'
            f'ℹ️ 計算に {_opt_elapsed:.0f} 秒かかりました。ファンド数を減らすと高速化できます。</div>',
            unsafe_allow_html=True
        )
    _opt_progress.empty()

    # ─── [改善E] LW / 生データ 切替インフォバー ────────────────────────────
    if _use_lw and analyzer._cov_shrinkage is not None:
        st.markdown(
            f'<div style="background:#eff6ff;border:1px solid #93c5fd;'
            f'border-left:4px solid #1d4ed8;border-radius:6px;'
            f'padding:8px 14px;font-size:0.8rem;color:#1e3a8a;margin-bottom:8px;">'
            f'🔬 <b>Ledoit-Wolf収縮共分散推定量を使用中</b>　'
            f'収縮係数: <b>{analyzer._cov_shrinkage:.4f}</b>　'
            f'（0に近いほど生データに近い、1に近いほど強く収縮）　'
            f'サイドバーのチェックを外すと生データ版（説明性重視）に切り替わります。'
            f'</div>',
            unsafe_allow_html=True,
        )
    elif _use_lw and analyzer._cov_shrinkage is None:
        # ⑥ LW=ON だが失敗した場合の明示警告（原因メッセージを表示）
        _lw_err_msg = getattr(analyzer, '_lw_error', None)
        if _lw_err_msg and 'scikit-learn がインストールされていません' in _lw_err_msg:
            # 最も多いケース: requirements.txt に未記載でデプロイ環境に sklearn がない
            st.warning(
                "⚠️ **scikit-learn が見つかりません**　"
                "サンプル共分散行列（生データ）で代替しています。  \n"
                "requirements.txt に `scikit-learn>=1.0.0` を追加して再デプロイすると "
                "Ledoit-Wolf 推定量が有効になります。"
            )
        else:
            _err_detail = _lw_err_msg or "詳細不明"
            st.warning(
                f"⚠️ **Ledoit-Wolf 推定に失敗しました**　"
                "サンプル共分散行列（生データ）にフォールバックしています。  \n"
                f"原因: `{_err_detail}`"
            )
    elif not _use_lw:
        st.markdown(
            '<div style="background:#fefce8;border:1px solid #fde047;'
            'border-left:4px solid #ca8a04;border-radius:6px;'
            'padding:8px 14px;font-size:0.8rem;color:#713f12;margin-bottom:8px;">'
            '📊 <b>生データ（サンプル共分散行列）を使用中</b>　'
            '観測値をそのまま使用するため説明性・透明性が高い一方、'
            '短期データでは推定誤差が大きくなる場合があります。'
            '</div>',
            unsafe_allow_html=True,
        )

    # ─── comparison_df：最適化直後にタブスコープ外で定義 ──────────
    # U-04 修正：_rpt_tab1 内で定義すると、タブが描画されなかった場合に
    # Excelエクスポート処理で NameError が発生するため、ここで事前計算する。
    #
    # 数値ベース統一：すべての列を float/int で保持し、表示フォーマットは
    # 参照側（st.dataframe の column_config や Excel 出力）に委ねる。
    # 旧実装は "12.34%" 形式の文字列を生成し、Excel 出力時に
    # .replace('%','') で逆変換していたため、書式変更で無言に壊れるリスクがあった。
    _comparison_data = []
    for _cpname, _cpf in portfolios.items():
        _cps = _cpf["stats"]
        _cpw = _cpf["weights"]
        _comparison_data.append({
            "プロファイル":  _cpname,
            "年率リターン":  round(_cps["年率リターン"]      * 100, 2),   # float %
            "年平均リスク":  round(_cps["年率ボラティリティ"] * 100, 2),   # float %
            "シャープ":      round(_cps["シャープレシオ"],          3),    # float
            "ソルティノ":    round(_cps["ソルティノレシオ"],         3),    # float
            "最大DD":        round(_cps["最大ドローダウン"]   * 100, 2),   # float % (負値)
            "カルマー":      round(_cps["カルマー比率"],            3),    # float
            "コア比率":      round(float(_cpw[core_idx])     * 100, 1),   # float %
            "ファンド数":    int((_cpw > 0.01).sum()),                     # int
        })
    comparison_df = pd.DataFrame(_comparison_data)

    # ── 表示用フォーマット辞書（st.dataframe の column_config で使用）──────
    _comparison_col_cfg = {
        "年率リターン": st.column_config.NumberColumn("年率リターン(%)", format="%+.2f%%"),
        "年平均リスク": st.column_config.NumberColumn("年平均リスク(%)", format="%.2f%%"),
        "シャープ":     st.column_config.NumberColumn("シャープ",        format="%.3f"),
        "ソルティノ":   st.column_config.NumberColumn("ソルティノ",       format="%.3f"),
        "最大DD":       st.column_config.NumberColumn("最大DD(%)",        format="%.2f%%"),
        "カルマー":     st.column_config.NumberColumn("カルマー",         format="%.3f"),
        "コア比率":     st.column_config.NumberColumn("コア比率(%)",      format="%.1f%%"),
        "ファンド数":   st.column_config.NumberColumn("ファンド数",       format="%d本"),
    }


    # ─── 健全性チェック ＋ コアファンド情報バー（診断パネル）────────
    if st.session_state.get('show_diagnosis', False):
        aggressive_vol   = portfolios['積極型']['stats']['年率ボラティリティ']
        conservative_vol = portfolios['保守型']['stats']['年率ボラティリティ']
        core_stats_fs    = fund_stats.loc[core_fund]
        core_sharpe      = core_stats_fs['シャープレシオ']
        core_volatility  = core_stats_fs['年率ボラ']
        core_return      = core_stats_fs['年率リターン']

        # ── 単調性チェック：保守→積極の順にリターン↑・ボラ↑が成立するか確認 ──
        # elif 連鎖ではなく独立した if で評価し、複数の問題を同時に表示できるようにする
        _p_order = ["保守型", "やや保守型", "バランス型", "やや積極型", "積極型"]
        _vols    = [portfolios[p]['stats']['年率ボラティリティ'] for p in _p_order]
        _rets    = [portfolios[p]['stats']['年率リターン']       for p in _p_order]
        _srs     = [portfolios[p]['stats']['シャープレシオ']     for p in _p_order]

        _mono_vol_ok = all(_vols[i] <= _vols[i+1] for i in range(len(_vols)-1))
        _mono_ret_ok = all(_rets[i] <= _rets[i+1] for i in range(len(_rets)-1))

        # ボラティリティ単調性違反があるプロファイルペアを特定
        _vol_violations = [
            f"{_p_order[i]}({_vols[i]*100:.1f}%) > {_p_order[i+1]}({_vols[i+1]*100:.1f}%)"
            for i in range(len(_vols)-1) if _vols[i] > _vols[i+1]
        ]
        _ret_violations = [
            f"{_p_order[i]}({_rets[i]*100:.1f}%) > {_p_order[i+1]}({_rets[i+1]*100:.1f}%)"
            for i in range(len(_rets)-1) if _rets[i] > _rets[i+1]
        ]
        # シャープレシオ：バランス型が最も高効率であるべきという期待に反するケースを検出
        # 保守型のシャープがバランス型を大きく上回る場合、コアが効率的すぎてサテライトが足を引っ張っている
        _bal_idx  = _p_order.index("バランス型")
        _cons_idx = _p_order.index("保守型")
        _sr_bal_vs_cons_warn = (
            _srs[_cons_idx] > _srs[_bal_idx] + 0.1  # 0.1超の差で警告（軽微な逆転はノイズのため無視）
        )

        _any_warn = False

        if not _mono_vol_ok:
            _any_warn = True
            _viol_str = "　/　".join(_vol_violations)
            st.markdown(
                f'<div class="health-warn">⚠️ <b>ボラティリティの逆転</b>　'
                f'保守→積極の順にリスクが増加すべきところ、以下のプロファイル間で逆転しています。<br>'
                f'<span style="font-size:0.8rem;">{_viol_str}</span><br>'
                f'コアファンドの変更またはスクリーニング条件の調整をご検討ください。</div>',
                unsafe_allow_html=True
            )

        if not _mono_ret_ok:
            _any_warn = True
            _viol_str = "　/　".join(_ret_violations)
            st.markdown(
                f'<div class="health-warn">⚠️ <b>リターンの逆転</b>　'
                f'保守→積極の順にリターンが増加すべきところ、以下のプロファイル間で逆転しています。<br>'
                f'<span style="font-size:0.8rem;">{_viol_str}</span><br>'
                f'サテライトファンドの質（シャープレシオ）をご確認ください。</div>',
                unsafe_allow_html=True
            )

        if _sr_bal_vs_cons_warn:
            _any_warn = True
            st.markdown(
                f'<div class="health-warn">⚠️ <b>シャープレシオの逆転</b>　'
                f'保守型（{_srs[_cons_idx]:.2f}）のリスク効率がバランス型（{_srs[_bal_idx]:.2f}）を大きく上回っています。<br>'
                f'サテライトファンドがポートフォリオ効率を低下させている可能性があります。'
                f'スクリーニング条件の見直しをご検討ください。</div>',
                unsafe_allow_html=True
            )

        if core_sharpe < 0.5:
            _any_warn = True
            st.markdown(
                f'<div class="health-warn">⚠️ <b>コアファンドの効率性</b>　シャープレシオ {core_sharpe:.2f} は目安（0.5）を下回っています。'
                f'別のファンドをコアとすることで全体効率が改善する可能性があります。</div>',
                unsafe_allow_html=True
            )

        if not _any_warn:
            st.markdown(
                f'<div class="health-ok">✅ <b>ポートフォリオは健全です</b>　'
                f'保守→積極の順にリスク・リターンが単調増加しています。'
                f'コアファンドのシャープレシオ（{core_sharpe:.2f}）も良好です。</div>',
                unsafe_allow_html=True
            )

        _ret_sign = "+" if core_return >= 0 else ""
        st.markdown(
            f'<div class="core-bar">'
            f'<span class="core-bar-label">★ コアファンド</span>'
            f'<span class="core-bar-name">{core_fund}</span>'
            f'<span style="color:#dde3ea">|</span>'
            f'<span class="core-bar-item">年率リターン <b style="color:{"#1e8449" if core_return>=0 else "#c0392b"}">{_ret_sign}{core_return*100:.1f}%</b></span>'
            f'<span class="core-bar-item">ボラ <b>{core_volatility*100:.1f}%</b></span>'
            f'<span class="core-bar-item">シャープ <b style="color:{"#1e8449" if core_sharpe>=1 else "#d35400"}">{core_sharpe:.2f}</b></span>'
            f'<span class="core-bar-item">最大DD <b style="color:#c0392b">{core_stats_fs["最大DD"]*100:.1f}%</b></span>'
            f'<span style="color:#dde3ea">|</span>'
            f'<span class="core-bar-item" style="color:#7a5c00;">無リスク金利 <b>{rf_rate*100:.1f}%</b></span>'
            f'</div>',
            unsafe_allow_html=True
        )
    else:
        # 変数は後続処理（コアバー in tab2等）でも参照されるため計算だけ実施
        core_stats_fs   = fund_stats.loc[core_fund]
        core_sharpe     = core_stats_fs['シャープレシオ']
        core_volatility = core_stats_fs['年率ボラ']
        core_return     = core_stats_fs['年率リターン']

    # ─── プロファイルカード ───────────────────────────────────
    # ─── 統合レポートパネル（3タブ構成: 比較/構成/リスク・リターン）──────

    # ── 全プロファイルの実績を事前集計（解説文の比較ロジックに使用） ────
    _profile_order_list = ["積極型", "やや積極型", "バランス型", "やや保守型", "保守型"]
    _all_stats = {}
    for _pn in _profile_order_list:
        _ps = portfolios[_pn]["stats"]
        _pw = portfolios[_pn]["weights"]
        _all_stats[_pn] = {
            "ret":  _ps["年率リターン"] * 100,
            "vol":  _ps["年率ボラティリティ"] * 100,
            "sr":   _ps["シャープレシオ"],
            "dd":   _ps["最大ドローダウン"] * 100,   # 負値
            "core": _pw[core_idx] * 100,
        }

    # 各指標の順位を算出（同率は最小順位を使用）
    def _rank_asc(key):
        """値が小さいほど順位1（ボラ・DD絶対値など"低いほど良い"指標用）"""
        vals = sorted(_all_stats.items(), key=lambda x: x[1][key])
        return {p: i + 1 for i, (p, _) in enumerate(vals)}
    def _rank_desc(key):
        """値が大きいほど順位1（リターン・シャープなど"高いほど良い"指標用）"""
        vals = sorted(_all_stats.items(), key=lambda x: x[1][key], reverse=True)
        return {p: i + 1 for i, (p, _) in enumerate(vals)}

    _rank_ret  = _rank_desc("ret")           # リターン高い＝1位
    _rank_sr   = _rank_desc("sr")            # シャープ高い＝1位
    _rank_vol  = _rank_asc("vol")            # ボラ低い＝1位
    _rank_dd   = _rank_desc("dd")            # DDは負値→大きい（-1%）＝1位（下落小さい）

    def _ordinal_jp(n):
        return ["最高", "2番目に高い", "3番目", "4番目", "最低"][n - 1]
    def _ordinal_risk_jp(n):
        return ["最小", "2番目に小さい", "中程度", "2番目に大きい", "最大"][n - 1]

    # ── 各プロファイルの解説文（全プロファイルの実績を比較して動的生成） ─────
    def _profile_commentary(pname, ret_, dd_, sr_, vol_, core_pct_):
        ret_sign  = "+" if ret_ >= 0 else ""
        r_ret  = _rank_ret[pname]
        r_sr   = _rank_sr[pname]
        r_vol  = _rank_vol[pname]
        r_dd   = _rank_dd[pname]   # 1=下落最小、5=下落最大

        # ── 第1文：リターンの位置づけ ──────────────────────────
        if r_ret == 1:
            sent1 = f"分析期間の年率リターンは{ret_sign}{ret_:.1f}%と、5プロファイル中最高でした。"
        elif r_ret == 5:
            sent1 = f"分析期間の年率リターンは{ret_sign}{ret_:.1f}%と、5プロファイル中最も低い水準でした。"
        else:
            sent1 = f"分析期間の年率リターンは{ret_sign}{ret_:.1f}%（5プロファイル中{_ordinal_jp(r_ret)}水準）でした。"

        # ── 第2文：下落（DD）の事実 ────────────────────────────
        if r_dd == 1:
            sent2 = f"分析期間中の最大下落率は{dd_:.1f}%と5プロファイル中最も小さく、下落局面での耐性が最も高い結果でした。"
        elif r_dd == 5:
            sent2 = f"分析期間中の最大下落率は{dd_:.1f}%と5プロファイル中最大で、価格変動が最も大きい構成です。"
        else:
            sent2 = f"分析期間中の最大下落率は{dd_:.1f}%（5プロファイル中{_ordinal_risk_jp(r_dd)}水準）でした。"

        # ── 第3文：シャープレシオの位置づけ ───────────────────
        if r_sr == 1:
            sent3 = f"リターン効率（シャープレシオ：{sr_:.2f}）は5プロファイル中最高で、リスクに対して最も効率的にリターンを獲得していました。"
        elif r_sr == 5:
            sent3 = f"リターン効率（シャープレシオ：{sr_:.2f}）は5プロファイル中最低でした。"
        else:
            sent3 = f"リターン効率（シャープレシオ：{sr_:.2f}）は5プロファイル中{_ordinal_jp(r_sr)}水準でした。"

        # ── 第4文：ポジショニングの一言 ───────────────────────
        if pname == "積極型":
            sent4 = "価格変動を受け入れながら長期成長を重視する場合の選択肢です。"
        elif pname == "やや積極型":
            sent4 = "高いリターンを求めながら、積極型よりも価格変動を抑えたい場合に位置します。"
        elif pname == "バランス型":
            cr_range = f"{int(portfolios[pname]['config']['core_range'][0]*100)}〜{int(portfolios[pname]['config']['core_range'][1]*100)}%"
            sent4 = f"コア比率{cr_range}でコアファンドの安定性とサテライトファンドの成長性を組み合わせた中間的な構成です。"
        elif pname == "やや保守型":
            sent4 = "大きな下落を避けながら、保守型よりもある程度のリターンを確保したい場合に位置します。"
        else:  # 保守型
            sent4 = "価格変動の安定を最優先とし、緩やかな成長を重視する場合の選択肢です。"

        return sent1 + sent2 + sent3 + sent4

    # ── 分析期間の特定（免責文言に使用） ────────────────────
    _period_start = returns_selected.index[0].strftime("%Y年%m月")
    _period_end   = returns_selected.index[-1].strftime("%Y年%m月")
    _period_months = len(returns_selected)

    # ── 統合レポートパネル出力 ─────────────────────────────────────
    st.markdown(
        f'<div class="report-panel-header">'
        f'<div class="report-panel-icon">📊</div>'
        f'<div>'
        f'<div class="report-panel-title">5プロファイル 比較分析レポート</div>'
        f'<div class="report-panel-meta">'
        f'分析期間: {_period_start}〜{_period_end}（{_period_months}ヶ月）　過去実績に基づく分析'
        f'</div>'
        f'</div></div>'
        f'<div class="report-panel-disclaimer">'
        f'<span style="flex-shrink:0;">⚠️</span>'
        f'<span>以下の数値はすべて'
        f'<b>{_period_start}〜{_period_end}（{_period_months}ヶ月）の分析期間における過去の実績</b>'
        f'です。将来の運用成果を保証するものではありません。</span>'
        f'</div>',
        unsafe_allow_html=True
    )

    _rpt_tab1, _rpt_tab2, _rpt_tab3 = st.tabs([
        "📊　比較サマリー",
        "📋　ファンド構成",
        "📈　リスク・リターン分析",
    ])

    with _rpt_tab1:
        # ── 選択状態の初期化（デフォルト：バランス型）────────────
        if "selected_card_profile" not in st.session_state:
            st.session_state["selected_card_profile"] = "バランス型"
        _sel = st.session_state["selected_card_profile"]

        cards_html = '<div class="profile-cards-wrap">'
        profile_order_list = ["積極型", "やや積極型", "バランス型", "やや保守型", "保守型"]
        for pname in profile_order_list:
            pf   = portfolios[pname]
            st_  = pf["stats"]
            w_   = pf["weights"]
            meta = _PROFILE_META.get(pname, {"color": "#555", "grad": "#555", "label_en": pname, "icon": ""})
            c_   = meta["color"]
            core_w_pct = w_[core_idx] * 100
            n_funds_   = int((w_ > 0.01).sum())
            ret_       = st_['年率リターン'] * 100
            vol_       = st_['年率ボラティリティ'] * 100
            sr_        = st_['シャープレシオ']
            dd_        = st_['最大ドローダウン'] * 100
            ret_sign   = "+" if ret_ >= 0 else ""
            sr_color   = "#1e8449" if sr_ >= 1.0 else ("#d35400" if sr_ >= 0.5 else "#c0392b")
            bar_w      = min(vol_ / 20 * 100, 100)
            donut_     = _donut_svg(core_w_pct, "rgba(255,255,255,0.9)")
            cr_min, cr_max = pf["config"]["core_range"]
            core_range_str = f"{int(cr_min*100)}–{int(cr_max*100)}%"

            # 選択中カードは強調ボーダー・チェックマーク付き
            is_sel     = (pname == _sel)
            card_style = (f"border-color:{c_}; box-shadow:0 0 0 3px {c_}55;"
                          if is_sel else f"border-color:{c_}40;")
            title_mark = " ✔" if is_sel else ""

            cards_html += (
                f'<div class="profile-card" style="{card_style}">'
                f'  <div class="profile-card-header" style="background:{meta["grad"]};">'
                f'    <div class="profile-card-eyebrow">{meta["label_en"].upper()}</div>'
                f'    <div class="profile-card-title">{pname}{title_mark}</div>'
                f'    <div class="profile-card-range">コア比率 {core_range_str}</div>'
                f'    <div class="profile-card-top">'
                f'      {donut_}'
                f'      <div style="text-align:right;">'
                f'        <div class="profile-card-ret">{ret_sign}{ret_:.1f}%</div>'
                f'        <div class="profile-card-ret-label">年率リターン（実績）</div>'
                f'      </div>'
                f'    </div>'
                f'  </div>'
                f'  <div class="profile-card-body">'
                f'    <div class="profile-card-row">'
                f'      <span class="profile-card-row-label">年平均リスク'
                f'        <span class="profile-card-row-label-sub">年間の価格変動幅の目安</span>'
                f'      </span>'
                f'      <span class="profile-card-row-val">{vol_:.1f}%</span>'
                f'    </div>'
                f'    <div class="profile-card-row">'
                f'      <span class="profile-card-row-label">シャープレシオ'
                f'        <span class="profile-card-row-label-sub">リターン効率（1.0超が目安）</span>'
                f'      </span>'
                f'      <span class="profile-card-row-val" style="color:{sr_color};">{sr_:.2f}</span>'
                f'    </div>'
                f'    <div class="profile-card-row">'
                f'      <span class="profile-card-row-label">最大DD（実績）'
                f'        <span class="profile-card-row-label-sub">分析期間中の最大下落率</span>'
                f'      </span>'
                f'      <span class="profile-card-row-val" style="color:#c0392b;">{dd_:.1f}%</span>'
                f'    </div>'
                f'    <div class="profile-card-row">'
                f'      <span class="profile-card-row-label">組入ファンド数'
                f'        <span class="profile-card-row-label-sub">分散の状況</span>'
                f'      </span>'
                f'      <span class="profile-card-row-val">{n_funds_}本</span>'
                f'    </div>'
                f'    <div class="risk-bar-wrap">'
                f'      <div style="font-size:0.70rem;color:#445563;margin-bottom:3px;">リスク水準</div>'
                f'      <div class="risk-bar-track">'
                f'        <div class="risk-bar-fill" style="width:{bar_w:.0f}%;background:{c_};"></div>'
                f'      </div>'
                f'      <div style="text-align:right;font-size:0.65rem;font-weight:700;color:{c_};margin-top:2px;">{vol_:.1f}%</div>'
                f'    </div>'
                f'  </div>'
                f'</div>'
            )
        cards_html += '</div>'
        st.markdown(cards_html, unsafe_allow_html=True)

        # ── プロファイル選択ボタン行 ──────────────────────────────
        _btn_cols = st.columns(5)
        for _bi, _bpname in enumerate(profile_order_list):
            _bmeta  = _PROFILE_META.get(_bpname, {"color": "#555"})
            _is_sel = (_bpname == st.session_state["selected_card_profile"])
            _label  = f"✔ {_bpname}" if _is_sel else _bpname
            with _btn_cols[_bi]:
                if st.button(
                    _label,
                    key=f"card_sel_{_bpname}",
                    use_container_width=True,
                    type="primary" if _is_sel else "secondary",
                ):
                    st.session_state["selected_card_profile"] = _bpname
                    st.rerun()

        # ── 選択プロファイルの解説パネル（カード群の下に1つだけ表示） ──
        _spname = st.session_state["selected_card_profile"]
        _spf    = portfolios[_spname]
        _spst   = _spf["stats"]
        _spw    = _spf["weights"]
        _sp_ret = _spst["年率リターン"] * 100
        _sp_vol = _spst["年率ボラティリティ"] * 100
        _sp_sr  = _spst["シャープレシオ"]
        _sp_dd  = _spst["最大ドローダウン"] * 100
        _sp_core = _spw[core_idx] * 100
        _spmeta = _PROFILE_META.get(_spname, {"color": "#555", "grad": "#555"})
        _sp_text = _profile_commentary(_spname, _sp_ret, _sp_dd, _sp_sr, _sp_vol, _sp_core)

        st.markdown(
            f'<div style="'
            f'background:#faf8f4;border:1px solid #e0dbd0;'
            f'border-left:5px solid {_spmeta["color"]};'
            f'border-radius:6px;padding:16px 22px;margin-top:4px;'
            f'font-size:0.92rem;font-weight:600;color:#2c3e50;line-height:1.95;">'
            f'<span style="font-size:1.0rem;font-weight:800;color:{_spmeta["color"]};margin-right:8px;">{_spname}</span>'
            f'{_sp_text}'
            f'</div>',
            unsafe_allow_html=True
        )

        # ── シャープレシオ凡例 ─────────────────────────────────────
        st.markdown(
            '<div class="sr-legend-wrap">'
            '<span>シャープレシオの目安：</span>'
            '<span class="sr-legend-chip" style="background:#e6f5ed;color:#1e7a4e;">🟢 1.0以上 ＝ 高効率</span>'
            '<span class="sr-legend-chip" style="background:#fff3e0;color:#c96a1a;">🟠 0.5〜1.0 ＝ 標準的</span>'
            '<span class="sr-legend-chip" style="background:#fde9e6;color:#c0392b;">🔴 0.5未満 ＝ 要確認</span>'
            '</div>',
            unsafe_allow_html=True
        )

        # ── [改善F] リスクパリティ カード（サイドバーチェック時のみ表示） ──
        if _show_rp:
            @st.cache_data(show_spinner=False)
            def _compute_risk_parity(_rets, _funds_tuple, _core_name, _lw: bool):
                """リスクパリティ最適化（バランス型設定で実行）"""
                _az  = PortfolioAnalyzer(_rets, use_ledoit_wolf=_lw)
                _ci  = list(_funds_tuple).index(_core_name)
                _w   = _az.optimize_portfolio(
                    _ci,
                    core_weight_range=(0.50, 0.65),  # バランス型と同一コア範囲
                    objective_type='risk_parity',
                    max_individual=0.20,
                    min_individual=0.03,
                )
                _st  = _az.calculate_portfolio_stats(_w)
                # サテライトのリスク寄与均等度を算出（情報表示用）
                _cov = _az.cov_matrix.values
                _vol = np.sqrt(_w @ _cov @ _w)
                _mrc = _cov @ _w
                _rc  = _w * _mrc / _vol if _vol > 1e-8 else np.zeros_like(_w)
                _non_core = np.array([i != _ci for i in range(len(_w))])
                _rc_sat   = _rc[_non_core]
                _rc_cv    = (_rc_sat.std() / _rc_sat.mean() * 100) if _rc_sat.mean() > 1e-8 else 0.0
                return _w, _st, float(_rc_cv)

            try:
                _rp_w, _rp_st, _rp_rc_cv = _compute_risk_parity(
                    returns_selected,
                    tuple(selected_funds),
                    core_fund,
                    _use_lw,
                )
                _rp_ret  = _rp_st['年率リターン'] * 100
                _rp_vol  = _rp_st['年率ボラティリティ'] * 100
                _rp_sr   = _rp_st['シャープレシオ']
                _rp_dd   = _rp_st['最大ドローダウン'] * 100
                _rp_core = _rp_w[core_idx] * 100
                _rp_nf   = int((_rp_w > 0.01).sum())
                _rp_ret_sign = "+" if _rp_ret >= 0 else ""
                _rp_sr_color = "#1e8449" if _rp_sr >= 1.0 else ("#d35400" if _rp_sr >= 0.5 else "#c0392b")
                _rp_donut    = _donut_svg(_rp_core, "rgba(255,255,255,0.9)")
                st.markdown(
                    '<div style="margin-top:16px;padding:6px 0 4px 0;'
                    'border-top:1px solid rgba(99,102,241,0.25);">'
                    '<span style="font-size:0.68rem;font-weight:800;letter-spacing:0.1em;'
                    'text-transform:uppercase;color:#6366f1;">⚖️ リスクパリティ配分（参考）</span>'
                    '<span style="font-size:0.65rem;color:#64748b;margin-left:8px;">'
                    'サテライトのリスク寄与を均等化した配分</span>'
                    '</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f'<div class="profile-cards-wrap">'
                    f'<div class="profile-card" style="border-color:#6366f140;max-width:260px;">'
                    f'  <div class="profile-card-header" style="background:linear-gradient(135deg,#4338ca,#6366f1);">'
                    f'    <div class="profile-card-eyebrow">RISK PARITY</div>'
                    f'    <div class="profile-card-title">リスクパリティ</div>'
                    f'    <div class="profile-card-range">コア比率 50–65%（バランス型と同一）</div>'
                    f'    <div class="profile-card-top">'
                    f'      {_rp_donut}'
                    f'      <div style="text-align:right;">'
                    f'        <div class="profile-card-ret">{_rp_ret_sign}{_rp_ret:.1f}%</div>'
                    f'        <div class="profile-card-ret-label">年率リターン（実績）</div>'
                    f'      </div>'
                    f'    </div>'
                    f'  </div>'
                    f'  <div class="profile-card-body">'
                    f'    <div class="profile-card-row">'
                    f'      <span class="profile-card-row-label">年平均リスク'
                    f'        <span class="profile-card-row-label-sub">年間の価格変動幅の目安</span>'
                    f'      </span>'
                    f'      <span class="profile-card-row-val">{_rp_vol:.1f}%</span>'
                    f'    </div>'
                    f'    <div class="profile-card-row">'
                    f'      <span class="profile-card-row-label">シャープレシオ'
                    f'        <span class="profile-card-row-label-sub">リターン効率（1.0超が目安）</span>'
                    f'      </span>'
                    f'      <span class="profile-card-row-val" style="color:{_rp_sr_color};">{_rp_sr:.2f}</span>'
                    f'    </div>'
                    f'    <div class="profile-card-row">'
                    f'      <span class="profile-card-row-label">最大DD（実績）'
                    f'        <span class="profile-card-row-label-sub">分析期間中の最大下落率</span>'
                    f'      </span>'
                    f'      <span class="profile-card-row-val" style="color:#c0392b;">{_rp_dd:.1f}%</span>'
                    f'    </div>'
                    f'    <div class="profile-card-row">'
                    f'      <span class="profile-card-row-label">リスク寄与CV（均等度）'
                    f'        <span class="profile-card-row-label-sub">低いほど均等（目標：0%）</span>'
                    f'      </span>'
                    f'      <span class="profile-card-row-val" style="color:#6366f1;">{_rp_rc_cv:.1f}%</span>'
                    f'    </div>'
                    f'    <div class="profile-card-row">'
                    f'      <span class="profile-card-row-label">組入ファンド数'
                    f'        <span class="profile-card-row-label-sub">分散の状況</span>'
                    f'      </span>'
                    f'      <span class="profile-card-row-val">{_rp_nf}本</span>'
                    f'    </div>'
                    f'  </div>'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                st.caption(
                    "⚖️ **リスクパリティ配分**：各サテライトファンドのリスク寄与（Risk Contribution）が"
                    "均等になるよう配分を決定します。「リスク寄与CV」が0%に近いほど均等化が実現されています。"
                    "コア比率はバランス型（50〜65%）と同一設定。バランス型との比較にご活用ください。"
                )
            except Exception as _rp_err:
                st.warning(f"⚠️ リスクパリティ最適化に失敗しました: {_rp_err}")

        # ─── 詳細メトリクスバッジ（全5プロファイル・サイドバーチェックで制御）──
        if st.session_state.get('show_profile_metrics', False):
            st.markdown('<div class="section-header">📐 全プロファイル 詳細指標</div>', unsafe_allow_html=True)
            for pname in profile_order_list:
                pf   = portfolios[pname]
                st_  = pf["stats"]
                w_   = pf["weights"]
                meta = _PROFILE_META.get(pname, {"color": "#555"})
                c_   = meta["color"]
                ret_ = st_['年率リターン'] * 100
                vol_ = st_['年率ボラティリティ'] * 100
                sr_  = st_['シャープレシオ']
                dd_  = st_['最大ドローダウン'] * 100
                so_  = st_['ソルティノレシオ']
                cm_  = st_['カルマー比率']
                cw_  = w_[core_idx] * 100
                mwr_ = st_['月次勝率'] * 100
                om_  = st_.get('Omega比率',  0.0)
                ul_  = st_.get('Ulcer指数',  0.0) * 100   # % 表示
                mr_  = st_.get('Martin比率', 0.0)
                gl_  = st_.get('GL比率',     0.0)
                ret_sign = "+" if ret_ >= 0 else ""
                sr_color = "#1e8449" if sr_ >= 1.0 else ("#d35400" if sr_ >= 0.5 else "#c0392b")
                st.markdown(f'<div style="font-size:0.78rem;font-weight:700;color:{c_};margin:10px 0 4px;">{pname}</div>', unsafe_allow_html=True)
                badges_html = (
                    '<div class="metric-badges-wrap">'
                    + _badge("年率リターン", f"{ret_sign}{ret_:.2f}%", "CAGR", c_)
                    + _badge("年平均リスク", f"{vol_:.2f}%",           "リスク水準", c_)
                    + _badge("シャープ",     f'<span style="color:{sr_color}">{sr_:.3f}</span>', "1.0以上が優秀", c_)
                    + _badge("ソルティノ",   f"{so_:.3f}",              "下方リスク調整", c_)
                    + _badge("最大DD",       f'<span style="color:#c0392b">{dd_:.2f}%</span>', "最悪ケース", c_)
                    + _badge("カルマー比率", f"{cm_:.3f}",              "DD比リターン", c_)
                    + _badge("Omega比率",    f"{om_:.3f}",              "利益/損失比率", c_)
                    + _badge("Ulcer指数",    f"{ul_:.2f}%",             "DD累積ペナルティ", c_)
                    + _badge("Martin比率",   f"{mr_:.3f}",              "リターン÷Ulcer", c_)
                    + _badge("GL比率",       f"{gl_:.3f}",              "平均利益÷平均損失", c_)
                    + _badge("コア比率",     f"{cw_:.1f}%",             "コアファンド", c_)
                    + _badge("月次勝率",     f"{mwr_:.1f}%",            "上昇月の割合", c_)
                    + '</div>'
                )
                st.markdown(badges_html, unsafe_allow_html=True)

        # comparison_df は最適化直後（タブスコープ外）で定義済み（U-04修正）
    
    with _rpt_tab2:
        st.markdown(
            f'<div class="core-bar">'
            f'<span class="core-bar-label">⭐ コアファンド</span>'
            f'<span class="core-bar-name">{core_fund}</span>'
            f'<span class="core-bar-item">（全プロファイル共通）</span>'
            f'</div>',
            unsafe_allow_html=True
        )
        st.markdown('<div class="tab-sub-header">プロファイル別 ファンド構成</div>', unsafe_allow_html=True)
    
        # 各プロファイルの投資比率を列として構築（転置形式）
        allocation_data = {}
    
        # 全ファンドでウェイトが1%以上あるものを収集
        funds_with_weights = set()
        for profile_name, portfolio in portfolios.items():
            w = portfolio["weights"]
            for i, fund in enumerate(selected_funds):
                if w[i] >= 0.01:
                    funds_with_weights.add(fund)
    
        # ファンドをキーとした辞書を作成
        for fund in selected_funds:
            if fund in funds_with_weights:
                allocation_data[fund] = {}
                for profile_name, portfolio in portfolios.items():
                    w = portfolio["weights"]
                    fund_idx = selected_funds.index(fund)
                    if w[fund_idx] >= 0.01:
                        allocation_data[fund][profile_name] = f"{w[fund_idx]*100:.1f}%"
                    else:
                        allocation_data[fund][profile_name] = ""
    
        # DataFrameを作成（行：ファンド、列：プロファイル）
        allocation_df = pd.DataFrame.from_dict(allocation_data, orient='index')

        # ── エクスポート用：数値ベース版を並行作成（%文字列の逆変換を不要にする）──
        allocation_data_numeric = {}
        for fund in selected_funds:
            if fund in funds_with_weights:
                allocation_data_numeric[fund] = {}
                for profile_name, portfolio in portfolios.items():
                    w = portfolio["weights"]
                    fund_idx = selected_funds.index(fund)
                    allocation_data_numeric[fund][profile_name] = (
                        round(w[fund_idx] * 100, 1) if w[fund_idx] >= 0.01 else 0.0
                    )
        allocation_df_numeric = pd.DataFrame.from_dict(allocation_data_numeric, orient='index')
        allocation_df_numeric = allocation_df_numeric[profile_order_list]
        allocation_df_numeric.index.name = "ファンド"
        if core_fund in allocation_df_numeric.index:
            _other = [f for f in allocation_df_numeric.index if f != core_fund]
            allocation_df_numeric = allocation_df_numeric.loc[[core_fund] + _other]
    
        # プロファイルの順序を指定（profile_order_list と統一）
        allocation_df = allocation_df[profile_order_list]
    
        # インデックス名を設定
        allocation_df.index.name = "ファンド"
    
        # コアファンドを最初に表示
        if core_fund in allocation_df.index:
            other_funds = [f for f in allocation_df.index if f != core_fund]
            allocation_df = allocation_df.loc[[core_fund] + other_funds]
    
        # スタイリング
        def highlight_core_row(row):
            """コアファンド行をハイライト"""
            if row.name == core_fund:
                return ['background-color: #fffacd; font-weight: bold' for _ in row]
            return ['' for _ in row]
    
        def highlight_profile_col(col):
            """各プロファイル列に色付け"""
            profile = col.name
            if profile in portfolios:
                color = portfolios[profile]['config']['color']
                return [f'background-color: {color}22' for _ in col]
            return ['' for _ in col]
    
        styled_allocation = allocation_df.style\
            .apply(highlight_core_row, axis=1)\
            .apply(highlight_profile_col, axis=0)\
            .set_properties(**{'text-align': 'center'})\
            .set_table_styles([
                {'selector': 'th.col_heading', 'props': 'text-align: center; font-weight: bold;'},
                {'selector': 'th.row_heading', 'props': 'text-align: left; font-weight: normal;'}
            ])
    
        st.dataframe(styled_allocation, use_container_width=True)
    
        st.caption("数値は投資比率（%）。1%未満は空欄。★コアファンド行はベージュ表示。各プロファイル列は対応カラーで色分け。")
        st.markdown('<hr style="border:none;border-top:1px solid #e8ecf0;margin:18px 0 14px 0;">', unsafe_allow_html=True)
        st.markdown('<div class="tab-sub-header">構成ファンド リスク・リターン サマリー</div>', unsafe_allow_html=True)

        # 表示対象：いずれかのプロファイルで1%以上配分されているファンド
        _constituent_funds = [
            f for f in selected_funds
            if any(portfolios[p]["weights"][selected_funds.index(f)] >= 0.01
                   for p in portfolios)
        ]

        # ── データ収集（数値はfloatのまま保持） ─────────────────────
        _summary_rows = []
        for _fund in _constituent_funds:
            _fi = selected_funds.index(_fund)

            # fund_stats（分析期間ベース）
            _fs         = fund_stats.loc[_fund]
            _ret_period = _fs['年率リターン'] * 100   # float % 値
            _vol_period = _fs['年率ボラ'] * 100        # float % 値
            _sharpe     = _fs['シャープレシオ']
            _corr_val   = _fs.get('コア相関', np.nan)

            # overview_raw（設定来データ）
            _ret_all  = np.nan
            _max_dd   = np.nan
            _win_rate = np.nan
            if _fund in overview_raw.index:
                _ov       = overview_raw.loc[_fund]
                _ret_all  = _ov.get('設定来リターン(年率)', np.nan)
                if pd.notna(_ret_all): _ret_all *= 100
                _max_dd   = _ov.get('最大DD(設定来)', np.nan)
                if pd.notna(_max_dd): _max_dd *= 100
                _win_rate = _ov.get('月次勝率', np.nan)
                if pd.notna(_win_rate): _win_rate *= 100

            _summary_rows.append({
                'ファンド'                  : _fund,
                'リターン\n分析期間(%)'    : _ret_period,
                'リターン\n設定来(%)'      : _ret_all,
                '年率リスク\n分析期間(%)'  : _vol_period,
                'シャープ\n分析期間'       : _sharpe,
                '最大DD\n設定来(%)'        : _max_dd,
                'コア相関\n分析期間'       : _corr_val,
                '月次勝率\n設定来(%)'      : _win_rate,
                '_ret_sort'                 : _ret_period,
                '_is_core'                  : (_fund == core_fund),
            })

        _summ_df = pd.DataFrame(_summary_rows).set_index('ファンド')

        # コアを先頭、残りはリターン降順
        _summ_df = pd.concat([
            _summ_df[_summ_df['_is_core']],
            _summ_df[~_summ_df['_is_core']].sort_values('_ret_sort', ascending=False)
        ]).drop(columns=['_ret_sort', '_is_core'])

        # ── 条件付き色分け（数値で比較） ─────────────────────────
        def _sc_row(row):
            if row.name == core_fund:
                return ['background-color: #dbeafe; font-weight: bold'] * len(row)
            return [''] * len(row)

        def _sc_ret(col):
            out = []
            for v in col:
                if pd.isna(v):       out.append('')
                elif v >= 10:        out.append('background-color: #86efac')
                elif v >= 3:         out.append('background-color: #bbf7d0')
                elif v >= 0:         out.append('background-color: #dcfce7')
                elif v >= -5:        out.append('background-color: #fee2e2')
                else:                out.append('background-color: #fca5a5')
            return out

        def _sc_sharpe(col):
            out = []
            for v in col:
                if pd.isna(v):      out.append('')
                elif v >= 1.0:      out.append('background-color: #bbf7d0')
                elif v >= 0.5:      out.append('background-color: #fef9c3')
                else:               out.append('background-color: #fee2e2')
            return out

        def _sc_dd(col):
            out = []
            for v in col:
                if pd.isna(v):      out.append('')
                elif v > -10:       out.append('background-color: #bbf7d0')
                elif v > -25:       out.append('background-color: #fef9c3')
                else:               out.append('background-color: #fee2e2')
            return out

        def _sc_corr(col):
            out = []
            for v in col:
                if pd.isna(v):              out.append('')
                elif 0.3 <= v <= 0.7:       out.append('background-color: #bbf7d0')
                elif 0.7 < v <= 0.9:        out.append('background-color: #fef9c3')
                elif v > 0.9:               out.append('background-color: #fca5a5')
                else:                       out.append('background-color: #f3f4f6')
            return out

        _disp_cols = [
            'リターン\n分析期間(%)', 'リターン\n設定来(%)',
            '年率リスク\n分析期間(%)', 'シャープ\n分析期間',
            '最大DD\n設定来(%)', 'コア相関\n分析期間', '月次勝率\n設定来(%)'
        ]

        _styled_summ = (
            _summ_df.style
            .apply(_sc_row, axis=1)
            .apply(_sc_ret,    subset=['リターン\n分析期間(%)', 'リターン\n設定来(%)'])
            .apply(_sc_sharpe, subset=['シャープ\n分析期間'])
            .apply(_sc_dd,     subset=['最大DD\n設定来(%)'])
            .apply(_sc_corr,   subset=['コア相関\n分析期間'])
            .format({
                'リターン\n分析期間(%)' : lambda v: f"{v:+.1f}%" if pd.notna(v) else "—",
                'リターン\n設定来(%)'   : lambda v: f"{v:+.1f}%" if pd.notna(v) else "—",
                '年率リスク\n分析期間(%)': lambda v: f"{v:.1f}%"  if pd.notna(v) else "—",
                'シャープ\n分析期間'    : lambda v: f"{v:.2f}"    if pd.notna(v) else "—",
                '最大DD\n設定来(%)'     : lambda v: f"{v:.1f}%"   if pd.notna(v) else "—",
                'コア相関\n分析期間'    : lambda v: f"{v:.2f}"    if pd.notna(v) else "—",
                '月次勝率\n設定来(%)'   : lambda v: f"{v:.0f}%"   if pd.notna(v) else "—",
            })
            .set_properties(**{'text-align': 'center', 'font-size': '0.82em', 'padding': '3px 6px'})
            .set_table_styles([
                {'selector': 'th.col_heading',
                 'props': 'text-align: center; font-size: 0.80em; white-space: pre-line; padding: 4px 6px;'},
                {'selector': 'th.row_heading',
                 'props': 'text-align: left; font-size: 0.80em;'},
            ])
        )

        # column_config で float 認識 & ソート可能にする
        _col_cfg = {
            'リターン\n分析期間(%)' : st.column_config.NumberColumn(
                "リターン\n分析期間(%)", format="%.1f%%", help="分析期間ベースの年率リターン"),
            'リターン\n設定来(%)'   : st.column_config.NumberColumn(
                "リターン\n設定来(%)",  format="%.1f%%", help="設定来（全期間）年率リターン"),
            '年率リスク\n分析期間(%)': st.column_config.NumberColumn(
                "年率リスク\n分析期間(%)", format="%.1f%%", help="分析期間ベースの年率ボラティリティ"),
            'シャープ\n分析期間'    : st.column_config.NumberColumn(
                "シャープ\n分析期間",   format="%.2f",   help="分析期間シャープレシオ（1.0超=優秀）"),
            '最大DD\n設定来(%)'     : st.column_config.NumberColumn(
                "最大DD\n設定来(%)",    format="%.1f%%", help="設定来最大ドローダウン"),
            'コア相関\n分析期間'    : st.column_config.NumberColumn(
                "コア相関\n分析期間",   format="%.2f",   help="コアファンドとの相関（0.3〜0.7が理想）"),
            '月次勝率\n設定来(%)'   : st.column_config.NumberColumn(
                "月次勝率\n設定来(%)",  format="%.0f%%", help="設定来月次プラス比率"),
        }

        st.dataframe(
            _summ_df,
            use_container_width=True,
            column_config=_col_cfg,
        )
        st.caption(
            f"🔵 コアファンド「{core_fund}」行は青ハイライト（column_configによりソート可能）。"
            "　リターン: +10%超=濃緑 / +3〜10%=緑 / 0〜3%=薄緑 / マイナス=赤。"
            "　シャープ: 🟢1.0超 / 🟡0.5-1.0 / 🔴0.5未満。"
            "　最大DD: 🟢-10%以内 / 🟡-10〜-25% / 🔴-25%超。"
            "　コア相関: 🟢0.3-0.7=分散◎ / 🟡0.7-0.9=やや高 / 🔴0.9超=高相関 / 灰=低相関。"
            "　列ヘッダーをクリックで昇順/降順ソートが可能（数値として正しく並び替え）。"
        )
    with _rpt_tab3:
        st.markdown('<div class="tab-sub-header">リスク・リターン マップ（分析期間）</div>', unsafe_allow_html=True)
        col_chart, col_sr = st.columns([3, 2])

        with col_chart:
            fig_scatter = go.Figure()

            # 個別ファンドをグレーでプロット（背景）
            for fund in selected_funds:
                fund_ret = fund_stats.loc[fund, '年率リターン'] * 100
                fund_vol = fund_stats.loc[fund, '年率ボラ'] * 100
                fig_scatter.add_trace(go.Scatter(
                    x=[fund_vol], y=[fund_ret],
                    mode='markers',
                    marker=dict(size=6, color='#dde3ea', symbol='circle'),
                    showlegend=False,
                    hovertext=fund,
                    hovertemplate='%{hovertext}<br>ボラ: %{x:.1f}%<br>リターン: %{y:.1f}%<extra></extra>'
                ))

            # 各ポートフォリオをプロット
            for pname in profile_order_list:
                portfolio = portfolios[pname]
                stats     = portfolio["stats"]
                meta      = _PROFILE_META.get(pname, {"color": "#555"})
                fig_scatter.add_trace(go.Scatter(
                    x=[stats['年率ボラティリティ'] * 100],
                    y=[stats['年率リターン'] * 100],
                    mode='markers+text',
                    name=pname,
                    marker=dict(size=18, color=meta["color"],
                                line=dict(color='#fff', width=2)),
                    text=[pname],
                    textposition="top center",
                    textfont=dict(size=11, color=meta["color"]),
                    hovertemplate=(
                        f'<b>{pname}</b><br>'
                        'ボラ: %{x:.1f}%<br>リターン: %{y:.1f}%<extra></extra>'
                    )
                ))

            # ── 有効フロンティア（キャッシュ付き）────────────────────────
            @st.cache_data(show_spinner=False)
            def _cached_efficient_frontier(_rets, _funds_tuple, _lw: bool):
                """有効フロンティアをキャッシュ付きで計算"""
                _az = PortfolioAnalyzer(_rets, use_ledoit_wolf=_lw)
                return _az.calculate_efficient_frontier(n_points=35)

            try:
                _ef_df = _cached_efficient_frontier(
                    returns_selected, tuple(selected_funds), _use_lw
                ).dropna(subset=['ボラティリティ', 'リターン_CAGR'])  # 両列有効な点のみ描画
                if not _ef_df.empty:
                    # 実現系列ベースCAGRを直接参照（近似式 μ-σ²/2 の上振れバイアスを排除）
                    _ef_vols = _ef_df['ボラティリティ'].values
                    _ef_cagr = _ef_df['リターン_CAGR'].values
                    fig_scatter.add_trace(go.Scatter(
                        x=_ef_vols * 100,
                        y=_ef_cagr * 100,
                        mode='lines',
                        name='有効フロンティア',
                        line=dict(color='#b3904a', width=1.5, dash='dot'),
                        hovertemplate='有効フロンティア<br>ボラ: %{x:.1f}%<br>リターン(CAGR): %{y:.1f}%<extra></extra>',
                        showlegend=True
                    ))
            except Exception:
                pass  # フロンティア計算失敗時はサイレントスキップ

            fig_scatter.update_layout(
                # タイトルはタブサブヘッダー（上部 st.markdown）で表示済みのため fig 内では空文字
                # ※ title=None → "undefined" 表示バグ、font.size=0 → バリデーションエラーのため
                #    空文字＋pad=0＋top余白ゼロで実質非表示にする
                title=dict(text="", pad=dict(t=0, b=0)),
                xaxis_title="年平均リスク（ボラティリティ）%",
                yaxis_title="年率リターン %",
                hovermode='closest',
                height=400,
                plot_bgcolor='#fafbfc',
                paper_bgcolor='#ffffff',
                xaxis=dict(gridcolor='#e8ecf0', zeroline=False),
                yaxis=dict(gridcolor='#e8ecf0', zeroline=False),
                # legend を X軸タイトルと重ならないよう下マージンを広げて配置
                legend=dict(orientation='h', yanchor='top', y=-0.18, xanchor='center', x=0.5,
                            font=dict(size=10)),
                margin=dict(t=20, b=90, l=50, r=20)
            )
            st.plotly_chart(fig_scatter, use_container_width=True)

        with col_sr:
            st.markdown(
                '<div style="font-size:0.82rem;font-weight:700;color:#1e3a5f;margin-bottom:10px;">'
                'シャープレシオ比較<br>'
                '<span style="font-size:0.68rem;font-weight:400;color:#2f3e4d;">'
                'リスク1単位あたりのリターン効率</span></div>',
                unsafe_allow_html=True
            )

            # シャープレシオ降順でソート
            sr_sorted = sorted(
                [(pn, portfolios[pn]["stats"]["シャープレシオ"]) for pn in profile_order_list],
                key=lambda x: x[1], reverse=True
            )
            sr_max = max(v for _, v in sr_sorted) if sr_sorted else 1.5
            bars_html = '<div class="sr-compare-wrap">'
            for pn, sr in sr_sorted:
                meta   = _PROFILE_META.get(pn, {"color": "#555"})
                c_     = meta["color"]
                bar_w  = min(sr / max(sr_max * 1.1, 1.5) * 100, 100)
                sr_col = "#1e8449" if sr >= 1.0 else ("#d35400" if sr >= 0.5 else "#c0392b")
                bars_html += (
                    f'<div class="sr-compare-row">'
                    f'  <div class="sr-compare-header">'
                    f'    <span style="font-weight:600;color:{c_};">{pn}</span>'
                    f'    <span style="font-weight:800;color:{sr_col};">{sr:.3f}</span>'
                    f'  </div>'
                    f'  <div class="sr-compare-bar-track">'
                    f'    <div class="sr-compare-bar-fill" style="width:{bar_w:.0f}%;background:{c_};"></div>'
                    f'  </div>'
                    f'</div>'
                )
            bars_html += (
                '<div class="sr-note">'
                '💡 <b>シャープレシオの目安</b><br>'
                '🟢 1.0以上 ＝ 優秀（リスク効率が高い）<br>'
                '🟠 0.5〜1.0 ＝ 普通<br>'
                '🔴 0.5未満 ＝ 要改善<br><br>'
                '国内株式インデックスの長期平均：約0.4〜0.6'
                '</div>'
            )
            bars_html += '</div>'
            st.markdown(bars_html, unsafe_allow_html=True)
    # 詳細分析セクション（外側：プロファイルタブ）
    st.markdown('<div class="section-header">🔍 プロファイル別 詳細分析</div>', unsafe_allow_html=True)

    available_profiles = list(portfolios.keys())
    if not available_profiles:
        st.error("ポートフォリオの生成に失敗しました。パラメータを調整してください。")
        st.stop()

    _profile_label = {
        "積極型":     "🔴 積極型",
        "やや積極型": "🟠 やや積極型",
        "バランス型": "🟡 バランス型",
        "やや保守型": "🟢 やや保守型",
        "保守型":     "🔵 保守型",
    }

    _outer_tabs = st.tabs([_profile_label.get(p, p) for p in available_profiles])

    for _outer_tab, _profile_name in zip(_outer_tabs, available_profiles):
        with _outer_tab:
            try:
                _w = portfolios[_profile_name]["weights"]
                _s = portfolios[_profile_name]["stats"]
                if not isinstance(_w, np.ndarray):
                    _w = np.array(_w)
                if _w.shape[0] != len(selected_funds):
                    st.error(f"ポートフォリオの次元が不正: {_w.shape[0]} != {len(selected_funds)}")
                    continue
                render_profile_detail(
                    _profile_name, _w, _s,
                    returns_selected=returns_selected,
                    selected_funds=selected_funds,
                    df_filtered=df_filtered,
                    df_price=df_price,
                    benchmark=benchmark,
                    core_fund=core_fund,
                    core_idx=core_idx,
                    fund_stats=fund_stats,
                    df_returns=df_returns,
                    portfolios=portfolios,
                    period_start=_period_start,
                    period_end=_period_end,
                    period_months=_period_months,
                    analyzer=analyzer,
                )
            except Exception as _e:
                st.error(f"ポートフォリオデータの取得に失敗: {_e}")

    # エクスポート機能
    st.markdown('<div class="section-header">💾 結果のエクスポート</div>', unsafe_allow_html=True)
    
    if st.button("📥 Excelファイルをダウンロード"):
        # 結果をまとめる
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # ポートフォリオ比較
            # comparison_df はすべて数値型で保持されているため変換不要。
            # Excel 列名に単位を明示するためリネームのみ行う。
            _comp_export = comparison_df.rename(columns={
                "年率リターン": "年率リターン(%)",
                "年平均リスク": "年平均リスク(%)",
                "最大DD":       "最大DD(%)",
                "コア比率":     "コア比率(%)",
                "ファンド数":   "ファンド数(本)",
            })
            _comp_export.to_excel(writer, sheet_name='ポートフォリオ比較', index=False)

            # 統合ファンド構成（数値ベースの allocation_df_numeric を直接出力）
            allocation_df_numeric.to_excel(writer, sheet_name='統合ファンド構成(%)')

            # 各ポートフォリオの構成（個別シート）
            for profile_name, portfolio in portfolios.items():
                w = portfolio["weights"]
                weights_export = pd.DataFrame({
                    'ファンド': selected_funds,
                    '比重(%)': (w * 100).round(2)
                })
                weights_export = weights_export[weights_export['比重(%)'] > 0.1].sort_values('比重(%)', ascending=False)
                sheet_name = profile_name[:20]
                weights_export.to_excel(writer, sheet_name=sheet_name, index=False)

            # ファンド統計（コピーして%変換・元のDataFrameを破壊しない）
            fund_stats_export = fund_stats.copy()
            fund_stats_export['年率リターン'] = (fund_stats_export['年率リターン'] * 100).round(2)
            fund_stats_export['年率ボラ']     = (fund_stats_export['年率ボラ']     * 100).round(2)
            fund_stats_export['最大DD']       = (fund_stats_export['最大DD']       * 100).round(2)
            fund_stats_export.to_excel(writer, sheet_name='ファンド統計')
        
        output.seek(0)
        
        st.download_button(
            label="📥 ダウンロード",
            data=output,
            file_name=f"portfolio_analysis_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    # ─── 免責事項 ─────────────────────────────────────────────
    st.markdown(
        '<div class="disclaimer">'
        '【留意事項】本資料は情報提供を目的として作成したものであり、特定の投資信託の購入・売却を勧誘するものではありません。'
        '過去の運用実績は将来の成果を保証するものではありません。'
        '投資信託は値動きのある有価証券等に投資しますので、基準価格が変動し、投資元本を割り込むことがあります。'
        '　ヘッジファンドダイレクト株式会社　関東財務局長（金商）第532号'
        '</div>',
        unsafe_allow_html=True
    )

else:
    st.markdown("""
<div style="background:linear-gradient(160deg,#0a1929,#0f172a 70%,#0d1f3c);
            border:1px solid rgba(179,144,74,0.25);border-radius:16px;
            padding:32px 28px 28px;margin:8px 0 20px 0;
            box-shadow:0 1px 3px rgba(0,0,0,0.06);">

  <!-- ウェルカムメッセージ -->
  <div style="text-align:center;margin-bottom:28px;">
    <div style="font-size:2.8rem;margin-bottom:12px;">📊</div>
    <div style="font-size:1.1rem;font-weight:800;color:#d4af6a;letter-spacing:0.04em;margin-bottom:6px;">
      月次基準価格データをアップロードして分析を開始
    </div>
    <div style="font-size:0.75rem;color:rgba(255,255,255,0.4);max-width:480px;margin:0 auto;line-height:1.6;">
      Date列と各ファンドの月次基準価格を含む .xlsx ファイルをアップロードすると、
      コア・サテライト戦略に基づく5段階ポートフォリオ最適化が自動実行されます
    </div>
  </div>

  <!-- 3ステップ -->
  <div style="display:flex;gap:12px;margin-bottom:28px;flex-wrap:wrap;">
    <div style="flex:1;min-width:180px;background:rgba(255,255,255,0.04);border:1px solid rgba(179,144,74,0.15);
                border-radius:10px;padding:14px 16px;">
      <div style="font-size:0.6rem;font-weight:800;letter-spacing:0.12em;color:rgba(179,144,74,0.7);
                  margin-bottom:8px;">STEP 1</div>
      <div style="font-size:0.85rem;margin-bottom:4px;">📂 データアップロード</div>
      <div style="font-size:0.68rem;color:rgba(255,255,255,0.4);line-height:1.5;">
        月次基準価格の Excel ファイルを選択。3年以上・50本以上を推奨
      </div>
    </div>
    <div style="flex:1;min-width:180px;background:rgba(255,255,255,0.04);border:1px solid rgba(179,144,74,0.15);
                border-radius:10px;padding:14px 16px;">
      <div style="font-size:0.6rem;font-weight:800;letter-spacing:0.12em;color:rgba(179,144,74,0.7);
                  margin-bottom:8px;">STEP 2</div>
      <div style="font-size:0.85rem;margin-bottom:4px;">⚙️ 分析設定</div>
      <div style="font-size:0.68rem;color:rgba(255,255,255,0.4);line-height:1.5;">
        分析期間・ベンチマーク・コアファンドを選択して分析実行
      </div>
    </div>
    <div style="flex:1;min-width:180px;background:rgba(255,255,255,0.04);border:1px solid rgba(179,144,74,0.15);
                border-radius:10px;padding:14px 16px;">
      <div style="font-size:0.6rem;font-weight:800;letter-spacing:0.12em;color:rgba(179,144,74,0.7);
                  margin-bottom:8px;">STEP 3</div>
      <div style="font-size:0.85rem;margin-bottom:4px;">🎯 結果確認</div>
      <div style="font-size:0.68rem;color:rgba(255,255,255,0.4);line-height:1.5;">
        5段階プロファイル・詳細分析・Excel出力まで自動生成
      </div>
    </div>
  </div>

  <!-- リスクプロファイル一覧 -->
  <div style="border-top:1px solid rgba(179,144,74,0.15);padding-top:20px;">
    <div style="font-size:0.68rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;
                color:rgba(179,144,74,0.6);margin-bottom:12px;">5段階リスクプロファイル</div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;">
      <div style="flex:1;min-width:100px;background:linear-gradient(135deg,#9b2c2c,#7b1f1f);
                  border-radius:6px;padding:10px 12px;">
        <div style="font-size:0.62rem;font-weight:800;color:rgba(255,255,255,0.7);margin-bottom:2px;">コア 20-35%</div>
        <div style="font-size:0.82rem;font-weight:700;color:#fff;">▲▲ 積極型</div>
        <div style="font-size:0.62rem;color:rgba(255,255,255,0.5);margin-top:2px;">高リターン追求</div>
      </div>
      <div style="flex:1;min-width:100px;background:linear-gradient(135deg,#c05621,#9a4218);
                  border-radius:6px;padding:10px 12px;">
        <div style="font-size:0.62rem;font-weight:800;color:rgba(255,255,255,0.7);margin-bottom:2px;">コア 35-50%</div>
        <div style="font-size:0.82rem;font-weight:700;color:#fff;">▲ やや積極型</div>
        <div style="font-size:0.62rem;color:rgba(255,255,255,0.5);margin-top:2px;">リターン重視</div>
      </div>
      <div style="flex:1;min-width:100px;background:linear-gradient(135deg,#2f855a,#236644);
                  border-radius:6px;padding:10px 12px;">
        <div style="font-size:0.62rem;font-weight:800;color:rgba(255,255,255,0.7);margin-bottom:2px;">コア 50-65%</div>
        <div style="font-size:0.82rem;font-weight:700;color:#fff;">◆ バランス型</div>
        <div style="font-size:0.62rem;color:rgba(255,255,255,0.5);margin-top:2px;">シャープ最大化</div>
      </div>
      <div style="flex:1;min-width:100px;background:linear-gradient(135deg,#2b6cb0,#1e4f8a);
                  border-radius:6px;padding:10px 12px;">
        <div style="font-size:0.62rem;font-weight:800;color:rgba(255,255,255,0.7);margin-bottom:2px;">コア 65-80%</div>
        <div style="font-size:0.82rem;font-weight:700;color:#fff;">▼ やや保守型</div>
        <div style="font-size:0.62rem;color:rgba(255,255,255,0.5);margin-top:2px;">安定重視</div>
      </div>
      <div style="flex:1;min-width:100px;background:linear-gradient(135deg,#2c5282,#1e3a63);
                  border-radius:6px;padding:10px 12px;">
        <div style="font-size:0.62rem;font-weight:800;color:rgba(255,255,255,0.7);margin-bottom:2px;">コア 80-95%</div>
        <div style="font-size:0.82rem;font-weight:700;color:#fff;">▼▼ 保守型</div>
        <div style="font-size:0.62rem;color:rgba(255,255,255,0.5);margin-top:2px;">リスク最小化</div>
      </div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)
