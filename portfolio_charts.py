"""
portfolio_charts.py  v2.0.3
============================
プロファイル別詳細描画モジュール。
portfolio_app.py から render_profile_detail() を import して使用する。

分割経緯:
  portfolio_optimizer_pro.py (3,417行) を
  portfolio_app.py / portfolio_charts.py の2ファイルに分割 (2026-03)

改善内容（v2.0.3）:
✅ D-01修正: tab6 内のネストタブを st.expander に変更
   - Streamlit は st.tabs のネストを公式サポートしていないため UI 崩れが発生する可能性があった
   - st.expander（最初の1件を expanded=True で開いた状態）に置き換え
   - ネスト起因の描画不整合・スクロール問題を解消

✅ D-02修正: ローリング相関の min_periods を 12 に統一
   - 旧実装: ローリング相関 min_periods=8、ローリングシャープ min_periods=12 と不一致
   - ウィンドウ12ヶ月に対して min_periods=8 では短期間での不安定な相関値が混入する恐れがあった
   - min_periods=12 に統一することでローリングシャープと開始タイミングを揃えた

✅ D-04修正: annual_vol_fund の ddof 明示
   - 旧実装: fund_returns_full.std() の ddof 未指定（pandas デフォルト=1 だが意図が不明確）
   - ddof=1 を明示し calc_metrics・FundScreener と完全統一
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import math

# ─── ヘルパー：ドーナツSVG ────────────────────────────────
def _donut_svg(pct_val, color, size=72):
    r = 26; cx = cy = 36; circ = 2 * math.pi * r
    arc = (pct_val / 100) * circ
    offset = circ / 4
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 72 72">'
        f'<circle cx="36" cy="36" r="26" fill="none" stroke="#b0bfc9" stroke-width="9"/>'
        f'<circle cx="36" cy="36" r="26" fill="none" stroke="{color}" stroke-width="9"'
        f' stroke-dasharray="{arc:.1f} {circ-arc:.1f}"'
        f' stroke-dashoffset="{offset:.1f}" stroke-linecap="round"/>'
        f'<text x="36" y="33" text-anchor="middle" font-size="11" font-weight="700" fill="{color}">{pct_val:.0f}%</text>'
        f'<text x="36" y="44" text-anchor="middle" font-size="7" fill="#2f3e4d">コア</text>'
        f'</svg>'
    )

# ─── ヘルパー：メトリクスバッジHTML ──────────────────────
def _badge(label, value, sub, accent):
    return (
        f'<div class="metric-badge" style="border-top:3px solid {accent};">'
        f'<div class="metric-badge-label">{label}</div>'
        f'<div class="metric-badge-value">{value}</div>'
        f'<div class="metric-badge-sub">{sub}</div>'
        f'</div>'
    )


def render_profile_detail(
    selected_profile, selected_weights, selected_stats,
    returns_selected, selected_funds, df_filtered,
    df_price, benchmark, core_fund, core_idx,
    fund_stats, df_returns, portfolios,
    period_start, period_end, period_months,
    analyzer=None
):
    # ポートフォリオリターン計算（内側タブ間共有）
    port_returns = returns_selected.values @ selected_weights
    port_cum_returns = (1 + port_returns).cumprod()
    constituent_funds = [selected_funds[i] for i, w in enumerate(selected_weights) if w > 0.01]

    # 分析期間文字列（引数から受け取り、f-string内で参照できるようローカル変数に展開）
    _period_start  = period_start
    _period_end    = period_end
    _period_months = period_months

    # ── 顧客／担当者モード切替 ────────────────────────────
    if "view_mode" not in st.session_state:
        st.session_state["view_mode"] = "client"

    col_mode_l, col_mode_r = st.columns([6, 1])
    with col_mode_r:
        if st.session_state["view_mode"] == "client":
            if st.button("⚙️ 担当者モード", key=f"mode_btn_{selected_profile}", use_container_width=True):
                st.session_state["view_mode"] = "advisor"
                st.rerun()
        else:
            if st.button("👤 顧客向け表示", key=f"mode_btn_{selected_profile}", use_container_width=True):
                st.session_state["view_mode"] = "client"
                st.rerun()
    with col_mode_l:
        if st.session_state["view_mode"] == "client":
            st.markdown(
                '<p style="font-size:0.82rem;font-weight:500;color:#1e3a5f;'
                'margin:6px 0 0;line-height:1.5;">'
                '👤 顧客向け表示モード　—　過去の実績を分かりやすく表示しています</p>',
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                '<p style="font-size:0.82rem;font-weight:500;color:#1e3a5f;'
                'margin:6px 0 0;line-height:1.5;">'
                '⚙️ 担当者モード　—　詳細指標・構成銘柄分析を含む全情報を表示しています</p>',
                unsafe_allow_html=True
            )

    _is_client = (st.session_state["view_mode"] == "client")

    # ── タブ定義（担当者モードのみ） ──────────────────────────
    if _is_client:
        tab1 = tab2 = tab3 = tab4 = tab5 = tab6 = None
    else:
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "📈 パフォーマンス",
            "🥧 構成",
            "📊 リスク分析",
            "🔗 相関分析",
            "🎲 モンテカルロ",
            "📋 構成銘柄分析"
        ])

    # ━━━ 顧客向けリッチ表示 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if _is_client:
        import json as _json
        import streamlit.components.v1 as _components

        _color_hex = {
            "積極型":     "#9b2c2c",
            "やや積極型": "#c05621",
            "バランス型": "#2f855a",
            "やや保守型": "#2b6cb0",
            "保守型":     "#2c5282",
        }.get(selected_profile, "#2f855a")
        _color_bg = {
            "積極型":     "rgba(155,44,44,0.10)",
            "やや積極型": "rgba(192,86,33,0.10)",
            "バランス型": "rgba(47,133,90,0.10)",
            "やや保守型": "rgba(43,108,176,0.10)",
            "保守型":     "rgba(44,82,130,0.10)",
        }.get(selected_profile, "rgba(47,133,90,0.10)")
        _profile_desc_map = {
            "積極型":     "リターン最大化を重視。短期的な大幅変動を許容できる方向け。",
            "やや積極型": "成長を重視しつつリスクをある程度抑える方向け。",
            "バランス型": "リスクとリターンのバランスを重視する標準的なポートフォリオ。",
            "やや保守型": "元本保全を重視しながら安定的なリターンを目指す方向け。",
            "保守型":     "元本保全を最優先。リターンよりも安定性を重視する方向け。",
        }
        _desc = _profile_desc_map.get(selected_profile, "")

        _total_ret = (port_cum_returns[-1] - 1) * 100
        _ann_ret   = selected_stats["年率リターン"] * 100
        _vol       = selected_stats["年率ボラティリティ"] * 100
        _sharpe    = selected_stats["シャープレシオ"]
        _mdd       = selected_stats["最大ドローダウン"] * 100
        _sortino   = min(selected_stats["ソルティノレシオ"], 10)
        _var95     = selected_stats["月次VaR_95"] * 100
        _cvar95    = selected_stats["月次CVaR_95"] * 100
        _win_rate  = selected_stats["月次勝率"] * 100
        _core_pct  = round(selected_weights[core_idx] * 100, 1)

        _cum_data   = port_cum_returns.tolist()
        _dates_str  = [d.strftime("%Y-%m") for d in df_filtered.index[-len(port_returns):]]
        _ret_col    = "#2f855a" if _ann_ret >= 0 else "#9b2c2c"
        _tret_col   = "#2f855a" if _total_ret >= 0 else "#9b2c2c"
        _ret_sign   = "+" if _ann_ret >= 0 else ""
        _tret_sign  = "+" if _total_ret >= 0 else ""
        _sr_col     = "#2f855a" if _sharpe >= 1.0 else ("#c05621" if _sharpe >= 0.5 else "#9b2c2c")

        # 年次リターン
        _port_ret_s   = pd.Series(port_returns, index=df_filtered.index[-len(port_returns):])
        _yearly       = _port_ret_s.resample("YE").apply(lambda x: (1 + x).prod() - 1)
        _yearly_years = [str(y) for y in _yearly.index.year.tolist()]
        _yearly_vals  = (_yearly.values * 100).tolist()

        # 構成ファンド
        _holdings = [
            {"name": selected_funds[i].split(" ", 1)[1] if " " in selected_funds[i] else selected_funds[i],
             "code": selected_funds[i].split(" ")[0],
             "weight": round(selected_weights[i] * 100, 1)}
            for i in range(len(selected_funds)) if selected_weights[i] > 0.005
        ]
        _holdings.sort(key=lambda x: x["weight"], reverse=True)

        # Holdings HTML
        _hold_rows = ""
        for _h in _holdings[:8]:
            _bw = min(_h["weight"], 100)
            _hold_rows += (
                f'<div style="display:flex;align-items:center;gap:10px;padding:7px 0;'
                f'border-bottom:1px solid rgba(30,60,120,0.07);">'
                f'<span style="font-family:monospace;font-size:12px;color:#1e3a5f;'
                f'width:28px;flex-shrink:0;">{_h["code"]}</span>'
                f'<div style="flex:1;background:rgba(30,60,120,0.07);border-radius:3px;height:5px;overflow:hidden;">'
                f'<div style="width:{_bw}%;height:100%;background:{_color_hex};border-radius:3px;opacity:0.8;"></div>'
                f'</div>'
                f'<span style="font-size:12px;color:#334155;width:160px;overflow:hidden;'
                f'white-space:nowrap;text-overflow:ellipsis;flex-shrink:0;">{_h["name"]}</span>'
                f'<span style="font-family:monospace;font-size:13px;font-weight:700;'
                f'color:{_color_hex};width:40px;text-align:right;flex-shrink:0;">{_h["weight"]}%</span>'
                f'</div>'
            )

        _dates_json       = _json.dumps(_dates_str, ensure_ascii=False)
        _cum_json         = _json.dumps(_cum_data)
        _yearly_years_j   = _json.dumps(_yearly_years)
        _yearly_vals_j    = _json.dumps(_yearly_vals)
        _sortino_color    = "#2f855a" if _sortino >= 1.0 else _color_hex

        _client_html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@300;400;500;700&family=Noto+Serif+JP:wght@600;700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{background:#F4F6F9;color:#1A2540;font-family:'Noto Sans JP',sans-serif;font-weight:300;padding:0 0 24px;}}
.disc-banner{{background:rgba(122,92,30,0.06);border-bottom:1px solid rgba(122,92,30,0.20);
  padding:7px 20px;font-size:12px;color:#6b4c10;display:flex;align-items:center;gap:8px;}}
.prof-header{{display:flex;align-items:flex-start;justify-content:space-between;
  padding:16px 20px 14px;background:#fff;border-bottom:1px solid rgba(30,60,120,0.10);margin-bottom:14px;}}
.prof-title{{font-family:'Noto Serif JP',serif;font-size:19px;font-weight:700;letter-spacing:0.04em;color:{_color_hex};}}
.past-tag{{display:inline-block;background:rgba(122,92,30,0.08);border:1px solid rgba(122,92,30,0.22);
  border-radius:3px;padding:1px 8px;font-size:11px;color:#7A5C1E;letter-spacing:0.06em;margin-left:8px;}}
.prof-sub{{font-size:13px;color:#334155;margin-top:4px;font-weight:400;line-height:1.6;}}
.core-bar-track{{width:140px;background:rgba(30,60,120,0.08);border-radius:3px;height:5px;margin-top:5px;overflow:hidden;}}
.core-bar-fill{{height:100%;border-radius:3px;background:{_color_hex};width:{min(_core_pct,100)}%;}}
.core-label{{font-size:12px;color:#334155;margin-top:4px;font-weight:400;}}
.metrics-grid{{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;padding:0 20px 14px;}}
.mc{{background:#fff;border:1px solid rgba(30,60,120,0.10);border-radius:9px;padding:14px 14px 12px;
  box-shadow:0 1px 4px rgba(30,60,120,0.05);position:relative;overflow:hidden;}}
.mc .lbl{{font-size:11px;color:#1e3a5f;letter-spacing:0.06em;text-transform:uppercase;margin-bottom:6px;font-weight:600;}}
.mc .val{{font-family:'Inter',sans-serif;font-size:22px;font-weight:700;letter-spacing:-0.02em;line-height:1;}}
.mc .unit{{font-size:11px;font-weight:400;opacity:0.7;}}
.mc .note{{font-size:11px;color:#334155;margin-top:6px;line-height:1.5;}}
.mc .warn{{font-size:11px;color:#7a5c00;margin-top:4px;font-weight:500;}}
.lower-grid{{display:grid;grid-template-columns:2fr 1fr;gap:10px;padding:0 20px 14px;}}
.card{{background:#fff;border:1px solid rgba(30,60,120,0.10);border-radius:9px;padding:16px 16px 12px;
  box-shadow:0 1px 4px rgba(30,60,120,0.05);}}
.card-title{{font-size:12px;color:#1e3a5f;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:4px;font-weight:600;}}
.card-sub{{font-size:12px;color:#334155;margin-bottom:12px;line-height:1.5;}}
.chart-wrap{{position:relative;height:220px;}}
.risk-row{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;padding:0 20px 14px;}}
.rc{{background:#fff;border:1px solid rgba(30,60,120,0.10);border-radius:9px;padding:12px 14px;
  box-shadow:0 1px 4px rgba(30,60,120,0.05);}}
.rc .lbl{{font-size:11px;color:#1e3a5f;letter-spacing:0.06em;text-transform:uppercase;margin-bottom:6px;font-weight:600;}}
.rc .val{{font-family:'Inter',sans-serif;font-size:18px;font-weight:700;letter-spacing:-0.01em;}}
.rc .note{{font-size:11px;color:#334155;margin-top:4px;line-height:1.5;}}
.disc-box{{margin:0 20px;background:rgba(122,92,30,0.04);border:1px solid rgba(122,92,30,0.16);
  border-radius:9px;padding:16px 18px;}}
.disc-box h4{{font-size:11px;color:#7A5C1E;letter-spacing:0.08em;text-transform:uppercase;
  margin-bottom:8px;display:flex;align-items:center;gap:5px;font-weight:700;}}
.disc-box p{{font-size:12px;color:#334155;line-height:1.9;margin-bottom:5px;}}
.yearly-wrap{{padding:0 20px 14px;}}
</style>
</head>
<body>
<div class="disc-banner">
  <span>⚠</span>
  <span>本資料は過去の運用実績に基づく分析・解説を目的としており、将来の運用成果を保証・示唆するものではありません。</span>
</div>
<div class="prof-header">
  <div>
<div class="prof-title">{selected_profile}<span class="past-tag">過去実績分析</span></div>
<div class="prof-sub">{_desc}&nbsp;&nbsp;分析期間：{_period_start}〜{_period_end}（{_period_months}ヶ月）</div>
  </div>
  <div style="text-align:right;">
<div style="font-size:12px;color:#1e3a5f;letter-spacing:0.06em;text-transform:uppercase;font-weight:600;">コアファンド比率</div>
<div class="core-bar-track"><div class="core-bar-fill"></div></div>
<div class="core-label">J01 Invesco Bond: {_core_pct}%　→ 残りサテライト資産</div>
  </div>
</div>
<div class="metrics-grid">
  <div class="mc" style="border-top:2px solid {_tret_col};">
<div class="lbl">累積リターン</div>
<div class="val" style="color:{_tret_col};">{_tret_sign}{_total_ret:.2f}<span class="unit">%</span></div>
<div class="note">分析期間全体（設定来ベース）</div>
<div class="warn">⚑ 過去の実績値</div>
  </div>
  <div class="mc" style="border-top:2px solid {_ret_col};">
<div class="lbl">年率リターン (CAGR)</div>
<div class="val" style="color:{_ret_col};">{_ret_sign}{_ann_ret:.2f}<span class="unit">%</span></div>
<div class="note">幾何平均・複利計算ベース</div>
<div class="warn">⚑ 過去の実績値</div>
  </div>
  <div class="mc" style="border-top:2px solid {_color_hex};">
<div class="lbl">年率ボラティリティ</div>
<div class="val" style="color:{_color_hex};">{_vol:.2f}<span class="unit">%</span></div>
<div class="note">月次標準偏差を年率換算</div>
<div class="warn">⚑ 過去の変動幅</div>
  </div>
  <div class="mc" style="border-top:2px solid {_sr_col};">
<div class="lbl">シャープレシオ</div>
<div class="val" style="color:{_sr_col};">{_sharpe:.2f}</div>
<div class="note">リスク1単位あたりの超過収益</div>
<div class="warn">⚑ 1以上が目安（過去値）</div>
  </div>
  <div class="mc" style="border-top:2px solid {_color_hex};">
<div class="lbl">月次勝率</div>
<div class="val" style="color:{_color_hex};">{_win_rate:.1f}<span class="unit">%</span></div>
<div class="note">プラス月数 ÷ 全月数</div>
<div class="warn">⚑ 過去の実績値</div>
  </div>
</div>
<div class="lower-grid">
  <div class="card">
<div class="card-title">基準価額の推移（指数化：初月＝1.0000）</div>
<div class="card-sub">分析開始月を1.0000として指数化。将来の推移を示すものではありません。</div>
<div class="chart-wrap"><canvas id="cumChart"></canvas></div>
  </div>
  <div class="card">
<div class="card-title">ポートフォリオ構成</div>
<div style="margin-top:8px;">{_hold_rows}</div>
  </div>
</div>
<div class="risk-row">
  <div class="rc">
<div class="lbl">最大ドローダウン (MDD)</div>
<div class="val" style="color:#9b2c2c;">{_mdd:.2f}<span style="font-size:11px;font-weight:400;">%</span></div>
<div class="note">過去最大の峰から谷への下落幅</div>
  </div>
  <div class="rc">
<div class="lbl">ソルティノレシオ</div>
<div class="val" style="color:{_sortino_color};">{_sortino:.2f}</div>
<div class="note">下方リスク1単位あたりの超過収益</div>
  </div>
  <div class="rc">
<div class="lbl">月次 VaR (95%)</div>
<div class="val" style="color:#c05621;">{_var95:.2f}<span style="font-size:11px;font-weight:400;">%</span></div>
<div class="note">月次で5%確率を超える損失の推計</div>
  </div>
  <div class="rc">
<div class="lbl">月次 CVaR (95%)</div>
<div class="val" style="color:#c05621;">{_cvar95:.2f}<span style="font-size:11px;font-weight:400;">%</span></div>
<div class="note">VaR超過時の期待損失</div>
  </div>
</div>
<div class="yearly-wrap">
  <div class="card">
<div class="card-title">年次リターン（棒グラフ）<span style="margin-left:8px;background:rgba(122,92,30,0.08);border:1px solid rgba(122,92,30,0.22);border-radius:3px;padding:1px 7px;font-size:11px;color:#7A5C1E;letter-spacing:0.06em;">過去実績</span></div>
<div class="card-sub">各暦年の実現リターン。将来の年次リターンを予測するものではありません。</div>
<div class="chart-wrap" style="height:180px;"><canvas id="yearlyChart"></canvas></div>
  </div>
</div>
<div class="disc-box">
  <h4>⚖ 重要な注意事項</h4>
  <p>本資料に掲載されているリターン・リスク指標はすべて<strong>過去の実績値</strong>であり、将来の運用成果を保証・約束するものでは一切ありません。記載の数値は手数料・税金を考慮していない場合があります。</p>
  <p>外国籍ファンドへの投資は、為替リスク・カントリーリスク・流動性リスク等を含む各種リスクを伴います。最大ドローダウンは過去の損失最大値であり、今後さらに大きな損失が生じる可能性を否定するものではありません。</p>
  <p>ヘッジファンドダイレクト株式会社は関東財務局長（金商）第532号の登録投資助言業者です。本資料は情報提供のみを目的としており、特定ファンドへの投資を勧誘・推奨するものではありません。</p>
</div>
<script>
(function(){{
  var dates={_dates_json};
  var cum={_cum_json};
  var yYears={_yearly_years_j};
  var yVals={_yearly_vals_j};
  var color="{_color_hex}";
  var colorBg="{_color_bg}";
  var ctx1=document.getElementById("cumChart").getContext("2d");
  new Chart(ctx1,{{type:"line",data:{{labels:dates,datasets:[{{
label:"{selected_profile}（過去実績）",data:cum,
borderColor:color,backgroundColor:colorBg,borderWidth:2,
pointRadius:0,pointHoverRadius:4,fill:true,tension:0.3
  }},{{
label:"元本基準（1.0）",
data:dates.map(function(){{return 1.0;}}),
borderColor:"rgba(30,60,120,0.18)",borderWidth:1,
borderDash:[4,4],pointRadius:0,fill:false
  }}]}},options:{{
responsive:true,maintainAspectRatio:false,animation:{{duration:600}},
interaction:{{mode:"index",intersect:false}},
plugins:{{
  legend:{{labels:{{color:"#4A5E7A",font:{{size:10}},boxWidth:14,padding:10}}}},
  tooltip:{{backgroundColor:"#fff",borderColor:color,borderWidth:1,
    titleColor:"#1A2540",bodyColor:"#4A5E7A",
    callbacks:{{label:function(c){{
      if(c.datasetIndex===0){{
        var v=c.parsed.y,chg=((v-1)*100).toFixed(2);
        return" "+c.dataset.label+": "+v.toFixed(4)+"  ("+(chg>=0?"+":"")+chg+"%)";
      }}return null;
    }}}}
  }}
}},
scales:{{
  x:{{ticks:{{color:"#33465e",font:{{size:9}},maxTicksLimit:10,maxRotation:0}},grid:{{color:"rgba(30,60,120,0.06)"}}}},
  y:{{ticks:{{color:"#33465e",font:{{size:9}},callback:function(v){{return v.toFixed(2);}}}},grid:{{color:"rgba(30,60,120,0.07)"}}}}
}}
  }}}});
  var ctx2=document.getElementById("yearlyChart").getContext("2d");
  new Chart(ctx2,{{type:"bar",data:{{labels:yYears,datasets:[{{
label:"年次リターン（実績）",data:yVals,
backgroundColor:yVals.map(function(v){{return v>=0?colorBg:"rgba(217,64,48,0.12)"}}),
borderColor:yVals.map(function(v){{return v>=0?color:"#9b2c2c"}}),
borderWidth:2,borderRadius:4
  }}]}},options:{{
responsive:true,maintainAspectRatio:false,animation:{{duration:500}},
plugins:{{
  legend:{{display:false}},
  tooltip:{{backgroundColor:"#fff",borderColor:color,borderWidth:1,
    titleColor:"#1A2540",bodyColor:"#4A5E7A",
    callbacks:{{label:function(c){{return" "+c.parsed.y.toFixed(2)+"%";}}}}
  }}
}},
scales:{{
  x:{{ticks:{{color:"#33465e",font:{{size:10}}}},grid:{{display:false}}}},
  y:{{ticks:{{color:"#33465e",font:{{size:9}},callback:function(v){{return v.toFixed(1)+"%";}}}},grid:{{color:"rgba(30,60,120,0.07)"}}}}
}}
  }}}});
}})();
</script>
</body>
</html>"""
        _components.html(_client_html, height=1020, scrolling=True)

    # ━━━ 担当者モード タブ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if not _is_client:
        with tab1:
            st.markdown(f"### {selected_profile} - パフォーマンス詳細")

            # パフォーマンスメトリクス
            col1, col2, col3, col4, col5 = st.columns(5)
    
            total_return = (port_cum_returns[-1] - 1) * 100
    
            with col1:
                st.metric("累積リターン（実績）", f"{total_return:.2f}%")
            with col2:
                st.metric("年率リターン（実績）", f"{selected_stats['年率リターン']*100:.2f}%")
            with col3:
                st.metric("年平均リスク（実績）", f"{selected_stats['年率ボラティリティ']*100:.2f}%")
            with col4:
                st.metric("シャープレシオ", f"{selected_stats['シャープレシオ']:.3f}")
            with col5:
                st.metric("最大DD（実績）", f"{selected_stats['最大ドローダウン']*100:.2f}%")
    
            # チャート作成
            fig = go.Figure()
    
            # ポートフォリオ
            fig.add_trace(go.Scatter(
                x=df_filtered.index[-len(port_cum_returns):],
                y=port_cum_returns,
                mode='lines',
                name=selected_profile,
                line=dict(color=portfolios[selected_profile]["config"]["color"], width=3)
            ))
    
            # 構成ファンド
            colors = px.colors.qualitative.Pastel
            for i, fund in enumerate(constituent_funds):
                fund_cum = (1 + df_returns[fund].iloc[-len(port_returns):]).cumprod()
                fig.add_trace(go.Scatter(
                    x=df_filtered.index[-len(fund_cum):],
                    y=fund_cum,
                    mode='lines',
                    name=fund[:25] + '...' if len(fund) > 25 else fund,
                    line=dict(color=colors[i % len(colors)], width=1, dash='dot'),
                    opacity=0.5,
                    visible='legendonly'  # 初期は非表示
                ))
    
            # ベンチマーク
            if benchmark != "なし":
                bench_returns = df_filtered[benchmark].pct_change().dropna()
                # iloc[-n:] でポートフォリオと期間を合わせ、indexを直接x軸に使用
                # (dropna後のindexをそのまま使うことで欠損値による日付ずれを防止)
                bench_slice = bench_returns.iloc[-len(port_returns):]
                bench_cum = (1 + bench_slice).cumprod()
                fig.add_trace(go.Scatter(
                    x=bench_cum.index,
                    y=bench_cum.values,
                    mode='lines',
                    name=f'{benchmark} (ベンチマーク)',
                    line=dict(color='black', width=2, dash='dash')
                ))
    
            fig.update_layout(
                title=f"{selected_profile} - 累積リターン推移",
                xaxis_title="日付",
                yaxis_title="累積リターン",
                hovermode='x unified',
                height=600,
                legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
            )
    
            st.plotly_chart(fig, use_container_width=True, key=f"{selected_profile}_cumret")
    
            # 月次リターン分布
            col1, col2 = st.columns(2)
    
            with col1:
                fig_hist = go.Figure(data=[go.Histogram(
                    x=port_returns * 100,
                    nbinsx=30,
                    marker_color=portfolios[selected_profile]["config"]["color"]
                )])
                fig_hist.update_layout(
                    title="月次リターン分布",
                    xaxis_title="リターン (%)",
                    yaxis_title="頻度",
                    height=400
                )
                st.plotly_chart(fig_hist, use_container_width=True, key=f"{selected_profile}_hist")
    
            with col2:
                # 年次リターン
                port_returns_series = pd.Series(port_returns, index=df_filtered.index[-len(port_returns):])
                yearly_returns = port_returns_series.resample('YE').apply(lambda x: (1 + x).prod() - 1)
        
                # Y軸の範囲を計算（アノテーションが見切れないように余白を追加）
                y_values = yearly_returns.values * 100
                y_min = y_values.min()
                y_max = y_values.max()
                y_range = y_max - y_min
        
                # 上下に余白を追加（最大値側は+20%、最小値側は-20%）
                if y_range > 0:
                    y_axis_min = y_min - y_range * 0.3 if y_min < 0 else y_min - y_range * 0.2
                    y_axis_max = y_max + y_range * 0.3 if y_max > 0 else y_max + y_range * 0.2
                else:
                    # 全て同じ値の場合
                    y_axis_min = y_min - 5
                    y_axis_max = y_max + 5
        
                fig_yearly = go.Figure(data=[go.Bar(
                    x=yearly_returns.index.year,
                    y=y_values,
                    marker_color=portfolios[selected_profile]["config"]["color"],
                    text=[f'{val:.1f}%' for val in y_values],
                    textposition='outside'
                )])
                fig_yearly.update_layout(
                    title="年次リターン",
                    xaxis_title="年",
                    yaxis_title="リターン (%)",
                    yaxis=dict(range=[y_axis_min, y_axis_max]),
                    height=400
                )
                st.plotly_chart(fig_yearly, use_container_width=True, key=f"{selected_profile}_yearly")
    
            # 構成ファンドの個別チャート
            st.markdown("### 構成ファンドの価格推移")
            st.caption("💡 ポートフォリオを構成する各ファンドの価格推移（基準価格=100として正規化）")
    
            # 1%以上の比重を持つファンドのみ表示
            constituent_funds_charts = [selected_funds[i] for i, w in enumerate(selected_weights) if w > 0.01]
    
            # 2列レイアウトで表示
            num_cols = 2
            num_funds = len(constituent_funds_charts)
    
            for i in range(0, num_funds, num_cols):
                cols = st.columns(num_cols)
        
                for j in range(num_cols):
                    if i + j < num_funds:
                        fund = constituent_funds_charts[i + j]
                        fund_idx = selected_funds.index(fund)
                
                        with cols[j]:
                            # ファンドの価格データを正規化（開始時点=100）
                            fund_prices = df_filtered[fund].dropna()
                            fund_prices_normalized = (fund_prices / fund_prices.iloc[0]) * 100
                    
                            # チャート作成
                            fig_fund = go.Figure()
                            fig_fund.add_trace(go.Scatter(
                                x=fund_prices_normalized.index,
                                y=fund_prices_normalized.values,
                                mode='lines',
                                name=fund[:30] + '...' if len(fund) > 30 else fund,
                                line=dict(color=portfolios[selected_profile]["config"]["color"], width=2),
                                fill='tozeroy',
                                fillcolor=f"rgba({int(portfolios[selected_profile]['config']['color'][1:3], 16)}, "
                                         f"{int(portfolios[selected_profile]['config']['color'][3:5], 16)}, "
                                         f"{int(portfolios[selected_profile]['config']['color'][5:7], 16)}, 0.1)"
                            ))
                    
                            # 統計情報
                            weight_pct = selected_weights[fund_idx] * 100
                            fund_return = fund_stats.loc[fund, '年率リターン'] * 100
                            fund_vol = fund_stats.loc[fund, '年率ボラ'] * 100
                    
                            fig_fund.update_layout(
                                title=f"{fund[:40]}<br><sub>比重: {weight_pct:.1f}% | リターン: {fund_return:.1f}% | ボラ: {fund_vol:.1f}%</sub>",
                                xaxis_title="",
                                yaxis_title="基準価格 (開始時=100)",
                                height=350,
                                showlegend=False,
                                hovermode='x unified',
                                margin=dict(t=80, b=40, l=60, r=20)
                            )
                    
                            st.plotly_chart(fig_fund, use_container_width=True, key=f"{selected_profile}_fund_{fund}")

        with tab2:
            st.markdown(f"### {selected_profile} - ポートフォリオ構成")
    
            # 比重データ
            weights_df = pd.DataFrame({
                'ファンド': selected_funds,
                '比重(%)': selected_weights * 100,
                '年率リターン(%)': [fund_stats.loc[f, '年率リターン'] * 100 for f in selected_funds],
                '年平均リスク(%)': [fund_stats.loc[f, '年率ボラ'] * 100 for f in selected_funds],
                'シャープレシオ': [fund_stats.loc[f, 'シャープレシオ'] for f in selected_funds]
            })
            weights_df = weights_df[weights_df['比重(%)'] > 1.0].sort_values('比重(%)', ascending=False)
    
            col1, col2 = st.columns([1, 1])
    
            with col1:
                # パイチャート
                fig_pie = go.Figure(data=[go.Pie(
                    labels=weights_df['ファンド'].apply(lambda x: x[:30] + '...' if len(x) > 30 else x),
                    values=weights_df['比重(%)'],
                    hole=0.4,
                    marker=dict(colors=px.colors.qualitative.Set3)
                )])
                fig_pie.update_layout(title="ファンド構成比率", height=500)
                st.plotly_chart(fig_pie, use_container_width=True, key=f"{selected_profile}_pie")
    
            with col2:
                # トリーマップ
                fig_tree = go.Figure(go.Treemap(
                    labels=weights_df['ファンド'].apply(lambda x: x[:25]),
                    parents=[""] * len(weights_df),
                    values=weights_df['比重(%)'],
                    textinfo="label+value+percent parent",
                    marker=dict(colors=px.colors.qualitative.Pastel)
                ))
                fig_tree.update_layout(title="ポートフォリオ構造", height=500)
                st.plotly_chart(fig_tree, use_container_width=True, key=f"{selected_profile}_tree")
    
            # 詳細テーブル
            st.dataframe(weights_df.round(3), use_container_width=True, hide_index=True)
    
            # コアファンドハイライト
            st.info(f"🎯 コアファンド: **{core_fund}** ({selected_weights[core_idx]*100:.1f}%)")

        with tab3:
            st.markdown(f"### {selected_profile} - リスク分析")
    
            # ドローダウン計算
            # 先頭に 1.0 を付加して期初損失を正確に捕捉（portfolio_utils 修正J と統一）
            # 付加しない場合、第1期の損失は running_max[0]=cum[0] となり DD[0]=0 になる
            _cum_with_start = np.concatenate([[1.0], port_cum_returns])
            _run_max = np.maximum.accumulate(_cum_with_start)
            _dd_full = (_cum_with_start - _run_max) / _run_max
            drawdown = _dd_full[1:]   # 付加した 1.0 点を除去して系列長を元に戻す
    
            # ドローダウンチャート
            fig_dd = go.Figure()
            fig_dd.add_trace(go.Scatter(
                x=df_filtered.index[-len(drawdown):],
                y=drawdown * 100,
                mode='lines',
                fill='tozeroy',
                name='ドローダウン',
                line=dict(color='red'),
                fillcolor='rgba(255, 0, 0, 0.2)'
            ))
            fig_dd.update_layout(
                title="ドローダウン推移",
                xaxis_title="日付",
                yaxis_title="ドローダウン (%)",
                hovermode='x unified',
                height=400
            )
            st.plotly_chart(fig_dd, use_container_width=True, key=f"{selected_profile}_dd")
    
            # リスク指標 — 従来の4指標
            col1, col2, col3, col4 = st.columns(4)

            max_dd_idx = np.argmin(drawdown)
            max_dd_date = df_filtered.index[-len(drawdown):][max_dd_idx]

            with col1:
                st.metric("最大ドローダウン", f"{selected_stats['最大ドローダウン']*100:.2f}%")
                st.caption(f"発生: {max_dd_date.strftime('%Y年%m月')}")
            with col2:
                st.metric("ソルティノレシオ", f"{selected_stats['ソルティノレシオ']:.3f}")
            with col3:
                st.metric("カルマー比率", f"{selected_stats['カルマー比率']:.3f}")
            with col4:
                st.metric("月次勝率", f"{selected_stats['月次勝率']*100:.1f}%")

            # ── [改善G・H] 新指標行 ─────────────────────────────────────
            # ポートフォリオレベルでOmega・Ulcer・Martin・GLを計算して表示
            _pr = pd.Series(port_returns)
            _tau = 0.0
            _pos = np.maximum(_pr - _tau, 0).sum()
            _neg = np.maximum(_tau - _pr, 0).sum()
            _omega_port = min(_pos / _neg, 99.99) if _neg > 1e-8 else (99.99 if _pos > 0 else 0.0)

            _dd_sq   = drawdown ** 2
            _ulcer_port = float(np.sqrt(np.mean(_dd_sq)))
            _ann_ret_geom = selected_stats['年率リターン']
            _martin_port  = (_ann_ret_geom / _ulcer_port) if _ulcer_port > 1e-8 else (
                99.99 if _ann_ret_geom > 0 else 0.0
            )
            _martin_port = min(max(_martin_port, -99.99), 99.99)

            _wins   = _pr[_pr > 0]
            _losses = _pr[_pr < 0]
            _ag = _wins.mean()        if len(_wins)   > 0 else 0.0
            _al = abs(_losses.mean()) if len(_losses) > 0 else 1e-8
            _gl_port = min(_ag / _al, 99.99) if _al > 1e-8 and _ag > 0 else (
                99.99 if _ag > 0 else 0.0
            )

            col5, col6, col7, col8 = st.columns(4)
            with col5:
                st.metric("Omega比率", f"{_omega_port:.3f}",
                          help="τ=0（月次元本割れ）に対する利益/損失の比率。非正規分布も正しく評価。1.0超で損益プラス。")
            with col6:
                st.metric("Ulcer指数", f"{_ulcer_port*100:.2f}%",
                          help="全期間のドローダウン二乗平均平方根。低いほど「深く長い」DDが少ない。")
            with col7:
                st.metric("Martin比率", f"{_martin_port:.3f}",
                          help="年率リターン÷Ulcer指数。カルマー比率のUlcer版。高いほど優秀。")
            with col8:
                st.metric("GL比率", f"{_gl_port:.3f}",
                          help="平均利益÷平均損失の絶対値。1.0超で利益が損失を上回る。売りオプション系は0.2前後に低下。")
    
            # VaR/CVaR（月次）
            col1, col2 = st.columns(2)
            with col1:
                st.metric("月次VaR (95%)", f"{selected_stats['月次VaR_95']*100:.2f}%")
            with col2:
                st.metric("月次CVaR (95%)", f"{selected_stats['月次CVaR_95']*100:.2f}%")
    
            # ローリング統計
            port_returns_series = pd.Series(port_returns, index=df_filtered.index[-len(port_returns):])
    
            col1, col2 = st.columns(2)
    
            with col1:
                # ローリングシャープ（月次リスクフリーレート控除、portfolio_utilsと定義を統一）
                rfr_monthly = (analyzer.risk_free_rate if analyzer is not None else 0.0) / 12
                rolling_sharpe = port_returns_series.rolling(window=12, min_periods=12).apply(
                    lambda x: ((x.mean() - rfr_monthly) * 12) / (x.std() * np.sqrt(12)) if x.std() > 0 else 0
                )
        
                fig_rs = go.Figure()
                fig_rs.add_trace(go.Scatter(
                    x=rolling_sharpe.index,
                    y=rolling_sharpe.values,
                    mode='lines',
                    name='ローリングシャープ',
                    line=dict(color='blue')
                ))
                fig_rs.add_hline(y=0, line_dash="dash", line_color="gray")
                fig_rs.update_layout(
                    title="12ヶ月ローリングシャープレシオ",
                    xaxis_title="日付",
                    yaxis_title="シャープレシオ",
                    height=400
                )
                st.plotly_chart(fig_rs, use_container_width=True, key=f"{selected_profile}_rolling_sharpe")
    
            with col2:
                # ローリングボラティリティ（min_periods=12・ddof=1 をローリングシャープと統一）
                rolling_vol = port_returns_series.rolling(window=12, min_periods=12).std(ddof=1) * np.sqrt(12)
        
                fig_rv = go.Figure()
                fig_rv.add_trace(go.Scatter(
                    x=rolling_vol.index,
                    y=rolling_vol.values * 100,
                    mode='lines',
                    name='ローリングボラ',
                    line=dict(color='orange')
                ))
                fig_rv.update_layout(
                    title="12ヶ月ローリングボラティリティ",
                    xaxis_title="日付",
                    yaxis_title="ボラティリティ (%)",
                    height=400
                )
                st.plotly_chart(fig_rv, use_container_width=True, key=f"{selected_profile}_rolling_vol")

    if tab4 is not None:
      with tab4:
        st.markdown("### 相関分析")
    
        # 選定ファンドの相関マトリックス
        corr_matrix = returns_selected.corr()
    
        # ヒートマップ
        fig_corr = go.Figure(data=go.Heatmap(
            z=corr_matrix.values,
            x=[f[:15] + '...' if len(f) > 15 else f for f in corr_matrix.columns],
            y=[f[:15] + '...' if len(f) > 15 else f for f in corr_matrix.index],
            colorscale='RdBu_r',
            zmid=0,
            zmin=-1,
            zmax=1,
            text=np.round(corr_matrix.values, 2),
            texttemplate='%{text}',
            textfont={"size": 7},
            hovertemplate='%{y} vs %{x}<br>相関: %{z:.3f}<extra></extra>'
        ))
        fig_corr.update_layout(
            title="選定ファンド相関マトリックス",
            height=700,
            xaxis={'side': 'bottom', 'tickangle': 45}
        )
        st.plotly_chart(fig_corr, use_container_width=True, key=f"{selected_profile}_corr_matrix")
    
        # コアファンドとのローリング相関
        st.markdown(f"#### {core_fund} とのローリング相関 (12ヶ月)")
    
        constituent_funds_corr = [f for i, f in enumerate(selected_funds) 
                                 if selected_weights[i] > 0.02 and f != core_fund]
    
        fig_rc = go.Figure()
    
        colors = px.colors.qualitative.Set1
        for i, fund in enumerate(constituent_funds_corr[:10]):
            # Series.rolling().corr() を使用：DatetimeIndex が保持され正確に描画される
            # DataFrame.rolling().corr() の MultiIndex 問題を回避
            rolling_corr_values = (
                returns_selected[core_fund]
                .rolling(window=12, min_periods=12)  # D-02修正: ローリングシャープ(min_periods=12)と統一
                .corr(returns_selected[fund])
                .dropna()
            )
        
            if len(rolling_corr_values) == 0:
                continue
        
            fig_rc.add_trace(go.Scatter(
                x=rolling_corr_values.index,
                y=rolling_corr_values.values,
                mode='lines',
                name=fund[:20] + '...' if len(fund) > 20 else fund,
                line=dict(color=colors[i % len(colors)]),
                hovertemplate='%{x|%Y-%m}<br>相関: %{y:.3f}<extra></extra>'
            ))
    
        fig_rc.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
        fig_rc.update_layout(
            title=f"{core_fund} とのローリング相関推移",
            xaxis_title="日付",
            yaxis_title="相関係数",
            hovermode='x unified',
            height=500
        )
        st.plotly_chart(fig_rc, use_container_width=True, key=f"{selected_profile}_rolling_corr")

    if tab5 is not None:
      with tab5:
        st.markdown("### モンテカルロシミュレーション")
    
        st.info("将来のポートフォリオパフォーマンスをシミュレーションします")
    
        col1, col2 = st.columns(2)
        with col1:
            sim_years = st.slider("シミュレーション期間（年）", 1, 10, 5, key=f"{selected_profile}_sim_years")
        with col2:
            n_simulations = st.slider("シミュレーション回数", 100, 10000, 1000, 100, key=f"{selected_profile}_n_simulations")
    
        if st.button("シミュレーション実行", key=f"{selected_profile}_run_mc"):
            with st.spinner("シミュレーション実行中..."):
                # モンテカルロシミュレーション
                n_periods = sim_years * 12

                # ── 月次パラメータ計算 ──────────────────────────────────────
                # port_std：時系列リターン系列から直接計算（共分散ベースの年率ボラを逆算するより整合的）
                port_returns_mc = returns_selected.values @ selected_weights
                port_std_monthly = float(np.std(port_returns_mc, ddof=1))

                # 対数正規分布の μ（月次）：算術平均リターンから分散ハーフを引く
                # E[r_arithmetic] = exp(μ + σ²/2) - 1  →  μ = ln(1+E[r]) - σ²/2
                port_mean_arith_monthly = selected_stats['年率期待リターン'] / 12
                log_mu = np.log1p(port_mean_arith_monthly) - 0.5 * port_std_monthly ** 2

                # ── ベクトル化モンテカルロ ──────────────────────────────────
                # 正規分布 N(log_mu, port_std_monthly) でログリターンを生成
                # → exp(累積和) で対数正規過程を正確に模擬
                # default_rng でグローバル乱数状態を汚染しない
                rng = np.random.default_rng(42)
                log_returns = rng.normal(log_mu, port_std_monthly, (n_simulations, n_periods))
                simulations = np.ones((n_simulations, n_periods + 1))
                simulations[:, 1:] = np.exp(np.cumsum(log_returns, axis=1))
            
                # 結果プロット
                fig_mc = go.Figure()
            
                # 各シミュレーション
                for i in range(min(100, n_simulations)):
                    fig_mc.add_trace(go.Scatter(
                        x=list(range(n_periods + 1)),
                        y=simulations[i, :],
                        mode='lines',
                        line=dict(color='lightblue', width=0.5),
                        opacity=0.3,
                        showlegend=False,
                        hoverinfo='skip'
                    ))
            
                # パーセンタイル
                percentiles = [5, 25, 50, 75, 95]
                colors_percentile = ['red', 'orange', 'green', 'orange', 'red']
            
                for pct, color in zip(percentiles, colors_percentile):
                    values = np.percentile(simulations, pct, axis=0)
                    fig_mc.add_trace(go.Scatter(
                        x=list(range(n_periods + 1)),
                        y=values,
                        mode='lines',
                        name=f'{pct}パーセンタイル',
                        line=dict(color=color, width=2)
                    ))
            
                fig_mc.update_layout(
                    title=f"モンテカルロシミュレーション ({n_simulations}回)",
                    xaxis_title="月数",
                    yaxis_title="ポートフォリオ価値",
                    height=500,
                    hovermode='x unified'
                )
                st.plotly_chart(fig_mc, use_container_width=True, key=f"{selected_profile}_montecarlo")
            
                # 統計サマリー
                final_values = simulations[:, -1]
            
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("期待値（中央値）", f"{np.median(final_values):.2f}")
                with col2:
                    st.metric("95%信頼区間下限", f"{np.percentile(final_values, 5):.2f}")
                with col3:
                    st.metric("95%信頼区間上限", f"{np.percentile(final_values, 95):.2f}")
                with col4:
                    prob_profit = (final_values > 1).sum() / n_simulations * 100
                    st.metric("利益確率", f"{prob_profit:.1f}%")

    if tab6 is not None:
      with tab6:
        st.markdown("### 構成銘柄詳細分析")
        st.info("💡 ポートフォリオを構成する各ファンドについて、オリジナルデータ全期間での詳細分析を表示します")
    
        # 構成銘柄を特定（ウェイト0.5%以上）
        constituent_funds_analysis = [(selected_funds[i], selected_weights[i]) 
                                     for i in range(len(selected_funds)) 
                                     if selected_weights[i] >= 0.005]
        constituent_funds_analysis.sort(key=lambda x: x[1], reverse=True)
    
        st.markdown(f"**分析対象ファンド数**: {len(constituent_funds_analysis)}本（ウェイト0.5%以上）")
    
        # 各ファンドについてexpander表示
        # D-01修正: st.tabs はStreamlit公式にネストをサポートしていないため st.expander に変更
        if len(constituent_funds_analysis) > 0:
            for idx, (fund, weight) in enumerate(constituent_funds_analysis):
                expander_label = (
                    f"{fund[:25]}... ({weight*100:.1f}%)" if len(fund) > 25
                    else f"{fund} ({weight*100:.1f}%)"
                )
                with st.expander(expander_label, expanded=(idx == 0)):
                    # ファンド名表示
                    st.markdown(f"#### 📊 {fund}")
                    st.markdown(f"**ポートフォリオ比重**: {weight*100:.2f}%")
                
                    # 全期間データを取得（欠損値を除外）
                    fund_prices_full = df_price[fund].dropna()
                
                    if len(fund_prices_full) < 12:
                        st.warning(f"⚠️ データポイントが不足しています（{len(fund_prices_full)}ヶ月）")
                        continue
                
                    # ベンチマークデータ
                    if benchmark != "なし":
                        bench_prices_full = df_price[benchmark].dropna()
                        # 期間を合わせる
                        common_idx = fund_prices_full.index.intersection(bench_prices_full.index)
                        fund_prices_full = fund_prices_full.loc[common_idx]
                        bench_prices_full = bench_prices_full.loc[common_idx]
                
                    # データ期間情報
                    st.caption(f"📅 データ期間: {fund_prices_full.index[0].strftime('%Y年%m月')} ～ {fund_prices_full.index[-1].strftime('%Y年%m月')} （{len(fund_prices_full)}ヶ月）")
                
                    # リターン計算
                    fund_returns_full = fund_prices_full.pct_change().dropna()
                
                    # 各期間のリターン計算関数
                    def calc_annualized_return(returns_series, periods):
                        """期間別の年率リターンを計算"""
                        if len(returns_series) < periods:
                            return np.nan
                        period_returns = returns_series.iloc[-periods:]
                        cum_return = (1 + period_returns).prod() - 1
                        annual_return = (1 + cum_return) ** (12 / periods) - 1
                        return annual_return * 100
                
                    # リターン表作成
                    periods_dict = {
                        "1年": 12,
                        "3年": 36,
                        "5年": 60,
                        "10年": 120,
                        "設定来": len(fund_returns_full)
                    }
                
                    # ファンド名を短縮（30文字以内）
                    fund_name_short = fund[:30] + '...' if len(fund) > 30 else fund
                
                    return_data = []
                    for period_name, period_months in periods_dict.items():
                        fund_ret = calc_annualized_return(fund_returns_full, period_months)
                    
                        if benchmark != "なし":
                            bench_returns_full = bench_prices_full.pct_change().dropna()
                            bench_ret = calc_annualized_return(bench_returns_full, period_months)
                        else:
                            bench_ret = np.nan
                    
                        return_data.append({
                            "期間": period_name,
                            fund_name_short: f"{fund_ret:.1f}%" if not np.isnan(fund_ret) else "N/A",
                            benchmark if benchmark != "なし" else "ベンチマーク": 
                                f"{bench_ret:.1f}%" if not np.isnan(bench_ret) else "N/A"
                        })
                
                    # 定量分析計算
                    def calc_metrics(returns_series, bench_returns_series=None, risk_free_rate=0.0):
                        """定量分析指標を計算

                        Notes
                        -----
                        シャープレシオは FundScreener._calculate_statistics と計算基準を統一。
                        算術平均ベースの期待リターンでシャープを計算（ポートフォリオ全体の指標と一貫）。
                        v3.3: Omega比率・Ulcer指数・Martin比率・GL比率を追加（改善G・H）。
                        """
                        if len(returns_series) < 12:
                            return {
                                "シャープレシオ":  np.nan,
                                "価格変動リスク":  np.nan,
                                "最大下落率":      np.nan,
                                "Omega比率":       np.nan,
                                "Ulcer指数":       np.nan,
                                "Martin比率":      np.nan,
                                "GL比率":          np.nan,
                                "相関性":          np.nan,
                            }

                        # 年率期待リターン（算術平均 - シャープ計算用：FundScreenerと統一）
                        annual_return_arith = returns_series.mean() * 12
                        # 年率リターン（CAGR - Martin比率計算用）
                        n_p = len(returns_series)
                        cum_r = (1 + returns_series).prod() - 1
                        annual_return_geom = (1 + cum_r) ** (12 / n_p) - 1 if n_p > 0 else 0
                        # 年率ボラティリティ（ddof=1：FundScreenerと統一）
                        annual_vol = returns_series.std(ddof=1) * np.sqrt(12)
                        # シャープレシオ（算術平均ベース・rf控除済み：FundScreenerと統一）
                        annual_excess = annual_return_arith - risk_free_rate
                        sharpe = annual_excess / annual_vol if annual_vol > 0 else 0

                        # 最大ドローダウン（先頭1.0付加で期初損失を正確に捕捉：portfolio_utils 修正J と統一）
                        _cum_np  = np.concatenate([[1.0], (1 + returns_series.values).cumprod()])
                        _rmax_np = np.maximum.accumulate(_cum_np)
                        _dd_arr  = (_cum_np - _rmax_np) / _rmax_np
                        drawdown = pd.Series(_dd_arr[1:], index=returns_series.index)
                        max_dd = float(_dd_arr[1:].min()) * 100

                        # ── [改善G] Omega比率 ─────────────────────────────
                        tau   = 0.0
                        pos   = np.maximum(returns_series - tau, 0).sum()
                        neg   = np.maximum(tau - returns_series, 0).sum()
                        omega = min(pos / neg, 99.99) if neg > 1e-8 else (99.99 if pos > 0 else 0.0)

                        # ── [改善G] Ulcer指数・Martin比率 ─────────────────
                        dd_series = drawdown  # 全期間のDD推移（≤0）
                        ulcer     = float(np.sqrt(np.mean(dd_series ** 2)))
                        martin    = (annual_return_geom / ulcer) if ulcer > 1e-8 else (
                            99.99 if annual_return_geom > 0 else 0.0
                        )
                        martin    = min(max(martin, -99.99), 99.99)

                        # ── [改善H] GL比率 ────────────────────────────────
                        wins   = returns_series[returns_series > 0]
                        losses = returns_series[returns_series < 0]
                        avg_gain = wins.mean()        if len(wins)   > 0 else 0.0
                        avg_loss = abs(losses.mean()) if len(losses) > 0 else 1e-8
                        gl_ratio = min(avg_gain / avg_loss, 99.99) if avg_loss > 1e-8 and avg_gain > 0 else (
                            99.99 if avg_gain > 0 else 0.0
                        )

                        # 相関係数（ベンチマークとの）
                        correlation = np.nan
                        if bench_returns_series is not None and len(bench_returns_series) >= 12:
                            common_idx = returns_series.index.intersection(bench_returns_series.index)
                            if len(common_idx) >= 12:
                                correlation = returns_series.loc[common_idx].corr(
                                    bench_returns_series.loc[common_idx]
                                )

                        return {
                            "シャープレシオ": f"{sharpe:.2f}",
                            "価格変動リスク": f"{annual_vol * 100:.1f}%",
                            "最大下落率":     f"{max_dd:.1f}%",
                            "Omega比率":      f"{omega:.2f}",
                            "Ulcer指数":      f"{ulcer*100:.2f}%",
                            "Martin比率":     f"{martin:.2f}",
                            "GL比率":         f"{gl_ratio:.2f}",
                            "相関性":         f"{correlation:.2f}" if not np.isnan(correlation) else "N/A",
                        }
                
                    _rf = analyzer.risk_free_rate if analyzer is not None else 0.0
                    if benchmark != "なし":
                        bench_returns_full = bench_prices_full.pct_change().dropna()
                        fund_metrics  = calc_metrics(fund_returns_full,  bench_returns_full, risk_free_rate=_rf)
                        bench_metrics = calc_metrics(bench_returns_full, risk_free_rate=_rf)
                    else:
                        fund_metrics  = calc_metrics(fund_returns_full, risk_free_rate=_rf)
                        bench_metrics = {
                            "シャープレシオ": "N/A", 
                            "価格変動リスク": "N/A",
                            "最大下落率": "N/A",
                            "相関性": "N/A"
                        }
                
                    _bname = benchmark if benchmark != "なし" else "ベンチマーク"
                    risk_data = [
                        # ── 従来指標 ──────────────────────────────────────
                        {
                            "指標": "シャープレシオ",
                            "説明": "リスク調整後リターン（1.0超が優秀）",
                            fund_name_short: fund_metrics["シャープレシオ"],
                            _bname: bench_metrics.get("シャープレシオ", "-"),
                        },
                        {
                            "指標": "価格変動リスク",
                            "説明": "年率ボラティリティ（低いほど安定）",
                            fund_name_short: fund_metrics["価格変動リスク"],
                            _bname: bench_metrics.get("価格変動リスク", "-"),
                        },
                        {
                            "指標": "最大下落率",
                            "説明": "設定来の最大ドローダウン",
                            fund_name_short: fund_metrics["最大下落率"],
                            _bname: bench_metrics.get("最大下落率", "-"),
                        },
                        # ── [改善G] 新指標 ────────────────────────────────
                        {
                            "指標": "Omega比率",
                            "説明": "利益/損失の比率（1.0超で損益プラス）",
                            fund_name_short: fund_metrics["Omega比率"],
                            _bname: bench_metrics.get("Omega比率", "-"),
                        },
                        {
                            "指標": "Ulcer指数",
                            "説明": "DD累積ペナルティ（低いほど良好）",
                            fund_name_short: fund_metrics["Ulcer指数"],
                            _bname: bench_metrics.get("Ulcer指数", "-"),
                        },
                        {
                            "指標": "Martin比率",
                            "説明": "リターン÷Ulcer指数（高いほど優秀）",
                            fund_name_short: fund_metrics["Martin比率"],
                            _bname: bench_metrics.get("Martin比率", "-"),
                        },
                        # ── [改善H] 新指標 ────────────────────────────────
                        {
                            "指標": "GL比率",
                            "説明": "平均利益÷平均損失（1.0超で損益有利）",
                            fund_name_short: fund_metrics["GL比率"],
                            _bname: bench_metrics.get("GL比率", "-"),
                        },
                        {
                            "指標": "相関性",
                            "説明": "コアとの相関（低いほど分散効果大）",
                            fund_name_short: fund_metrics["相関性"],
                            _bname: "-",
                        },
                    ]

                    # 表示
                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown("##### 📊 リターン（年率）")
                        return_df = pd.DataFrame(return_data)

                        # スタイリング付きで表示
                        def color_returns(val):
                            """リターン値に色付け"""
                            if isinstance(val, str) and '%' in val:
                                try:
                                    num_val = float(val.replace('%', ''))
                                    if num_val > 0:
                                        return 'background-color: #d4edda; color: #155724'
                                    elif num_val < 0:
                                        return 'background-color: #f8d7da; color: #721c24'
                                except:
                                    pass
                            return ''

                        styled_return_df = return_df.style.map(
                            color_returns,
                            subset=[fund_name_short, _bname],
                        )
                        st.dataframe(styled_return_df, use_container_width=True, hide_index=True)

                    with col2:
                        st.markdown("##### 📉 定量分析（設定来）")
                        risk_df = pd.DataFrame(risk_data)
                        st.dataframe(risk_df, use_container_width=True, hide_index=True)
                
                    # パフォーマンス推移グラフ
                    st.markdown("##### 📈 パフォーマンス推移（指数化）")
                
                    # 指数化（開始時点=100）
                    fund_indexed = (fund_prices_full / fund_prices_full.iloc[0]) * 100
                
                    fig_perf = go.Figure()
                
                    # ファンド
                    fig_perf.add_trace(go.Scatter(
                        x=fund_indexed.index,
                        y=fund_indexed.values,
                        mode='lines',
                        name=fund[:40] + '...' if len(fund) > 40 else fund,
                        line=dict(color='#ff6b35', width=2.5),
                        hovertemplate='%{x|%Y-%m}<br>価格: %{y:.2f}<extra></extra>'
                    ))
                
                    # ベンチマーク
                    if benchmark != "なし":
                        bench_indexed = (bench_prices_full / bench_prices_full.iloc[0]) * 100
                        fig_perf.add_trace(go.Scatter(
                            x=bench_indexed.index,
                            y=bench_indexed.values,
                            mode='lines',
                            name=benchmark,
                            line=dict(color='#004e89', width=2, dash='solid'),
                            opacity=0.7,
                            hovertemplate='%{x|%Y-%m}<br>価格: %{y:.2f}<extra></extra>'
                        ))
                
                    fig_perf.update_layout(
                        title=f"パフォーマンス推移（指数化） - {fund[:50]}",
                        xaxis_title="",
                        yaxis_title="指数（開始時=100）",
                        hovermode='x unified',
                        height=500,
                        legend=dict(
                            orientation="h",
                            yanchor="bottom",
                            y=1.02,
                            xanchor="right",
                            x=1
                        )
                    )
                
                    # 期間表示を追加
                    fig_perf.add_annotation(
                        text=f"表示期間: {fund_prices_full.index[0].strftime('%Y年%m月')} 〜 {fund_prices_full.index[-1].strftime('%Y年%m月')}",
                        xref="paper", yref="paper",
                        x=1, y=-0.1,
                        showarrow=False,
                        xanchor='right',
                        font=dict(size=9, color='gray')
                    )
                
                    st.plotly_chart(fig_perf, use_container_width=True, key=f"{selected_profile}_fund_perf_{idx}")
                
                    # 統計サマリー
                    st.markdown("##### 📋 統計サマリー")
                
                    col1, col2, col3, col4 = st.columns(4)
                
                    # 設定来リターン
                    total_return_fund = ((fund_prices_full.iloc[-1] / fund_prices_full.iloc[0]) - 1) * 100
                    annual_return_fund = calc_annualized_return(fund_returns_full, len(fund_returns_full))
                    annual_vol_fund = fund_returns_full.std(ddof=1) * np.sqrt(12) * 100  # D-04修正: ddof=1明示（calc_metrics・FundScreenerと統一）
                
                    with col1:
                        st.metric("設定来リターン", f"{total_return_fund:.1f}%")
                    with col2:
                        st.metric("年率リターン", f"{annual_return_fund:.1f}%")
                    with col3:
                        st.metric("年平均リスク", f"{annual_vol_fund:.1f}%")
                    with col4:
                        st.metric("データ期間", f"{len(fund_prices_full)}ヶ月")
