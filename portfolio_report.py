"""
portfolio_report.py  v1.3.0
=============================
統合レポートパネル・エクスポート機能モジュール。
portfolio_app.py から import して使用する。

修正（v1.3.0 — コードレビュー修正 2026-03）:
✅ [FIX-CFG] compute_rp_portfolio のコア比率・個別上限をハードコードから引数化
   - 旧実装: core_weight_range=(0.50, 0.65), max_individual=0.20 をリテラルで埋め込み。
     portfolio_app.py の optimization_configs["バランス型"] が変更されても
     compute_rp_portfolio だけ旧値を参照し続ける問題があった。
   - 新実装: core_weight_range / max_individual / min_individual を引数として受け取る。
     呼び出し元（portfolio_app.py）が optimization_configs から値を渡すことで一元管理。
     後方互換のためデフォルト値は旧リテラル値と同一に設定。

修正（v1.2.0 — 2026-03）:
  compute_rp_portfolio をモジュールレベルに昇格（importable化）。
  build_report_data に show_rp / rp_result / tr_portfolio 引数を追加。
  render_report_panel にテールリスク最小型カードを追加。
  build_report_data の return バグを修正（show_diagnosis=True 時も正しく返す）。

修正（v1.1.0 — 2026-03）:
  _rank_asc/_rank_desc/_profile_commentary を for ループ外に正しく配置。
"""
import hashlib
import io
import warnings
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from portfolio_charts import donut_svg as _donut_svg, badge as _badge  # [ISSUE-3修正] 公開 API から import
from portfolio_utils import PortfolioAnalyzer

# ── デザインシステム定数 ───────────────────────────────────────
_PROFILE_META = {
    "積極型":         {"color": "#9b2c2c", "grad": "linear-gradient(135deg,#9b2c2c,#7b1f1f)", "label_en": "Aggressive",   "icon": "▲▲"},
    "やや積極型":     {"color": "#c05621", "grad": "linear-gradient(135deg,#c05621,#9a4218)", "label_en": "Growth",       "icon": "▲"},
    "バランス型":     {"color": "#2f855a", "grad": "linear-gradient(135deg,#2f855a,#236644)", "label_en": "Balanced",     "icon": "◆"},
    "やや保守型":     {"color": "#2b6cb0", "grad": "linear-gradient(135deg,#2b6cb0,#1e4f8a)", "label_en": "Moderate",     "icon": "▼"},
    "保守型":         {"color": "#2c5282", "grad": "linear-gradient(135deg,#2c5282,#1e3a63)", "label_en": "Conservative", "icon": "▼▼"},
    "リスクパリティ": {"color": "#6366f1", "grad": "linear-gradient(135deg,#4338ca,#6366f1)", "label_en": "Risk Parity",  "icon": ""},
    "テールリスク最小型": {"color": "#553c9a", "grad": "linear-gradient(135deg,#44337a,#6b46c1)", "label_en": "Tail-Risk Min", "icon": ""},
}

# ── 標準5プロファイル定数（比較テーブル・カード等で使用） ─────
_STANDARD_PROFILES = ["積極型", "やや積極型", "バランス型", "やや保守型", "保守型"]


@st.cache_data(show_spinner=False)
def compute_rp_portfolio(
    _rets, _funds_tuple, _core_name, _lw: bool, _rf: float,
    data_hash: str = "",
    core_weight_range: tuple = (0.50, 0.65),
    max_individual: float = 0.20,
    min_individual: float = 0.03,
):
    """リスクパリティポートフォリオを計算してキャッシュする。

    コアウェイト制約（デフォルトはバランス型と同一：50〜65%）を維持したまま、
    サテライト各ファンドのリスク寄与（Risk Contribution）を均等化した配分を算出。

    Parameters
    ----------
    core_weight_range : tuple
        コアファンドのウェイト範囲。デフォルト (0.50, 0.65)。
        [FIX-CFG] 旧実装はリテラル (0.50, 0.65) をハードコードしていたため、
        portfolio_app.py の optimization_configs["バランス型"]["core_range"] が
        変更されても compute_rp_portfolio だけ古い値を参照し続ける問題があった。
        引数化することで呼び出し側が optimization_configs から一元管理できる。
    max_individual : float
        個別ファンドの上限ウェイト。デフォルト 0.20。
    min_individual : float
        個別ファンドの下限ウェイト（自動調整の基準値）。デフォルト 0.03。

    Returns
    -------
    tuple[np.ndarray, dict, float]
        (weights, stats, risk_contribution_cv)
        risk_contribution_cv: サテライトのリスク寄与 CV（変動係数）。0%に近いほど均等化が達成されている。
    """
    _az  = PortfolioAnalyzer(_rets, risk_free_rate=_rf, use_ledoit_wolf=_lw)
    _ci  = list(_funds_tuple).index(_core_name)

    # O-04 相当: 下限可行性チェック
    # コア最小値 + サテライト本数 × min_individual > 1.0 になると最適化が収束しない。
    # portfolio_app.py のO-04修正と同一ロジックでここでも自動調整する。
    _core_lo    = core_weight_range[0]
    _max_ind    = max_individual
    _min_ind    = min_individual
    _n_sat      = max(len(_funds_tuple) - 1, 1)
    if _core_lo + _n_sat * _min_ind > 1.0 + 1e-6:
        _min_ind = max(0.0, (1.0 - _core_lo) / _n_sat - 1e-6)
        warnings.warn(
            f"compute_rp_portfolio: 下限可行性違反のため min_individual を "
            f"{_min_ind:.4f} に自動調整します "
            f"(core_min={_core_lo}, n_satellite={_n_sat})",
            RuntimeWarning,
            stacklevel=2,
        )

    _w   = _az.optimize_portfolio(
        _ci,
        core_weight_range=core_weight_range,
        objective_type="risk_parity",
        max_individual=_max_ind,
        min_individual=_min_ind,
    )
    _st  = _az.calculate_portfolio_stats(_w)
    _cov = _az.cov_matrix.values
    _vol = np.sqrt(_w @ _cov @ _w)
    _mrc = _cov @ _w
    _rc  = _w * _mrc / _vol if _vol > 1e-8 else np.zeros_like(_w)
    _non_core = np.array([i != _ci for i in range(len(_w))])
    _rc_sat   = _rc[_non_core]
    _rc_cv    = (_rc_sat.std() / _rc_sat.mean() * 100) if _rc_sat.mean() > 1e-8 else 0.0
    return _w, _st, float(_rc_cv)

