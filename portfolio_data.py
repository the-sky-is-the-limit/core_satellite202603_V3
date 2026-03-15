"""
portfolio_data.py  v1.0.0
==========================
データ読込・概観テーブル計算・表示整形モジュール。
portfolio_app.py から import して使用する。

新規作成経緯（ステージ2リファクタ 2026-03）:
  portfolio_app.py の if uploaded_file ブロック内に定義されていた
  データ層の関数群を本ファイルに切り出した。
  対象：load_fund_data / compute_fund_overview_table /
        build_overview_cache_key /
        prep_overview_df / make_overview_col_config / style_overview_table

責務：
  - Excel ファイルの読み込みとキャッシュ管理
  - 全ファンド概観テーブルの計算（マルチピリオド・リスク・相関）
  - 概観テーブルの表示整形（列設定・スタイリング）

UI ロジック（st.tabs / st.dataframe の呼び出し）は app.py 側に残す。
本ファイルは「何を計算・整形するか」だけを担い、
「どこに・いつ表示するか」には関与しない。
"""

import hashlib

import numpy as np
import pandas as pd
import streamlit as st


# ─────────────────────────────────────────────────────────────
# データ読み込み
# ─────────────────────────────────────────────────────────────

@st.cache_data
def load_fund_data(file, file_id: str) -> pd.DataFrame:  # noqa: ARG001（file_id はキャッシュキー専用）
    """Excel ファイルを読み込み、Date インデックスの DataFrame を返す。

    Parameters
    ----------
    file     : UploadedFile
        Streamlit の file_uploader が返すオブジェクト。
    file_id  : str
        ファイル名・サイズ・先頭ハッシュを結合した一意識別子。
        UploadedFile 単体ではキャッシュが無効化されない場合があるため、
        明示的なキャッシュキー引数として渡す（D-03 修正）。

    Notes
    -----
    UploadedFile オブジェクト単体ではハッシュが変わらない場合があるため、
    ファイル名+サイズを文字列化した file_id でキャッシュを確実に無効化する。
    """
    df = pd.read_excel(file)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").sort_index()
    return df


# ─────────────────────────────────────────────────────────────
# 概観テーブル計算
# ─────────────────────────────────────────────────────────────

def build_overview_cache_key(
    df_price: pd.DataFrame,
    months_param: int,
    rf_rate_annual: float,
) -> str:
    """compute_fund_overview_table に渡すキャッシュキーを生成する。

    先頭日・末尾日・分析月数・無リスク金利・全列名を結合した文字列の
    MD5 ハッシュ（先頭12文字）を返す。

    先頭日を含めることで、古いファンド削除など
    データ先頭の変化も確実に検知できる（⑦ 修正）。
    """
    key_src = (
        f"{df_price.index[0].strftime('%Y%m')}_{df_price.index[-1].strftime('%Y%m')}"
        f"_{months_param}"
        f"_{rf_rate_annual:.4f}"
        f"_{','.join(sorted(df_price.columns))}"
    )
    return hashlib.md5(key_src.encode()).hexdigest()[:12]


