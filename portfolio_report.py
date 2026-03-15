"""
portfolio_report.py  v1.0.0
=============================
統合レポートパネル・エクスポート機能モジュール。
portfolio_app.py から import して使用する。

新規作成経緯（ステージ3リファクタ 2026-03）:
  portfolio_app.py の最適化完了後ブロック（約1,000行）から
  レポート描画・エクスポート責務を切り出した。

責務:
  - build_report_data()     : 比較・診断・カードの事前計算
  - render_report_panel()   : プロファイルカード＋3タブ統合レポート描画
  - render_export_section() : Excel ダウンロードボタン
"""
import io
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ── デザインシステム定数 ───────────────────────────────────────
_PROFILE_META = {
    "積極型":     {"color": "#9b2c2c", "grad": "linear-gradient(135deg,#9b2c2c,#7b1f1f)", "label_en": "Aggressive",   "icon": "▲▲"},
    "やや積極型": {"color": "#c05621", "grad": "linear-gradient(135deg,#c05621,#9a4218)", "label_en": "Growth",       "icon": "▲"},
    "バランス型": {"color": "#2f855a", "grad": "linear-gradient(135deg,#2f855a,#236644)", "label_en": "Balanced",     "icon": "◆"},
    "やや保守型": {"color": "#2b6cb0", "grad": "linear-gradient(135deg,#2b6cb0,#1e4f8a)", "label_en": "Moderate",     "icon": "▼"},
    "保守型":     {"color": "#2c5282", "grad": "linear-gradient(135deg,#2c5282,#1e3a63)", "label_en": "Conservative", "icon": "▼▼"},
}

def build_report_data(
    portfolios, selected_funds, core_fund, core_idx,
    fund_stats, returns_selected, rf_rate,
    show_diagnosis,
) -> dict:
    """比較・診断・カード描画に必要なデータを事前計算して dict で返す。

    U-04 修正：タブスコープ外で定義することで Excel 出力時の NameError を防ぐ。
    """
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



def render_report_panel(
    ctx: dict,
    portfolios, selected_funds, core_fund, core_idx,
    fund_stats, returns_selected, rf_rate,
):
    """統合レポートパネル（プロファイルカード＋3タブ）を描画する。

    ctx は build_report_data() の戻り値。
    _rank_asc/_rank_desc/_profile_commentary は本関数スコープで定義し、
    _all_stats を閉包として正しく参照する。
    """
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


def render_export_section(
    portfolios, selected_funds,
    comparison_df, allocation_df_numeric, fund_stats,
):
    """Excel エクスポートセクション（ダウンロードボタン）を描画する。"""
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