def build_report_data(
    portfolios, selected_funds, core_fund, core_idx,
    fund_stats, returns_selected, rf_rate,
    show_diagnosis,
    show_rp: bool = False,
    rp_result=None,
    tr_portfolio=None,
) -> dict:
    """比較・診断・カード描画に必要なデータを事前計算して dict で返す。

    Parameters
    ----------
    show_rp : bool
        True のとき、comparison_df にリスクパリティとテールリスク最小型の行を追加する。
    rp_result : tuple | None
        compute_rp_portfolio() の戻り値 (weights, stats, rc_cv)。
    tr_portfolio : dict | None
        portfolios["テールリスク最小型"] の値（weights / stats / config）。
    """
    # ─── comparison_df：最適化直後にタブスコープ外で定義 ──────────
    # U-04 修正：_rpt_tab1 内で定義すると、タブが描画されなかった場合に
    # Excelエクスポート処理で NameError が発生するため、ここで事前計算する。
    #
    # 数値ベース統一：すべての列を float/int で保持し、表示フォーマットは
    # 参照側（st.dataframe の column_config や Excel 出力）に委ねる。
    # 旧実装は "12.34%" 形式の文字列を生成し、Excel 出力時に
    # .replace('%','') で逆変換していたため、書式変更で無言に壊れるリスクがあった。

    def _pf_row(name, cps, cpw):
        return {
            "プロファイル":  name,
            "年平均リターン":  round(cps["年率リターン"]      * 100, 2),
            "年率価格変動リスク":  round(cps["年率ボラティリティ"] * 100, 2),
            "シャープ":      round(cps["シャープレシオ"],          3),
            "ソルティノ":    round(cps["ソルティノレシオ"],         3),
            "最大DD":        round(cps["最大ドローダウン"]   * 100, 2),
            "カルマー":      round(cps["カルマー比率"],            3),
            "コア比率":      round(float(cpw[core_idx])     * 100, 1),
            "ファンド数":    int((cpw > 0.01).sum()),
        }

    _comparison_data = []
    # 標準5プロファイルのみを基本行として追加（テールリスク最小型は別扱い）
    for _cpname in _STANDARD_PROFILES:
        if _cpname not in portfolios:
            continue
        _cpf = portfolios[_cpname]
        _comparison_data.append(_pf_row(_cpname, _cpf["stats"], _cpf["weights"]))

    # ── チェックボックスON時：リスクパリティ・テールリスク最小型を追加 ──
    if show_rp:
        if rp_result is not None:
            _rp_w, _rp_st, _ = rp_result
            _comparison_data.append(_pf_row("リスクパリティ", _rp_st, _rp_w))
        if tr_portfolio is not None:
            _tr_w = tr_portfolio["weights"]
            _tr_st = tr_portfolio["stats"]
            _comparison_data.append(_pf_row("テールリスク最小型", _tr_st, _tr_w))

    comparison_df = pd.DataFrame(_comparison_data)

    # ── 表示用フォーマット辞書（st.dataframe の column_config で使用）──────
    _comparison_col_cfg = {
        "年平均リターン": st.column_config.NumberColumn("年平均リターン(%)", format="%+.2f%%"),
        "年率価格変動リスク": st.column_config.NumberColumn("年率価格変動リスク(%)", format="%.2f%%"),
        "シャープ":     st.column_config.NumberColumn("シャープ",        format="%.3f"),
        "ソルティノ":   st.column_config.NumberColumn("ソルティノ",       format="%.3f"),
        "最大DD":       st.column_config.NumberColumn("最大DD(%)",        format="%.2f%%"),
        "カルマー":     st.column_config.NumberColumn("カルマー",         format="%.3f"),
        "コア比率":     st.column_config.NumberColumn("コア比率(%)",      format="%.1f%%"),
        "ファンド数":   st.column_config.NumberColumn("ファンド数",       format="%d本"),
    }


    # ─── 健全性チェック ＋ コアファンド情報バー（診断パネル）────────
    # [ISSUE-6修正] 旧実装は st.session_state.get('show_diagnosis') を直接参照していたが、
    # 引数として受け取った show_diagnosis を一貫して使用するよう修正する。
    #
    # [BUG-Ph4修正] 旧実装は show_diagnosis=True 時に st.markdown() を直接呼び出しており、
    # データ構築関数が UI 描画（副作用）を内包していた。これを修正し:
    #   - 健全性チェックの結果は health_warnings（HTMLリスト）として返す
    #   - コアバーの HTML は core_bar_html として返す
    #   - 実際の st.markdown() 呼び出しは render_report_panel が行う
    # これにより build_report_data は純粋なデータ計算関数になり、
    # テスト環境での呼び出しや将来の再利用が可能になる。
    _health_warnings: list = []   # (html_str,) のリスト
    _core_bar_html: str = ""

    if show_diagnosis:
        # [ISSUE-6修正] aggressive_vol / conservative_vol を削除。
        # BUG-1修正（2026-03）で if/else ブランチを整理した際、
        # 単調性チェックが _vols リスト方式に変更されたにもかかわらず
        # 旧実装の2変数定義だけが残留していた（一切参照されていないデッドコード）。
        core_stats_fs    = fund_stats.loc[core_fund]
        core_sharpe      = core_stats_fs['シャープレシオ']
        core_volatility  = core_stats_fs['年率ボラ']
        core_return      = core_stats_fs['年率リターン']

        # ── 単調性チェック：保守→積極の順にリターン↑・ボラ↑が成立するか確認 ──
        # elif 連鎖ではなく独立した if で評価し、複数の問題を同時に表示できるようにする
        _p_order = ["保守型", "やや保守型", "バランス型", "やや積極型", "積極型"]
        _p_avail = [p for p in _p_order if p in portfolios]   # 存在するプロファイルのみ
        _vols    = [portfolios[p]['stats']['年率ボラティリティ'] for p in _p_avail]
        _rets    = [portfolios[p]['stats']['年率リターン']       for p in _p_avail]
        _srs     = [portfolios[p]['stats']['シャープレシオ']     for p in _p_avail]

        _mono_vol_ok = all(_vols[i] <= _vols[i+1] for i in range(len(_vols)-1))
        _mono_ret_ok = all(_rets[i] <= _rets[i+1] for i in range(len(_rets)-1))

        # ボラティリティ単調性違反があるプロファイルペアを特定
        _vol_violations = [
            f"{_p_avail[i]}({_vols[i]*100:.1f}%) > {_p_avail[i+1]}({_vols[i+1]*100:.1f}%)"
            for i in range(len(_vols)-1) if _vols[i] > _vols[i+1]
        ]
        _ret_violations = [
            f"{_p_avail[i]}({_rets[i]*100:.1f}%) > {_p_avail[i+1]}({_rets[i+1]*100:.1f}%)"
            for i in range(len(_rets)-1) if _rets[i] > _rets[i+1]
        ]
        # シャープレシオ：バランス型が最も高効率であるべきという期待に反するケースを検出
        # 保守型のシャープがバランス型を大きく上回る場合、コアが効率的すぎてサテライトが足を引っ張っている
        _any_warn = False
        if "バランス型" in _p_avail and "保守型" in _p_avail:
            _bal_idx  = _p_avail.index("バランス型")
            _cons_idx = _p_avail.index("保守型")
            _sr_bal_vs_cons_warn = (
                _srs[_cons_idx] > _srs[_bal_idx] + 0.1  # 0.1超の差で警告（軽微な逆転はノイズのため無視）
            )
        else:
            _sr_bal_vs_cons_warn = False
            _bal_idx = _cons_idx = 0  # unused sentinel

        if not _mono_vol_ok:
            _any_warn = True
            _viol_str = "　/　".join(_vol_violations)
            _health_warnings.append(
                f'<div class="health-warn">⚠️ <b>ボラティリティの逆転</b>　'
                f'保守→積極の順にリスクが増加すべきところ、以下のプロファイル間で逆転しています。<br>'
                f'<span style="font-size:0.92rem;">{_viol_str}</span><br>'
                f'コアファンドの変更またはスクリーニング条件の調整をご検討ください。</div>'
            )

        if not _mono_ret_ok:
            _any_warn = True
            _viol_str = "　/　".join(_ret_violations)
            _health_warnings.append(
                f'<div class="health-warn">⚠️ <b>リターンの逆転</b>　'
                f'保守→積極の順にリターンが増加すべきところ、以下のプロファイル間で逆転しています。<br>'
                f'<span style="font-size:0.92rem;">{_viol_str}</span><br>'
                f'サテライトファンドの質（シャープレシオ）をご確認ください。</div>'
            )

        if _sr_bal_vs_cons_warn:
            _any_warn = True
            _health_warnings.append(
                f'<div class="health-warn">⚠️ <b>シャープレシオの逆転</b>　'
                f'保守型（{_srs[_cons_idx]:.2f}）のリスク効率がバランス型（{_srs[_bal_idx]:.2f}）を大きく上回っています。<br>'
                f'サテライトファンドがポートフォリオ効率を低下させている可能性があります。'
                f'スクリーニング条件の見直しをご検討ください。</div>'
            )

        if core_sharpe < 0.5:
            _any_warn = True
            _health_warnings.append(
                f'<div class="health-warn">⚠️ <b>コアファンドの効率性</b>　シャープレシオ {core_sharpe:.2f} は目安（0.5）を下回っています。'
                f'別のファンドをコアとすることで全体効率が改善する可能性があります。</div>'
            )

        if not _any_warn:
            _health_warnings.append(
                f'<div class="health-ok">✅ <b>ポートフォリオは健全です</b>　'
                f'保守→積極の順にリスク・リターンが単調増加しています。'
                f'コアファンドのシャープレシオ（{core_sharpe:.2f}）も良好です。</div>'
            )

        _ret_sign = "+" if core_return >= 0 else ""
        _core_bar_html = (
            f'<div class="core-bar">'
            f'<span class="core-bar-label">★ コアファンド</span>'
            f'<span class="core-bar-name">{core_fund}</span>'
            f'<span style="color:#dde3ea">|</span>'
            f'<span class="core-bar-item">年平均リターン <b style="color:{"#1e8449" if core_return>=0 else "#c0392b"}">{_ret_sign}{core_return*100:.1f}%</b></span>'
            f'<span class="core-bar-item">ボラ <b>{core_volatility*100:.1f}%</b></span>'
            f'<span class="core-bar-item">シャープ <b style="color:{"#1e8449" if core_sharpe>=1 else "#d35400"}">{core_sharpe:.2f}</b></span>'
            f'<span class="core-bar-item">最大DD <b style="color:#c0392b">{core_stats_fs["最大DD"]*100:.1f}%</b></span>'
            f'<span style="color:#dde3ea">|</span>'
            f'<span class="core-bar-item" style="color:#7a5c00;">無リスク金利 <b>{rf_rate*100:.1f}%</b></span>'
            f'</div>'
        )
    else:
        # 変数は後続処理（コアバー in tab2等）でも参照されるため計算だけ実施
        core_stats_fs   = fund_stats.loc[core_fund]
        core_sharpe     = core_stats_fs['シャープレシオ']
        core_volatility = core_stats_fs['年率ボラ']
        core_return     = core_stats_fs['年率リターン']

    # ── 計算済みデータを dict で返す（show_diagnosis の if/else を抜けた後に必ず実行）──
    # v1.2.0 バグ修正: 旧実装では else ブロック内にのみ return があったため、
    # show_diagnosis=True の場合に None が返されていた。
    return {
        "comparison_df":       comparison_df,
        "_comparison_col_cfg": _comparison_col_cfg,
        "core_stats_fs":       core_stats_fs,
        "core_sharpe":         core_sharpe,
        "core_volatility":     core_volatility,
        "core_return":         core_return,
        # [BUG-Ph4修正] 健全性チェック結果を HTML 文字列リストで返す。
        # 描画は呼び出し元（render_report_panel）が行う。
        "health_warnings":     _health_warnings,
        "core_bar_html":       _core_bar_html,
    }


