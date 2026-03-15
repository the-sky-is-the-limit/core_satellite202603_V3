import streamlit as st
import pandas as pd
import numpy as np
# [BUG-H修正] go / px / datetime / _donut_svg / _badge を削除。
# ステージ1〜3リファクタでチャート描画・エクスポートを
# portfolio_charts / portfolio_report に移管した際の残留インポート。
# go / px はどの描画処理でも参照されていない。
# datetime は render_export_section（portfolio_report）に移管済み。
# _donut_svg / _badge は portfolio_report.py で import・使用されており
# portfolio_app.py での直接参照はない。
from portfolio_utils import PortfolioAnalyzer, FundScreener
from portfolio_charts import render_profile_detail, render_fund_drill_section
from portfolio_data import (
    load_fund_data,
    compute_fund_overview_table,
    build_overview_cache_key,
    prep_overview_df,
    make_overview_col_config,
    style_overview_table,
    CURRENCY_KEYWORDS,  # M-2: 通貨列フィルタは portfolio_data で一元管理
)
from portfolio_report import (
    build_report_data,
    render_report_panel,
    render_export_section,
    compute_rp_portfolio,
)
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
      <span style="font-size:0.78rem;font-weight:700;color:#1e3a5f;">分析実行</span>
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

    # データ読み込み（load_fund_data は portfolio_data で管理）
    try:
        df_price = load_fund_data(uploaded_file, _file_id)
    except Exception as _load_err:
        # Section 5: エラー種別「データ形式不正」
        st.markdown(
            f'<div class="health-warn">⚠️ <b>ファイル形式または列構成が想定と異なります</b>　'
            f'正しい列構成（Date列 + 各ファンドの月次NAV）の .xlsx ファイルを再アップロードしてください。'
            f'<br><span style="font-size:0.78rem;opacity:0.8;">詳細: {_load_err}</span></div>',
            unsafe_allow_html=True
        )
        st.stop()
    
    # 通貨列を除外（それ以外は全てファンド候補として扱う）
    # M-2: ローカル定義を廃止。portfolio_data.CURRENCY_KEYWORDS を参照することで
    #      test_app.py との定義乖離リスクを解消する。
    fund_cols = [col for col in df_price.columns 
                 if not any(curr in col for curr in CURRENCY_KEYWORDS)]
    
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
    # [BUG-E + ISSUE-7 統合修正]
    # Streamlit の session_state key 早期読み取りパターンを使い、
    # サイドバーの表示順序を保ちながら rf_rate の 1-run 遅延を解消する。
    #
    # Streamlit の動作原則:
    #   key= 付きウィジェットの値はスクリプト開始時点で
    #   session_state[key] に前回値として格納済みになる。
    #   よって「ウィジェットの描画（st.slider）より前」に
    #   session_state[key] を参照しても、前回のユーザー操作が反映された
    #   「現在値」を取得できる。
    #
    # → rf_rate スライダーに key='_rf_rate_slider' を付与しておき、
    #   キャッシュキー生成前に session_state から現在値を読む。
    #   スライダー自体はサイドバー本来の位置（詳細設定の後）で描画する。
    #   初回（key 未登録）はデフォルト 0.5% を使用。
    _rf_rate_param_early = st.session_state.get('_rf_rate_slider', 0.5)
    rf_rate_annual        = _rf_rate_param_early / 100.0
    st.session_state['rf_rate'] = rf_rate_annual

    with st.spinner("サマリーテーブルを計算中..."):
        _cache_key = build_overview_cache_key(df_price, months_param, rf_rate_annual)
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

    run_button = st.button("分析実行　— ポートフォリオ最適化を開始", type="primary", use_container_width=True)

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

    # ── 無リスク金利設定（シャープレシオ計算に使用）──────────────────
    # key='_rf_rate_slider' を付与することで、スクリプト先頭での
    # session_state 早期読み取りと同期する（ISSUE-7 / BUG-E 統合修正）。
    # 現在の金利環境（日本国債・米国債）を踏まえてデフォルト0.5%に設定。
    with st.sidebar.expander("📐 シャープレシオ設定", expanded=False):
        rf_rate_param = st.slider(
            "無リスク金利（年率%）",
            min_value=0.0, max_value=3.0, value=0.5, step=0.1,
            key='_rf_rate_slider',
            help="シャープレシオ計算時に控除する無リスク金利。日本国債利回りを目安に設定してください（デフォルト：0.5%）"
        )
    rf_rate_annual = rf_rate_param / 100.0  # 小数に変換（以降の処理用に上書き）
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

    # [改善F] リスクパリティ & テールリスク最小型の表示切替
    # チェックボックスひとつで両方を同時に表示/非表示する。
    _show_rp = st.sidebar.checkbox(
        "リスクパリティ / テールリスク最小型を表示",
        value=False,
        key="show_risk_parity",
        help=(
            "【リスクパリティ】\n"
            "バランス型のコア比率（50〜65%）を維持したまま、\n"
            "サテライト各ファンドのリスク寄与を均等化した配分を追加表示します。\n\n"
            "【テールリスク最小型】\n"
            "CVaR（ワースト5%月の平均損失）を直接最小化したプロファイルです。\n"
            "正規分布を前提としないため、ファットテール・左歪み分布の\n"
            "ヘッジファンドを正しく評価できます。\n"
            "超保守クライアント向けの参考プロファイルとしてご活用ください。"
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
            _perf_df    = prep_overview_df(overview_raw[_perf_avail])
            st.dataframe(
                _perf_df,
                column_config=make_overview_col_config(_perf_df.columns),
                use_container_width=True, height=400,
            )
            st.caption("💡 列ヘッダークリックでソート可。年率CAGR表示。🔵コアファンド行は凡例のみ（ハイライトは選定後）")

        with tab_risk:
            _risk_cols  = ['データ期間(年)', '設定来リターン(年率)', '設定来ボラ',
                           'シャープ(設定来)', '最大DD(設定来)', '月次勝率']
            _risk_avail = [c for c in _risk_cols if c in overview_raw.columns]
            _risk_df    = prep_overview_df(overview_raw[_risk_avail])
            st.dataframe(
                _risk_df,
                column_config=make_overview_col_config(_risk_df.columns),
                use_container_width=True, height=400,
            )
            st.caption("💡 列ヘッダークリックでソート可。最大DD：-10%以内が理想、-25%超は要注意。シャープ：1.0超が優秀。")

        with tab_corr:
            _corr_cols  = ['データ期間(年)', '設定来リターン(年率)', '設定来ボラ',
                           'コア相関(設定来)', f'コア相関({months_param//12}年)', '相関安定性(σ)']
            _corr_avail = [c for c in _corr_cols if c in overview_raw.columns]
            _corr_df    = prep_overview_df(overview_raw[_corr_avail])
            st.dataframe(
                _corr_df,
                column_config=make_overview_col_config(_corr_df.columns),
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
    # [BUG-D修正] 旧実装は missing_rates < 0.2 に閾値を緩和していたため、
    # 欠損月を持つファンドが valid_funds に混入し、
    # 後段の returns_selected.dropna() で分析期間が意図より短縮されるリスクがあった。
    # 修正後：コアは強制追加しつつ、サテライトは欠損ゼロ基準を維持する。
    # これにより欠損ファンド混入を防ぎながら、コアのフォールバックを確保できる。
    if core_fund not in valid_funds:
        valid_funds = [core_fund] + [
            f for f in missing_rates[missing_rates == 0].index if f != core_fund
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
    # [BUG-F修正] rf_rate を渡し、シャープレシオ計算をサイドバー設定と統一
    screener = FundScreener(df_returns, risk_free_rate=rf_rate)
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
        # [改善A3] キャッシュヒット時はタイトルにインジケータを表示
        _cache_hit = getattr(screener, '_stats_cache_hit', False)
        _cache_badge = " ⚡ 統計キャッシュ使用" if _cache_hit else ""
        with st.expander(f"🔍 バケット別スクリーニング結果（クリックで詳細）{_cache_badge}", expanded=False):
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
    # M-1: risk_free_rate を渡すことで LW インフォバーのシャープレシオを
    #      FundScreener・optimize_portfolios と同一基準に統一する
    analyzer = PortfolioAnalyzer(
        returns_selected, risk_free_rate=rf_rate, use_ledoit_wolf=_use_lw
    )
    
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
        },
        # ── [改善B1] テールリスク最小型プロファイル ─────────────────────────
        # CVaR(95%)を直接最小化。正規分布を仮定しないため、ヘッジファンドに多い
        # ファットテール・左歪み分布（売りオプション系・CTA等）を正しく評価できる。
        # 「最悪シナリオの平均損失を最小化したい」保守・超保守クライアント向け。
        "テールリスク最小型": {
            "core_range": (0.70, 0.85),
            "objective": "min_cvar",
            "max_individual": 0.12,
            "min_individual": 0.02,
            "target_volatility": None
        },
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
                            configs_key, _configs_dict,
                            use_lw: bool = True, rf_rate: float = 0.0):
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
            M-1: rf_rate もキーに含まれているため、金利変更時は確実に再計算される。
        _configs_dict : dict
            プロファイル別の最適化設定
        use_lw : bool
            Ledoit-Wolf収縮共分散推定量を使用するか（キャッシュキーに含まれる）
        rf_rate : float
            年率無リスク金利（M-1: FundScreener と同一値を渡すことでシャープレシオを統一）

        Returns:
        --------
        dict : プロファイル別のポートフォリオ
        """
        # 関数内でAnalyzerを作成（キャッシュ安定性のため）
        # M-1: risk_free_rate を渡し、シャープレシオ計算基準を FundScreener と統一する
        _analyzer = PortfolioAnalyzer(
            _returns_selected, risk_free_rate=rf_rate, use_ledoit_wolf=use_lw
        )
        
        # タプルをリストに戻す
        _selected_funds = list(selected_funds_tuple)
        _core_idx = _selected_funds.index(core_fund_name)  # 外側スコープの core_idx と区別
        
        # プロファイル定義（仕様書 Section 2.2 デザインシステムカラーと統一）
        profile_colors = {
            "積極型":         "#9b2c2c",
            "やや積極型":     "#c05621",
            "バランス型":     "#2f855a",
            "やや保守型":     "#2b6cb0",
            "保守型":         "#2c5282",
            "テールリスク最小型": "#553c9a",   # [改善B1] CVaR最小化プロファイル
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
                rf_rate=rf_rate,   # M-1: FundScreener と同一の無リスク金利を渡す
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

    # ─── [改善F] リスクパリティ & テールリスク最小型を事前計算（チェックON時のみ）──
    # キャッシュ済みの compute_rp_portfolio を使用するため、チェックボックスONでも
    # 2回目以降の実行ではほぼ瞬時に完了する。
    _rp_result   = None
    _tr_portfolio = portfolios.get("テールリスク最小型", None)   # optimization_configs に常に含まれる
    if _show_rp:
        try:
            _ret_hash = hashlib.sha256(
                pd.util.hash_pandas_object(returns_selected, index=True).values.tobytes()
            ).hexdigest()[:16]
            _rp_result = compute_rp_portfolio(
                returns_selected,
                tuple(selected_funds),
                core_fund,
                _use_lw,
                rf_rate,
                _ret_hash,
            )
        except Exception as _rp_pre_err:
            st.warning(f"⚠️ リスクパリティ事前計算に失敗しました: {_rp_pre_err}")

    # ─── レポートデータ事前計算 ＋ 統合レポートパネル ────────────
    # （build_report_data / render_report_panel は portfolio_report で管理）
    _report_ctx = build_report_data(
        portfolios=portfolios,
        selected_funds=selected_funds,
        core_fund=core_fund,
        core_idx=core_idx,
        fund_stats=fund_stats,
        returns_selected=returns_selected,
        rf_rate=rf_rate,
        show_diagnosis=st.session_state.get("show_diagnosis", False),
        show_rp=_show_rp,
        rp_result=_rp_result,
        tr_portfolio=_tr_portfolio,
    )
    # comparison_df / _comparison_col_cfg を ctx から取り出す
    comparison_df         = _report_ctx["comparison_df"]

    # render_report_panel は (allocation_df_numeric, period_start, period_end, period_months) を返す
    allocation_df_numeric, _period_start, _period_end, _period_months = render_report_panel(
        ctx=_report_ctx,
        portfolios=portfolios,
        selected_funds=selected_funds,
        core_fund=core_fund,
        core_idx=core_idx,
        fund_stats=fund_stats,
        returns_selected=returns_selected,
        rf_rate=rf_rate,
        show_rp=_show_rp,
        overview_raw=overview_raw,
        use_lw=_use_lw,
        rp_result=_rp_result,
        tr_portfolio=_tr_portfolio,
    )

    # 詳細分析セクション（外側：プロファイルタブ）
    st.markdown('<div class="section-header">🔍 プロファイル別 詳細分析</div>', unsafe_allow_html=True)

    # 標準5プロファイルのみを外側タブの基本セットとする
    # テールリスク最小型は portfolios dict に含まれているが、
    # チェックOFF時は外側タブに表示しない（比較サマリーにも出さない）
    _standard_5 = ["積極型", "やや積極型", "バランス型", "やや保守型", "保守型"]
    available_profiles = [p for p in _standard_5 if p in portfolios]

    # チェックON時: リスクパリティ & テールリスク最小型タブを追加
    # RP は portfolios dict には入っていないので、擬似的な dict エントリを用意する
    _extra_profiles = []  # (profile_name, weights, stats) のリスト
    if _show_rp:
        if _rp_result is not None:
            _rp_w, _rp_st, _ = _rp_result
            _extra_profiles.append(("リスクパリティ", _rp_w, _rp_st))
        if _tr_portfolio is not None:
            _extra_profiles.append(("テールリスク最小型", _tr_portfolio["weights"], _tr_portfolio["stats"]))

    if not available_profiles and not _extra_profiles:
        st.error("ポートフォリオの生成に失敗しました。パラメータを調整してください。")
        st.stop()

    _profile_label = {
        "積極型":         "🔴 積極型",
        "やや積極型":     "🟠 やや積極型",
        "バランス型":     "🟡 バランス型",
        "やや保守型":     "🟢 やや保守型",
        "保守型":         "🔵 保守型",
        "リスクパリティ": "⚖️ リスクパリティ",
        "テールリスク最小型": "🛡 テールリスク最小型",
    }

    # 全タブ名一覧（標準5 + 追加分）
    _all_tab_profiles   = available_profiles + [ep[0] for ep in _extra_profiles]
    _outer_tabs = st.tabs([_profile_label.get(p, p) for p in _all_tab_profiles])

    # 標準5プロファイルのタブ描画
    for _outer_tab, _profile_name in zip(_outer_tabs[:len(available_profiles)], available_profiles):
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

            # ── 📊 構成ファンド 個別分析（このプロファイルタブに連動）──
            # render_profile_detail の直後・同一タブ内に配置することで、
            # 外側タブ切替と構成ファンド表示を完全に連動させる。
            # Streamlit タブには選択コールバックがないため、
            # タブの外に1回だけ呼ぶ方式では連動できない。
            render_fund_drill_section(
                portfolios       = portfolios,
                selected_funds   = selected_funds,
                returns_selected = returns_selected,
                core_fund        = core_fund,
                core_idx         = core_idx,
                df_filtered      = df_filtered,
                fund_stats       = fund_stats,
                period_start     = _period_start,
                period_end       = _period_end,
                period_months    = _period_months,
                profile_name     = _profile_name,   # タブ名を直接指定
            )

    # リスクパリティ & テールリスク最小型のタブ描画（チェックON時のみ）
    for _outer_tab, (_ep_name, _ep_w, _ep_st) in zip(
        _outer_tabs[len(available_profiles):], _extra_profiles
    ):
        with _outer_tab:
            try:
                if not isinstance(_ep_w, np.ndarray):
                    _ep_w = np.array(_ep_w)
                if _ep_w.shape[0] != len(selected_funds):
                    st.error(f"ポートフォリオの次元が不正: {_ep_w.shape[0]} != {len(selected_funds)}")
                    continue
                # portfolios dict に擬似エントリを追加して render_profile_detail に渡す
                _ep_portfolios_ext = dict(portfolios)
                _ep_cfg = {
                    "core_range": (0.50, 0.65) if _ep_name == "リスクパリティ" else (0.70, 0.85),
                    "max_individual": 0.20,
                    "objective": "risk_parity" if _ep_name == "リスクパリティ" else "min_cvar",
                    "color": "#6366f1" if _ep_name == "リスクパリティ" else "#553c9a",
                }
                _ep_portfolios_ext[_ep_name] = {
                    "weights": _ep_w,
                    "stats":   _ep_st,
                    "config":  _ep_cfg,
                }
                render_profile_detail(
                    _ep_name, _ep_w, _ep_st,
                    returns_selected=returns_selected,
                    selected_funds=selected_funds,
                    df_filtered=df_filtered,
                    df_price=df_price,
                    benchmark=benchmark,
                    core_fund=core_fund,
                    core_idx=core_idx,
                    fund_stats=fund_stats,
                    df_returns=df_returns,
                    portfolios=_ep_portfolios_ext,
                    period_start=_period_start,
                    period_end=_period_end,
                    period_months=_period_months,
                    analyzer=analyzer,
                )
            except Exception as _e:
                st.error(f"{_ep_name}の詳細分析に失敗: {_e}")

    # ─── エクスポート機能 ─────────────────────────────────────────
    # （render_export_section は portfolio_report で管理）
    render_export_section(
        portfolios=portfolios,
        selected_funds=selected_funds,
        comparison_df=comparison_df,
        allocation_df_numeric=allocation_df_numeric,
        fund_stats=fund_stats,
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