@st.cache_data(show_spinner=False)
def compute_fund_overview_table(
    cache_key: str,
    _df_price: pd.DataFrame,
    fund_cols_tuple: tuple,
    core_fund: str,
    analysis_months: int,
    rf_rate: float = 0.005,
) -> pd.DataFrame:
    """全ファンドの多期間リターン・リスク・相関サマリーテーブルを計算。

    ・マルチピリオドリターン : 1年/3年/5年/10年/設定来（年率 CAGR）
    ・リスク指標             : 設定来ボラティリティ、最大 DD、シャープレシオ、月次勝率
    ・コア相関               : 設定来相関、選択分析期間の相関、ローリング相関安定性

    Parameters
    ----------
    cache_key      : str
        df_price の内容変化を検知するためのハッシュ文字列。
        build_overview_cache_key() で生成する。
    _df_price      : pd.DataFrame
        基準価格 DataFrame（全期間）。先頭アンダースコアは
        Streamlit のキャッシュ対象外引数を示す慣例。
    fund_cols_tuple : tuple
        対象ファンド列名のタプル。
    core_fund      : str
        コアファンド名（相関計算の基準）。
    analysis_months : int
        選択中の分析期間（月数）。
    rf_rate        : float
        年率無リスク金利（シャープレシオ計算用）。デフォルト 0.5%。

    Notes
    -----
    - 最大 DD：先頭に 1.0 を付加して期初損失を正確に捕捉
      （PortfolioAnalyzer._calculate_statistics と統一）
    - ローリング相関安定性：min_periods=12 を明示して
      不完全ウィンドウによるゼロ混入を防ぐ
    """
    fund_cols = list(fund_cols_tuple)

    # コアファンドの全期間リターン系列
    core_px_full  = _df_price[core_fund].dropna()
    core_ret_full = core_px_full.pct_change().dropna()

    # コアファンドの分析期間リターン系列
    # pct_change() で 1 本消費されるため、必要月次リターン数+1 本の価格データを取得する
    core_px_period  = _df_price[core_fund].iloc[-(analysis_months + 1):].dropna()
    core_ret_period = core_px_period.pct_change().dropna()

    def cagr(ret_series: pd.Series, months: int):
        """指定月数の年率 CAGR。データ不足は None を返す。"""
        if len(ret_series) < months:
            return None
        r   = ret_series.iloc[-months:]
        cum = (1 + r).prod() - 1
        return (1 + cum) ** (12.0 / months) - 1

    rows = []
    for fund in fund_cols:
        prices = _df_price[fund].dropna()
        if len(prices) < 13:   # 最低1年分（12ヶ月リターン + 1ヶ月）
            continue

        ret        = prices.pct_change().dropna()
        n          = len(ret)
        data_years = round(n / 12.0, 1)

        # ── マルチピリオドリターン ──────────────────────────────
        r1y  = cagr(ret, 12)
        r3y  = cagr(ret, 36)
        r5y  = cagr(ret, 60)
        r10y = cagr(ret, 120)
        r_all = cagr(ret, n)        # 設定来

        # ── 設定来リスク指標 ────────────────────────────────────
        vol    = ret.std(ddof=1) * np.sqrt(12)
        # 無リスク金利を控除したシャープレシオ（rf_rate=0.0 のときは従来と同値）
        sharpe = ((r_all - rf_rate) / vol) if (r_all is not None and vol > 1e-6) else None

        # 最大 DD：先頭に 1.0 を付加して期初損失を正確に捕捉
        # （_calculate_statistics と統一。旧実装 cum_ret.cummax() は
        #   第1期の損失を DD=0 と誤計上する可能性があった）
        cum_np  = np.concatenate([[1.0], (1 + ret.values).cumprod()])
        rmax_np = np.maximum.accumulate(cum_np)
        dd_np   = (cum_np - rmax_np) / rmax_np
        max_dd  = float(dd_np[1:].min())

        win_rate = (ret > 0).sum() / n     # 月次勝率

        # ── コアファンドとの相関 ────────────────────────────────
        # 設定来相関
        idx_full   = ret.index.intersection(core_ret_full.index)
        corr_full  = (
            ret[idx_full].corr(core_ret_full[idx_full])
            if len(idx_full) >= 12 else None
        )

        # 分析期間相関
        idx_period   = ret.index.intersection(core_ret_period.index)
        corr_period  = (
            ret[idx_period].corr(core_ret_period[idx_period])
            if len(idx_period) >= 6 else None
        )

        # 相関安定性：12ヶ月ローリング相関の標準偏差
        # σ が小さいほど相関が安定（分散効果が予測しやすい）
        # min_periods=12 を明示して、不完全ウィンドウによるゼロ混入を防ぐ
        if len(idx_full) >= 24:
            rolling_c = (
                ret[idx_full]
                .rolling(12, min_periods=12)
                .corr(core_ret_full[idx_full])
            )
            corr_stability = (
                rolling_c.dropna().std(ddof=1)
                if rolling_c.dropna().shape[0] >= 2 else None
            )
        else:
            corr_stability = None

        rows.append({
            "ファンド名"                        : fund,
            "データ期間(年)"                    : data_years,
            "1年リターン"                       : r1y,
            "3年リターン(年率)"                 : r3y,
            "5年リターン(年率)"                 : r5y,
            "10年リターン(年率)"                : r10y,
            "設定来リターン(年率)"               : r_all,
            "設定来ボラ"                         : vol,
            "シャープ(設定来)"                   : sharpe,
            "最大DD(設定来)"                    : max_dd,
            "月次勝率"                           : win_rate,
            "コア相関(設定来)"                   : corr_full,
            f"コア相関({analysis_months // 12}年)": corr_period,
            "相関安定性(σ)"                      : corr_stability,
        })

    return pd.DataFrame(rows).set_index("ファンド名")


# ─────────────────────────────────────────────────────────────
# 概観テーブル表示整形
# ─────────────────────────────────────────────────────────────