def render_report_panel(
    ctx: dict,
    portfolios, selected_funds, core_fund, core_idx,
    fund_stats, returns_selected, rf_rate,
    show_rp: bool = False,
    overview_raw=None,
    use_lw: bool = False,
    rp_result=None,
    tr_portfolio=None,
):
    """統合レポートパネル（プロファイルカード＋3タブ）を描画する。"""
    # _show_rp のみローカル変数にバインド（条件分岐で複数箇所から参照するため）
    # use_lw / rp_result / tr_portfolio は直接パラメータ名で参照する
    _show_rp = show_rp
    if overview_raw is None:
        overview_raw = pd.DataFrame()

    # [ISSUE-1修正] ctx から計算済みデータを展開して再利用する。
    # 旧実装では ctx が引数として渡されながら render_report_panel 内で一切参照されず、
    # build_report_data() による事前計算の恩恵を受けていなかった。
    # comparison_df / _comparison_col_cfg は比較サマリータブに表示し、
    # ctx 内の値を実際に使うことで設計と実装を一致させる。
    comparison_df       = ctx.get("comparison_df",       pd.DataFrame())
    _comparison_col_cfg = ctx.get("_comparison_col_cfg", {})

    # [BUG-Ph4修正] build_report_data が生成した健全性チェック HTML を描画。
    # 旧実装では build_report_data 内で直接 st.markdown() を呼んでいたが、
    # データ計算関数が UI 副作用を持つべきでないため、描画責任をここに移した。
    for _hw in ctx.get("health_warnings", []):
        st.markdown(_hw, unsafe_allow_html=True)
    _core_bar_html = ctx.get("core_bar_html", "")
    if _core_bar_html:
        st.markdown(_core_bar_html, unsafe_allow_html=True)

    # ─── プロファイルカード ───────────────────────────────────
    # ─── 統合レポートパネル（3タブ構成: 比較/構成/リスク・リターン）──────

    # ── 全プロファイルの実績を事前集計（解説文の比較ロジックに使用） ────
    _profile_order_list = ["積極型", "やや積極型", "バランス型", "やや保守型", "保守型"]
    _all_stats = {}
    for _pn in _profile_order_list:
        # [BUG-Ph4付随修正] KeyError ガード: 将来プロファイル削除時やテスト時に
        # portfolios にエントリが存在しない場合でもクラッシュしないよう保護する。
        if _pn not in portfolios:
            continue
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
    _rank_vol  = _rank_asc("vol")            # ボラ低い＝1位（将来の解説文拡張用に保持）
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
        _      = _rank_vol[pname]  # ボラ順位 — 将来の解説文拡張用（現在は r_dd/r_sr/r_ret で解説）
        r_dd   = _rank_dd[pname]   # 1=下落最小、5=下落最大

        # ── 第1文：リターンの位置づけ ──────────────────────────
        if r_ret == 1:
            sent1 = f"分析期間の年平均リターンは{ret_sign}{ret_:.1f}%と、5プロファイル中最高でした。"
        elif r_ret == 5:
            sent1 = f"分析期間の年平均リターンは{ret_sign}{ret_:.1f}%と、5プロファイル中最も低い水準でした。"
        else:
            sent1 = f"分析期間の年平均リターンは{ret_sign}{ret_:.1f}%（5プロファイル中{_ordinal_jp(r_ret)}水準）でした。"

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
        f'<div class="report-panel-icon">■</div>'
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
        "比較サマリー",
        "ファンド構成",
        "リスク・リターン分析",
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
                f'        <div class="profile-card-ret-label">年平均リターン（実績）</div>'
                f'      </div>'
                f'    </div>'
                f'  </div>'
                f'  <div class="profile-card-body">'
                f'    <div class="profile-card-row">'
                f'      <span class="profile-card-row-label">年率価格変動リスク'
                f'      </span>'
                f'      <span class="profile-card-row-val">{vol_:.1f}%</span>'
                f'    </div>'
                f'    <div class="profile-card-row">'
                f'      <span class="profile-card-row-label">シャープレシオ'
                f'      </span>'
                f'      <span class="profile-card-row-val" style="color:{sr_color};">{sr_:.2f}</span>'
                f'    </div>'
                f'    <div class="profile-card-row">'
                f'      <span class="profile-card-row-label">最大DD（実績）'
                f'        <span class="profile-card-row-label-sub">分析期間中の<br>最大下落率</span>'
                f'      </span>'
                f'      <span class="profile-card-row-val" style="color:#c0392b;">{dd_:.1f}%</span>'
                f'    </div>'
                f'    <div class="profile-card-row">'
                f'      <span class="profile-card-row-label">組入ファンド数'
                f'      </span>'
                f'      <span class="profile-card-row-val">{n_funds_}本</span>'
                f'    </div>'
                f'    <div class="risk-bar-wrap">'
                f'      <div style="font-size:1.06rem;color:#445563;margin-bottom:3px;">リスク水準</div>'
                f'      <div class="risk-bar-track">'
                f'        <div class="risk-bar-fill" style="width:{bar_w:.0f}%;background:{c_};"></div>'
                f'      </div>'
                f'      <div style="text-align:right;font-size:0.75rem;font-weight:700;color:{c_};margin-top:2px;">{vol_:.1f}%</div>'
                f'    </div>'
                f'  </div>'
                f'</div>'
            )
        cards_html += '</div>'
        st.markdown(cards_html, unsafe_allow_html=True)

        # ── プロファイル選択ボタン行 ──────────────────────────────
        _btn_cols = st.columns(5)
        for _bi, _bpname in enumerate(profile_order_list):
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
            f'font-size:1.06rem;font-weight:600;color:#2c3e50;line-height:1.95;">'
            f'<span style="font-size:1.15rem;font-weight:800;color:{_spmeta["color"]};margin-right:8px;">{_spname}</span>'
            f'{_sp_text}'
            f'</div>',
            unsafe_allow_html=True
        )

        # ── シャープレシオ凡例 ─────────────────────────────────────
        st.markdown(
            '<div class="sr-legend-wrap">'
            '<span>シャープレシオの目安：</span>'
            '<span class="sr-legend-chip" style="background:#e6f5ed;color:#1e7a4e;"><span style="color:#1e7a4e;">■</span> 1.0以上 ＝ 高効率</span>'
            '<span class="sr-legend-chip" style="background:#fff3e0;color:#c96a1a;"><span style="color:#c96a1a;">■</span> 0.5〜1.0 ＝ 標準的</span>'
            '<span class="sr-legend-chip" style="background:#fde9e6;color:#c0392b;"><span style="color:#c0392b;">■</span> 0.5未満 ＝ 要確認</span>'
            '</div>',
            unsafe_allow_html=True
        )

        # ── [改善F] リスクパリティ & テールリスク最小型 カード（サイドバーチェック時のみ） ──
        if _show_rp:
            # ヘッダーバー
            st.markdown(
                '<div style="margin-top:16px;padding:6px 0 4px 0;'
                'border-top:1px solid rgba(99,102,241,0.25);">'
                '<span style="font-size:0.90rem;font-weight:800;letter-spacing:0.1em;'
                'text-transform:uppercase;color:#6366f1;">リスクパリティ配分（参考）</span>'
                '<span style="font-size:0.75rem;color:#64748b;margin-left:8px;">'
                'サテライトのリスク寄与を均等化した配分 / テールリスク最小型（CVaR最小化）</span>'
                '</div>',
                unsafe_allow_html=True,
            )

            # ── リスクパリティ カード ─────────────────────────────
            if rp_result is not None:
                try:
                    _rp_w, _rp_st, _rp_rc_cv = rp_result
                    _rp_ret  = _rp_st['年率リターン'] * 100
                    _rp_vol  = _rp_st['年率ボラティリティ'] * 100
                    _rp_sr   = _rp_st['シャープレシオ']
                    _rp_dd   = _rp_st['最大ドローダウン'] * 100
                    _rp_core = _rp_w[core_idx] * 100
                    _rp_nf   = int((_rp_w > 0.01).sum())
                    _rp_ret_sign = "+" if _rp_ret >= 0 else ""
                    _rp_sr_color = "#1e8449" if _rp_sr >= 1.0 else ("#d35400" if _rp_sr >= 0.5 else "#c0392b")
                    _rp_donut    = _donut_svg(_rp_core, "rgba(255,255,255,0.9)")

                    _rp_card_html = (
                        f'<div class="profile-card" style="border-color:#6366f140;max-width:300px;">'
                        f'  <div class="profile-card-header" style="background:linear-gradient(135deg,#4338ca,#6366f1);">'
                        f'    <div class="profile-card-eyebrow">RISK PARITY</div>'
                        f'    <div class="profile-card-title">リスクパリティ</div>'
                        f'    <div class="profile-card-range">コア比率 50–65%（バランス型と同一）</div>'
                        f'    <div class="profile-card-top">'
                        f'      {_rp_donut}'
                        f'      <div style="text-align:right;">'
                        f'        <div class="profile-card-ret">{_rp_ret_sign}{_rp_ret:.1f}%</div>'
                        f'        <div class="profile-card-ret-label">年平均リターン（実績）</div>'
                        f'      </div>'
                        f'    </div>'
                        f'  </div>'
                        f'  <div class="profile-card-body">'
                        f'    <div class="profile-card-row">'
                        f'      <span class="profile-card-row-label">年率価格変動リスク'
                        f'      </span>'
                        f'      <span class="profile-card-row-val">{_rp_vol:.1f}%</span>'
                        f'    </div>'
                        f'    <div class="profile-card-row">'
                        f'      <span class="profile-card-row-label">シャープレシオ'
                        f'      </span>'
                        f'      <span class="profile-card-row-val" style="color:{_rp_sr_color};">{_rp_sr:.2f}</span>'
                        f'    </div>'
                        f'    <div class="profile-card-row">'
                        f'      <span class="profile-card-row-label">最大DD（実績）'
                        f'        <span class="profile-card-row-label-sub">分析期間中の<br>最大下落率</span>'
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
                        f'      </span>'
                        f'      <span class="profile-card-row-val">{_rp_nf}本</span>'
                        f'    </div>'
                        f'  </div>'
                        f'</div>'
                    )
                except Exception as _rp_err:
                    _rp_card_html = f'<div style="color:#c0392b;font-size:0.92rem;">⚠️ リスクパリティ最適化失敗: {_rp_err}</div>'
            else:
                _rp_card_html = ""

            # ── テールリスク最小型 カード ─────────────────────────
            _tr_card_html = ""
            if tr_portfolio is not None:
                try:
                    _tr_w  = tr_portfolio["weights"]
                    _tr_st = tr_portfolio["stats"]
                    _tr_ret  = _tr_st['年率リターン'] * 100
                    _tr_vol  = _tr_st['年率ボラティリティ'] * 100
                    _tr_sr   = _tr_st['シャープレシオ']
                    _tr_dd   = _tr_st['最大ドローダウン'] * 100
                    _tr_core = _tr_w[core_idx] * 100
                    _tr_nf   = int((_tr_w > 0.01).sum())
                    _tr_ret_sign = "+" if _tr_ret >= 0 else ""
                    _tr_sr_color = "#1e8449" if _tr_sr >= 1.0 else ("#d35400" if _tr_sr >= 0.5 else "#c0392b")
                    _tr_donut    = _donut_svg(_tr_core, "rgba(255,255,255,0.9)")
                    # CVaR（月次）を取得 — stats に格納済みの場合はそれを使用
                    _tr_cvar = _tr_st.get('月次CVaR_95', None)
                    _tr_cvar_str = f"{_tr_cvar*100:.2f}%" if _tr_cvar is not None else "—"

                    _tr_card_html = (
                        f'<div class="profile-card" style="border-color:#553c9a40;max-width:300px;">'
                        f'  <div class="profile-card-header" style="background:linear-gradient(135deg,#44337a,#6b46c1);">'
                        f'    <div class="profile-card-eyebrow">TAIL-RISK MIN</div>'
                        f'    <div class="profile-card-title">テールリスク最小型</div>'
                        f'    <div class="profile-card-range">コア比率 70–85%（CVaR最小化）</div>'
                        f'    <div class="profile-card-top">'
                        f'      {_tr_donut}'
                        f'      <div style="text-align:right;">'
                        f'        <div class="profile-card-ret">{_tr_ret_sign}{_tr_ret:.1f}%</div>'
                        f'        <div class="profile-card-ret-label">年平均リターン（実績）</div>'
                        f'      </div>'
                        f'    </div>'
                        f'  </div>'
                        f'  <div class="profile-card-body">'
                        f'    <div class="profile-card-row">'
                        f'      <span class="profile-card-row-label">年率価格変動リスク'
                        f'      </span>'
                        f'      <span class="profile-card-row-val">{_tr_vol:.1f}%</span>'
                        f'    </div>'
                        f'    <div class="profile-card-row">'
                        f'      <span class="profile-card-row-label">シャープレシオ'
                        f'      </span>'
                        f'      <span class="profile-card-row-val" style="color:{_tr_sr_color};">{_tr_sr:.2f}</span>'
                        f'    </div>'
                        f'    <div class="profile-card-row">'
                        f'      <span class="profile-card-row-label">最大DD（実績）'
                        f'        <span class="profile-card-row-label-sub">分析期間中の<br>最大下落率</span>'
                        f'      </span>'
                        f'      <span class="profile-card-row-val" style="color:#c0392b;">{_tr_dd:.1f}%</span>'
                        f'    </div>'
                        f'    <div class="profile-card-row">'
                        f'      <span class="profile-card-row-label">月次CVaR 95%'
                        f'        <span class="profile-card-row-label-sub">ワースト5%月の平均損失</span>'
                        f'      </span>'
                        f'      <span class="profile-card-row-val" style="color:#553c9a;">{_tr_cvar_str}</span>'
                        f'    </div>'
                        f'    <div class="profile-card-row">'
                        f'      <span class="profile-card-row-label">組入ファンド数'
                        f'      </span>'
                        f'      <span class="profile-card-row-val">{_tr_nf}本</span>'
                        f'    </div>'
                        f'  </div>'
                        f'</div>'
                    )
                except Exception as _tr_err:
                    _tr_card_html = f'<div style="color:#c0392b;font-size:0.92rem;">⚠️ テールリスク最小型表示失敗: {_tr_err}</div>'

            # ── 2カードを横並び表示 ────────────────────────────────
            if _rp_card_html or _tr_card_html:
                st.markdown(
                    f'<div class="profile-cards-wrap">{_rp_card_html}{_tr_card_html}</div>',
                    unsafe_allow_html=True,
                )
                st.caption(
                    "**リスクパリティ**：各サテライトのリスク寄与（RC）が均等になるよう配分。「リスク寄与CV」が0%に近いほど均等。"
                    "　**テールリスク最小型**：CVaR（ワースト5%月の平均損失）を直接最小化。正規分布を前提としないためヘッジファンド特有の"
                    "ファットテール・左歪み分布に対応。超保守クライアント向けの参考値としてご活用ください。"
                )

        # ─── 詳細メトリクスバッジ（全5プロファイル・サイドバーチェックで制御）──
        if st.session_state.get('show_profile_metrics', False):
            st.markdown('<div class="section-header">全プロファイル 詳細指標</div>', unsafe_allow_html=True)
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
                st.markdown(f'<div style="font-size:0.90rem;font-weight:700;color:{c_};margin:10px 0 4px;">{pname}</div>', unsafe_allow_html=True)
                badges_html = (
                    '<div class="metric-badges-wrap">'
                    + _badge("年平均リターン", f"{ret_sign}{ret_:.2f}%", "複利", c_)
                    + _badge("年率価格変動リスク", f"{vol_:.2f}%",           "リスク水準", c_)
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

        # ── [ISSUE-1修正] 5プロファイル比較テーブルを tab1 末尾に表示 ──────
        # 旧実装では comparison_df が build_report_data() で生成されながら
        # render_report_panel 内で表示されていなかった（設計と実装の乖離）。
        # ctx から取り出した comparison_df をここで描画することで、
        # 「比較サマリー」タブの内容を完結させる。
        # [FIX-LOW-Ph4-2] _comparison_col_cfg が column_config=で正しく渡されていることを確認済み（L831）。
        # build_report_data で生成→ctx 経由で渡される→ここで使用という流れが意図通り機能している。
        if not comparison_df.empty:
            st.markdown('<hr style="border:none;border-top:1px solid #e2e8f0;margin:18px 0 12px 0;">', unsafe_allow_html=True)
            _cmp_title = "5プロファイル + 参考配分 数値比較" if _show_rp else "5プロファイル 数値比較"
            st.markdown(
                f'<div class="tab-sub-header">{_cmp_title}</div>',
                unsafe_allow_html=True,
            )
            st.dataframe(
                comparison_df,
                column_config=_comparison_col_cfg,
                use_container_width=True,
                hide_index=True,
            )
            _cmp_caption = "年平均リターン・最大DD は複利（CAGR）ベース。シャープ・ソルティノ・カルマーは高いほど優秀。　コア比率はポートフォリオ内のコアファンド比率。"
            if _show_rp:
                _cmp_caption += "　リスクパリティ・テールリスク最小型はサイドバーチェックON時に追加表示される参考プロファイルです。"
            st.caption(_cmp_caption)

    with _rpt_tab2:
        st.markdown(
            f'<div class="core-bar">'
            f'<span class="core-bar-label">コアファンド</span>'
            f'<span class="core-bar-name">{core_fund}</span>'
            f'<span class="core-bar-item">（全プロファイル共通）</span>'
            f'</div>',
            unsafe_allow_html=True
        )
        st.markdown('<div class="tab-sub-header">プロファイル別 ファンド構成</div>', unsafe_allow_html=True)

        # ファンド構成テーブルは標準5プロファイルのみを対象とする
        # テールリスク最小型 / リスクパリティは portfolios dict に入っているが
        # 構成表の列には含めない（allocation_df の列が増えすぎるのを防ぐ）
        _tab2_profiles = [p for p in _STANDARD_PROFILES if p in portfolios]

        # 各プロファイルの投資比率を列として構築（転置形式）
        allocation_data = {}

        # 全ファンドでウェイトが1%以上あるものを収集
        funds_with_weights = set()
        for profile_name in _tab2_profiles:
            w = portfolios[profile_name]["weights"]
            for i, fund in enumerate(selected_funds):
                if w[i] >= 0.01:
                    funds_with_weights.add(fund)

        # ファンドをキーとした辞書を作成
        for fund in selected_funds:
            if fund in funds_with_weights:
                allocation_data[fund] = {}
                for profile_name in _tab2_profiles:
                    w = portfolios[profile_name]["weights"]
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
                for profile_name in _tab2_profiles:
                    w = portfolios[profile_name]["weights"]
                    fund_idx = selected_funds.index(fund)
                    allocation_data_numeric[fund][profile_name] = (
                        round(w[fund_idx] * 100, 1) if w[fund_idx] >= 0.01 else 0.0
                    )
        allocation_df_numeric = pd.DataFrame.from_dict(allocation_data_numeric, orient='index')
        allocation_df_numeric = allocation_df_numeric[_tab2_profiles]
        allocation_df_numeric.index.name = "ファンド"
        if core_fund in allocation_df_numeric.index:
            _other = [f for f in allocation_df_numeric.index if f != core_fund]
            allocation_df_numeric = allocation_df_numeric.loc[[core_fund] + _other]

        # プロファイルの順序を指定（_tab2_profiles と統一）
        allocation_df = allocation_df[_tab2_profiles]

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

        # [Fix B] HTMLテーブル方式に切り替えたため旧Styler関数は不要

        # [Fix B] st.dataframe の Styler では列ヘッダーの white-space: pre-line が
        # Streamlit AgGrid 上で無視されスクロールが発生する。
        # HTMLテーブルを st.markdown で直接描画することで列名折り返しを確実に実現する。

        # ── フォーマット関数 ─────────────────────────────────────
        def _fmt_ret(v):
            return f"{v:+.1f}%" if pd.notna(v) else "—"
        def _fmt_vol(v):
            return f"{v:.1f}%" if pd.notna(v) else "—"
        def _fmt_sr(v):
            return f"{v:.2f}" if pd.notna(v) else "—"
        def _fmt_dd(v):
            return f"{v:.1f}%" if pd.notna(v) else "—"
        def _fmt_corr(v):
            return f"{v:.2f}" if pd.notna(v) else "—"
        def _fmt_wr(v):
            return f"{v:.0f}%" if pd.notna(v) else "—"

        # ── セル背景色 ─────────────────────────────────────────
        def _bg_ret(v):
            if pd.isna(v): return ''
            if v >= 10:    return '#86efac'
            if v >= 3:     return '#bbf7d0'
            if v >= 0:     return '#dcfce7'
            if v >= -5:    return '#fee2e2'
            return '#fca5a5'
        def _bg_sr(v):
            if pd.isna(v): return ''
            if v >= 1.0:   return '#bbf7d0'
            if v >= 0.5:   return '#fef9c3'
            return '#fee2e2'
        def _bg_dd(v):
            if pd.isna(v): return ''
            if v > -10:    return '#bbf7d0'
            if v > -25:    return '#fef9c3'
            return '#fee2e2'
        def _bg_corr(v):
            if pd.isna(v):          return ''
            if 0.3 <= v <= 0.7:     return '#bbf7d0'
            if 0.7 < v <= 0.9:      return '#fef9c3'
            if v > 0.9:             return '#fca5a5'
            return '#f3f4f6'

        # ── 列定義：(DataFrame列名, 表示ヘッダー(HTMLで<br>折り返し), fmt関数, bg関数) ──
        _col_defs = [
            ('リターン\n分析期間(%)',  'リターン<br>分析期間(%)',  _fmt_ret,  _bg_ret),
            ('リターン\n設定来(%)',    'リターン<br>設定来(%)',    _fmt_ret,  _bg_ret),
            ('年率リスク\n分析期間(%)', '年率リスク<br>分析期間(%)', _fmt_vol, None),
            ('シャープ\n分析期間',     'シャープ<br>分析期間',     _fmt_sr,   _bg_sr),
            ('最大DD\n設定来(%)',      '最大DD<br>設定来(%)',      _fmt_dd,   _bg_dd),
            ('コア相関\n分析期間',     'コア相関<br>分析期間',     _fmt_corr, _bg_corr),
            ('月次勝率\n設定来(%)',    '月次勝率<br>設定来(%)',    _fmt_wr,   None),
        ]

        # ── HTMLテーブル生成 ────────────────────────────────────
        _th_style = (
            'background:#f1f5f9;color:#1e3a5f;font-weight:700;font-size:0.82rem;'
            'text-align:center;padding:6px 8px;border:1px solid #e2e8f0;'
            'white-space:normal;line-height:1.4;min-width:70px;'
        )
        _th_fund_style = (
            'background:#f1f5f9;color:#1e3a5f;font-weight:700;font-size:0.82rem;'
            'text-align:left;padding:6px 10px;border:1px solid #e2e8f0;'
            'min-width:160px;'
        )

        _html_rows = []
        # ヘッダー行
        _header = f'<tr><th style="{_th_fund_style}">ファンド</th>'
        for _, _hdr, _, _ in _col_defs:
            _header += f'<th style="{_th_style}">{_hdr}</th>'
        _header += '</tr>'
        _html_rows.append(_header)

        # データ行
        for _fund_name, _row in _summ_df.iterrows():
            _is_core = (_fund_name == core_fund)
            _row_bg  = '#dbeafe' if _is_core else '#ffffff'
            _row_fw  = 'bold'    if _is_core else 'normal'
            _td_fund = (
                f'<td style="background:{_row_bg};font-weight:{_row_fw};'
                f'font-size:0.82rem;padding:4px 10px;border:1px solid #e2e8f0;'
                f'white-space:nowrap;max-width:220px;overflow:hidden;'
                f'text-overflow:ellipsis;">{_fund_name}</td>'
            )
            _tds = _td_fund
            for _col, _, _fmt, _bg in _col_defs:
                _val = _row.get(_col, np.nan)
                _txt = _fmt(_val)
                _cell_bg = _row_bg if _is_core else (_bg(_val) if _bg else '#ffffff')
                _tds += (
                    f'<td style="background:{_cell_bg};font-weight:{_row_fw};'
                    f'font-size:0.85rem;text-align:center;padding:4px 8px;'
                    f'border:1px solid #e2e8f0;">{_txt}</td>'
                )
            _html_rows.append(f'<tr>{_tds}</tr>')

        _table_html = (
            '<div style="overflow-x:auto;">'
            '<table style="width:100%;border-collapse:collapse;font-family:sans-serif;">'
            + ''.join(_html_rows)
            + '</table></div>'
        )
        st.markdown(_table_html, unsafe_allow_html=True)
        st.markdown(
            f'<div style="font-size:0.78rem;color:rgba(49,51,63,0.6);line-height:1.7;">'
            f'コアファンド「{core_fund}」行は青ハイライト。'
            '　リターン: +10%超=濃緑 / +3〜10%=緑 / 0〜3%=薄緑 / マイナス=赤。'
            '　シャープ: <span style="color:#1e7a4e;">■</span>1.0超 / <span style="color:#d4a017;">■</span>0.5-1.0 / <span style="color:#c0392b;">■</span>0.5未満。'
            '　最大DD: <span style="color:#1e7a4e;">■</span>-10%以内 / <span style="color:#d4a017;">■</span>-10〜-25% / <span style="color:#c0392b;">■</span>-25%超。'
            '　コア相関: <span style="color:#1e7a4e;">■</span>0.3-0.7=分散◎ / <span style="color:#d4a017;">■</span>0.7-0.9=やや高 / <span style="color:#c0392b;">■</span>0.9超=高相関 / 灰=低相関。'
            '　列ヘッダーをクリックで昇順/降順ソートが可能（数値として正しく並び替え）。'
            '</div>',
            unsafe_allow_html=True,
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
                    hovertemplate='%{hovertext}<br>価格変動リスク: %{x:.1f}%<br>年平均リターン: %{y:.1f}%<extra></extra>'
                ))

            # 各ポートフォリオをプロット
            for pname in profile_order_list:
                portfolio = portfolios[pname]
                stats     = portfolio["stats"]
                meta      = _PROFILE_META.get(pname, {"color": "#555"})

                # [バグ②修正] ポートフォリオのX軸を時系列stdに統一
                # stats['年率ボラティリティ'] はLW収縮共分散ベースのため、
                # LW収縮で相関が圧縮された分散ポートフォリオほど実際より低く算出される。
                # 個別ファンドの散布図X（時系列std×√12）・フロンティアX（サンプル共分散）
                # と統一するため、実際のポートフォリオ月次リターン系列から時系列stdを計算する。
                _w_arr   = np.array(portfolio["weights"])
                _port_r  = returns_selected.values @ _w_arr
                _ts_vol  = float(_port_r.std(ddof=1)) * np.sqrt(12) * 100  # 年率% (時系列)

                fig_scatter.add_trace(go.Scatter(
                    x=[_ts_vol],
                    y=[stats['年率リターン'] * 100],
                    mode='markers+text',
                    name=pname,
                    marker=dict(size=18, color=meta["color"],
                                line=dict(color='#fff', width=2)),
                    text=[pname],
                    textposition="top center",
                    textfont=dict(size=13, color=meta["color"]),
                    hovertemplate=(
                        f'<b>{pname}</b><br>'
                        '価格変動リスク: %{x:.1f}%<br>年平均リターン: %{y:.1f}%<extra></extra>'
                    )
                ))

            # ── 有効フロンティア（キャッシュ付き）────────────────────────
            @st.cache_data(show_spinner=False)
            def _cached_efficient_frontier(_rets, _funds_tuple, _rf: float, data_hash: str = ""):
                """有効フロンティアをキャッシュ付きで計算。
                [バグ①②修正] ボラスイープ型（固定vol→最大μ）でCAGR上限を正しく保証。
                フロンティア内部でサンプル共分散を使用するため use_ledoit_wolf 引数は不要。
                """
                _az = PortfolioAnalyzer(_rets, risk_free_rate=_rf, use_ledoit_wolf=False)
                return _az.calculate_efficient_frontier(n_points=25)

            try:
                _ef_hash = hashlib.sha256(
                    pd.util.hash_pandas_object(returns_selected, index=True).values.tobytes()
                ).hexdigest()[:16]
                _ef_df = _cached_efficient_frontier(
                    returns_selected, tuple(selected_funds), rf_rate, _ef_hash
                ).dropna(subset=['ボラティリティ', 'リターン_CAGR'])  # 両列有効な点のみ描画
                if not _ef_df.empty:
                    # 実現系列ベースCAGRを直接参照（散布図Y軸と同定義）
                    _ef_vols = _ef_df['ボラティリティ'].values
                    _ef_cagr = _ef_df['リターン_CAGR'].values
                    fig_scatter.add_trace(go.Scatter(
                        x=_ef_vols * 100,
                        y=_ef_cagr * 100,
                        mode='lines',
                        name='有効フロンティア',
                        line=dict(color='#b3904a', width=1.5, dash='dot'),
                        hovertemplate='有効フロンティア<br>価格変動リスク: %{x:.1f}%<br>年平均リターン(複利): %{y:.1f}%<extra></extra>',
                        showlegend=True
                    ))
            except Exception:
                pass  # フロンティア計算失敗時はサイレントスキップ

            fig_scatter.update_layout(
                # タイトルはタブサブヘッダー（上部 st.markdown）で表示済みのため fig 内では空文字
                # ※ title=None → "undefined" 表示バグ、font.size=0 → バリデーションエラーのため
                #    空文字＋pad=0＋top余白ゼロで実質非表示にする
                title=dict(text="", pad=dict(t=0, b=0)),
                xaxis_title="年率価格変動リスク（ボラティリティ）%",
                yaxis_title="年平均リターン（複利）%",
                hovermode='closest',
                height=400,
                plot_bgcolor='#fafbfc',
                paper_bgcolor='#ffffff',
                xaxis=dict(gridcolor='#e8ecf0', zeroline=False),
                yaxis=dict(gridcolor='#e8ecf0', zeroline=False),
                # legend を X軸タイトルと重ならないよう下マージンを広げて配置
                legend=dict(orientation='h', yanchor='top', y=-0.18, xanchor='center', x=0.5,
                            font=dict(size=12)),
                margin=dict(t=20, b=90, l=50, r=20)
            )
            st.plotly_chart(fig_scatter, use_container_width=True)

        with col_sr:
            st.markdown(
                '<div style="font-size:0.94rem;font-weight:700;color:#1e3a5f;margin-bottom:10px;">'
                'シャープレシオ比較<br>'
                '<span style="font-size:0.90rem;font-weight:400;color:#2f3e4d;">'
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
                '<b>シャープレシオの目安</b><br>'
                '<span style="color:#1e7a4e;">■</span> 1.0以上 ＝ 優秀（リスク効率が高い）<br>'
                '<span style="color:#c96a1a;">■</span> 0.5〜1.0 ＝ 普通<br>'
                '<span style="color:#c0392b;">■</span> 0.5未満 ＝ 要改善<br><br>'
                '国内株式インデックスの長期平均：約0.4〜0.6'
                '</div>'
            )
            bars_html += '</div>'
            st.markdown(bars_html, unsafe_allow_html=True)

    # ── allocation_df_numeric と分析期間を返す ──────────────────
    return allocation_df_numeric, _period_start, _period_end, _period_months


def render_export_section(
    portfolios, selected_funds,
    comparison_df, allocation_df_numeric, fund_stats,
    period_months: int = 0,
):
    """Excel エクスポートセクション（ダウンロードボタン）を描画する。"""
    st.markdown('<div class="section-header">💾 結果のエクスポート</div>', unsafe_allow_html=True)

    # [FIX-LOW-Ph4-1] 旧実装は「st.button でクリック → Excel 生成 → st.download_button 出現」
    # という2クリック構造だった。st.download_button に data= として BytesIO を直接渡すことで
    # 1クリックでダウンロードが完了する UX に改善する。
    # Excel 生成は毎 run で実行されるが、ファンド数 30 本・6プロファイルで < 0.5秒 のため許容範囲。
    # 生成コストを下げたい場合は @st.cache_data で出力バイト列をキャッシュすることを検討。
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:

        # ── ポートフォリオ比較シート ──────────────────────────
        _comp_export = comparison_df.rename(columns={
            "年平均リターン": "年平均リターン(%)",
            "年率価格変動リスク": "年率価格変動リスク(%)",
            "最大DD":       "最大DD(%)",
            "コア比率":     "コア比率(%)",
            "ファンド数":   "ファンド数(本)",
        })
        _comp_export.to_excel(writer, sheet_name='ポートフォリオ比較', index=False)

        # ── 統合ファンド構成シート ────────────────────────────
        allocation_df_numeric.to_excel(writer, sheet_name='統合ファンド構成(%)')

        # ── 各プロファイル個別シート ──────────────────────────
        # 分析期間ラベル（例: 36ヶ月 → "3年"）
        _period_map = {12: "1年", 36: "3年", 60: "5年", 120: "10年", 180: "15年"}
        _period_lbl = _period_map.get(period_months, f"{period_months}ヶ月") if period_months else ""

        for profile_name, portfolio in portfolios.items():
            w    = portfolio["weights"]
            pst  = portfolio["stats"]

            # ── 構成ファンド行（weight > 0.1%）────────────────
            _rows = []
            for i, fund in enumerate(selected_funds):
                _w_pct = round(w[i] * 100, 2)
                if _w_pct <= 0.1:
                    continue
                # fund_stats から個別指標を取得（存在しない列はNaN）
                if fund in fund_stats.index:
                    _fs  = fund_stats.loc[fund]
                    _ret = round(float(_fs.get('年率リターン', float('nan'))) * 100, 2)
                    _vol = round(float(_fs.get('年率ボラ',     float('nan'))) * 100, 2)
                    _sr  = round(float(_fs.get('シャープレシオ', float('nan'))), 6)
                    _mdd = round(float(_fs.get('最大DD',        float('nan'))) * 100, 2)
                else:
                    _ret = _vol = _sr = _mdd = float('nan')

                _rows.append({
                    'ファンド':       fund,
                    '比重(%)':        _w_pct,
                    '年平均リターン(%)': _ret,
                    '年率価格変動リスク(%)': _vol,
                    'シャープ':        _sr,
                    '最大DD(%)':       _mdd,
                })

            _df = pd.DataFrame(_rows).sort_values('比重(%)', ascending=False)

            # ── ポートフォリオ合計行 ──────────────────────────
            _port_ret = round(float(pst.get('年率リターン',       0)) * 100, 2)
            _port_vol = round(float(pst.get('年率ボラティリティ', 0)) * 100, 2)
            _port_sr  = round(float(pst.get('シャープレシオ',     0)), 3)
            _port_mdd = round(float(pst.get('最大ドローダウン',   0)) * 100, 2)

            _summary_label = f"{_period_lbl}{profile_name}ポートフォリオ" if _period_lbl else f"{profile_name}ポートフォリオ"
            _summary_row = pd.DataFrame([{
                'ファンド':       _summary_label,
                # [P3修正] '100%'（文字列）→ 100.0（float）に統一。
                # 文字列混在で列 dtype が object になり Excel での数値ソート・集計が不可になる問題を解消。
                '比重(%)':        100.0,
                '年平均リターン(%)': _port_ret,
                '年率価格変動リスク(%)': _port_vol,
                'シャープ':        _port_sr,
                '最大DD(%)':       _port_mdd,
            }])

            _export_df = pd.concat([_df, _summary_row], ignore_index=True)

            # シート名: Excel の制限（31文字以内、特殊文字禁止）
            # [BUG-Ph4修正] 旧実装は両辺が同一（常に[:28]スライス）だったため
            # 25文字以下の名前でも不要なスライスが実行されていた。
            # 正しくは「28文字以内ならそのまま、超えたら切り詰め」。
            sheet_name = profile_name if len(profile_name) <= 28 else profile_name[:28]
            _export_df.to_excel(writer, sheet_name=sheet_name, index=False)

        # ── ファンド統計シート ────────────────────────────────
        fund_stats_export = fund_stats.copy()
        fund_stats_export['年率リターン'] = (fund_stats_export['年率リターン'] * 100).round(2)
        fund_stats_export['年率ボラ']     = (fund_stats_export['年率ボラ']     * 100).round(2)
        fund_stats_export['最大DD']       = (fund_stats_export['最大DD']       * 100).round(2)
        # UIラベルに合わせて列名を変更
        fund_stats_export = fund_stats_export.rename(columns={
            '年率リターン': '年平均リターン(%)',
            '年率ボラ':     '年率価格変動リスク(%)',
            '最大DD':       '最大DD(%)',
        })
        fund_stats_export.to_excel(writer, sheet_name='ファンド統計')

    output.seek(0)

    st.download_button(
        label="📥 Excelファイルをダウンロード",
        data=output,
        file_name=f"portfolio_analysis_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