def make_overview_col_config(columns) -> dict:
    """float の overview DataFrame 用 column_config を生成する。

    - pct 列は ×100 済みの値を ``"%.1f%%"`` でフォーマット（ソート可能）
    - 符号付き列（リターン/最大 DD）は ``"%+.1f%%"`` でフォーマット
    - 相関・シャープ・期間は ``"%.2f"`` / ``"%.1f"``

    Notes
    -----
    旧名 ``_make_overview_col_config``（モジュール移動に伴いアンダースコア除去）
    """
    pct_signed_label = {
        "1年リターン":          "1年 リターン(%)",
        "3年リターン(年率)":    "3年 リターン(%)",
        "5年リターン(年率)":    "5年 リターン(%)",
        "10年リターン(年率)":   "10年 リターン(%)",
        "設定来リターン(年率)":  "設定来 リターン(%)",
        "最大DD(設定来)":        "最大DD 設定来(%)",
    }
    pct_unsigned_label = {
        "設定来ボラ": "設定来 ボラ(%)",
        "月次勝率":   "月次 勝率(%)",
    }
    cfg = {}
    for col in columns:
        if col in pct_signed_label:
            cfg[col] = st.column_config.NumberColumn(
                pct_signed_label[col], format="%+.1f%%")
        elif col in pct_unsigned_label:
            cfg[col] = st.column_config.NumberColumn(
                pct_unsigned_label[col], format="%.1f%%")
        elif col == "シャープ(設定来)":
            cfg[col] = st.column_config.NumberColumn(
                "シャープ(設定来)", format="%.2f")
        elif col == "データ期間(年)":
            cfg[col] = st.column_config.NumberColumn(
                "期間(年)", format="%.1f")
        elif "コア相関" in col or "相関安定性" in col:
            cfg[col] = st.column_config.NumberColumn(col, format="%.2f")
    return cfg


def prep_overview_df(df_raw: pd.DataFrame) -> pd.DataFrame:
    """overview_raw（小数）から表示・ソート用 DataFrame を作成する。

    % 列を ×100 した float のまま返す（文字列変換なし）。
    → st.dataframe の列ソートが正しく機能する。

    Notes
    -----
    旧名 ``_prep_overview_df``（モジュール移動に伴いアンダースコア除去）
    """
    pct_cols = [
        "1年リターン", "3年リターン(年率)", "5年リターン(年率)",
        "10年リターン(年率)", "設定来リターン(年率)",
        "設定来ボラ", "最大DD(設定来)", "月次勝率",
    ]
    df = df_raw.copy()
    for col in pct_cols:
        if col in df.columns:
            df[col] = df[col] * 100   # float のまま ×100（ソート有効）
    return df


def style_overview_table(
    df_raw: pd.DataFrame,
    core_fund: str,
    selected_funds: list = None,
) -> "pd.io.formats.style.Styler":
    """選定ファンド詳細統計など小テーブル向け：Styler で行ハイライトのみ適用。

    大テーブルは prep_overview_df + make_overview_col_config を使用。

    Parameters
    ----------
    df_raw         : pd.DataFrame
        overview_raw（小数スケール）の部分切り出し。
    core_fund      : str
        コアファンド名（青ハイライト対象）。
    selected_funds : list, optional
        選定ファンド名リスト（黄ハイライト対象）。
    """
    df_disp = prep_overview_df(df_raw)

    pct_signed_cols   = [
        "1年リターン", "3年リターン(年率)", "5年リターン(年率)",
        "10年リターン(年率)", "設定来リターン(年率)", "最大DD(設定来)",
    ]
    pct_unsigned_cols = ["設定来ボラ", "月次勝率"]
    fmt = {}
    for col in pct_signed_cols:
        if col in df_disp.columns:
            fmt[col] = lambda x: f"{x:+.1f}%" if pd.notna(x) else "—"
    for col in pct_unsigned_cols:
        if col in df_disp.columns:
            fmt[col] = lambda x: f"{x:.1f}%" if pd.notna(x) else "—"
    for col in ["シャープ(設定来)", "データ期間(年)"]:
        if col in df_disp.columns:
            fmt[col] = lambda x: f"{x:.2f}" if pd.notna(x) else "—"
    corr_cols = [c for c in df_disp.columns if "コア相関" in c or "相関安定性" in c]
    for col in corr_cols:
        fmt[col] = lambda x: f"{x:.2f}" if pd.notna(x) else "—"

    def row_style(row):
        name = row.name
        if name == core_fund:
            return ["background-color: #dbeafe; font-weight: bold"] * len(row)
        if selected_funds and name in selected_funds and name != core_fund:
            return ["background-color: #fef9c3"] * len(row)
        return [""] * len(row)

    styled = df_disp.style.apply(row_style, axis=1)
    if fmt:
        styled = styled.format(fmt, na_rep="—")
    styled = styled.set_properties(**{"text-align": "right"})
    styled = styled.set_table_styles([
        {"selector": "th.col_heading", "props": "text-align: center; font-size: 0.82em;"},
        {"selector": "th.row_heading", "props": "text-align: left; font-size: 0.82em;"},
        {"selector": "td",             "props": "font-size: 0.82em; padding: 3px 8px;"},
    ])
    return styled
