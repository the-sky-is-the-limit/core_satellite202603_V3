"""
射影関数・制約保証・全プロファイル E2E テスト

v2.0.1 推奨事項のフォローアップとして、Phase 7 レビューで特定された
テストカバレッジのギャップを埋める。

テスト5: 射影関数 _project_to_feasible_simplex の境界値テスト
テスト6: _cvxpy_clip_and_normalize の境界値テスト
テスト7: 全7プロファイル E2E 制約充足テスト
テスト8: 効率的フロンティア計算テスト
テスト9: calculate_portfolio_stats の CAGR ガード（FIX-Ph1-REVIEW 回帰テスト）
テスト10: screen_funds 負クォータガード（FIX-Ph2-REVIEW 回帰テスト）

実行方法:
  python test_constraints.py               # 実データあり
  TEST_DATA_FILE=other.xlsx python test_constraints.py
"""
import os
import sys
import warnings

import numpy as np
import pandas as pd

from portfolio_utils import FundScreener, PortfolioAnalyzer
from portfolio_data import CURRENCY_KEYWORDS

_DEFAULT_DATA_FILE = 'frends202512.xlsx'
DATA_FILE = os.environ.get('TEST_DATA_FILE', _DEFAULT_DATA_FILE)

# ── ヘルパー ──────────────────────────────────────────────────
_TOL_SUM  = 1e-6   # sum=1 の許容誤差
_TOL_BOUND = 1e-6  # bounds 内の許容誤差


def _make_analyzer(n_funds=10, n_months=36, seed=42):
    """テスト用の PortfolioAnalyzer を合成データで生成。"""
    rng = np.random.default_rng(seed)
    returns = pd.DataFrame(
        rng.normal(0.005, 0.03, (n_months, n_funds)),
        columns=[f'Fund{i}' for i in range(n_funds)],
    )
    return PortfolioAnalyzer(returns, risk_free_rate=0.005)


def _check_constraints(
    w, active, core_idx, core_range, min_ind, max_ind, label=""
):
    """ウェイトが全制約を満たすか検証し、違反があれば AssertionError を送出。"""
    core_lo, core_hi = core_range
    n = len(w)
    errors = []

    # sum=1
    if abs(w.sum() - 1.0) > _TOL_SUM:
        errors.append(f"sum={w.sum():.10f} (delta={w.sum()-1.0:.2e})")

    # 非負
    if (w < -_TOL_BOUND).any():
        errors.append(f"negative weights: min={w.min():.8f}")

    # コア bounds
    if w[core_idx] < core_lo - _TOL_BOUND:
        errors.append(f"core={w[core_idx]:.6f} < core_lo={core_lo}")
    if w[core_idx] > core_hi + _TOL_BOUND:
        errors.append(f"core={w[core_idx]:.6f} > core_hi={core_hi}")

    # 非コア active bounds
    for i in range(n):
        if i == core_idx:
            continue
        if active[i]:
            if w[i] < min_ind - _TOL_BOUND:
                errors.append(f"w[{i}]={w[i]:.6f} < min_ind={min_ind}")
            if w[i] > max_ind + _TOL_BOUND:
                errors.append(f"w[{i}]={w[i]:.6f} > max_ind={max_ind}")
        else:
            if abs(w[i]) > _TOL_BOUND:
                errors.append(f"inactive w[{i}]={w[i]:.6f} != 0")

    if errors:
        raise AssertionError(f"[{label}] 制約違反: " + "; ".join(errors))


# ── テスト5: 射影関数の境界値テスト ───────────────────────────
def test_projection_boundary():
    """_project_to_feasible_simplex のエッジケースを網羅的に検証。"""
    print("\n" + "=" * 60)
    print("テスト5: 射影関数 _project_to_feasible_simplex 境界値テスト")
    print("=" * 60)

    analyzer = _make_analyzer(n_funds=10)
    n = 10
    core_idx = 0
    core_range = (0.50, 0.65)
    min_ind = 0.03
    max_ind = 0.20
    all_active = np.ones(n, dtype=bool)
    all_ok = True

    # ── ケース1: 全ファンドが下限に張り付き（delta > 0）──────────
    print("\n[5-1] 全ファンドが下限に張り付き")
    try:
        w_low = np.full(n, min_ind)
        w_low[core_idx] = core_range[0]
        result = analyzer._project_to_feasible_simplex(
            w_low, all_active, core_idx, core_range, min_ind, max_ind
        )
        _check_constraints(result, all_active, core_idx, core_range, min_ind, max_ind, "5-1")
        print(f"  ✓ sum={result.sum():.8f}, core={result[core_idx]:.4f}")
    except Exception as e:
        print(f"  ✗ {e}")
        all_ok = False

    # ── ケース2: 全ファンドが上限に張り付き（delta < 0）──────────
    print("\n[5-2] 全ファンドが上限に張り付き")
    try:
        w_high = np.full(n, max_ind)
        w_high[core_idx] = core_range[1]
        result = analyzer._project_to_feasible_simplex(
            w_high, all_active, core_idx, core_range, min_ind, max_ind
        )
        _check_constraints(result, all_active, core_idx, core_range, min_ind, max_ind, "5-2")
        print(f"  ✓ sum={result.sum():.8f}, core={result[core_idx]:.4f}")
    except Exception as e:
        print(f"  ✗ {e}")
        all_ok = False

    # ── ケース3: コアでのみ調整可能（非コアが全て上限 or 下限）──
    print("\n[5-3] 非コアが全て上限に張り付き → コアで調整")
    try:
        w_nc_max = np.full(n, max_ind)
        # コアが調整余地を持つ値
        w_nc_max[core_idx] = 1.0 - (n - 1) * max_ind
        result = analyzer._project_to_feasible_simplex(
            w_nc_max, all_active, core_idx, core_range, min_ind, max_ind
        )
        _check_constraints(result, all_active, core_idx, core_range, min_ind, max_ind, "5-3")
        print(f"  ✓ sum={result.sum():.8f}, core={result[core_idx]:.4f}")
    except Exception as e:
        print(f"  ✗ {e}")
        all_ok = False

    # ── ケース4: 可行性限界（core_min + (n-1)*min_ind ≈ 1.0）──
    print("\n[5-4] 可行性限界ケース")
    try:
        # n=10, core_min=0.50 → min_ind = (1.0-0.50)/9 ≈ 0.0556
        _limit_min = (1.0 - core_range[0]) / (n - 1)
        w_limit = np.full(n, _limit_min)
        w_limit[core_idx] = core_range[0]
        result = analyzer._project_to_feasible_simplex(
            w_limit, all_active, core_idx, core_range, _limit_min, max_ind
        )
        _check_constraints(result, all_active, core_idx, core_range, _limit_min, max_ind, "5-4")
        print(f"  ✓ sum={result.sum():.8f}, core={result[core_idx]:.4f}")
    except Exception as e:
        print(f"  ✗ {e}")
        all_ok = False

    # ── ケース5: 非アクティブ銘柄が含まれる場合 ──────────────
    print("\n[5-5] 一部非アクティブ（5本のみアクティブ）")
    try:
        partial_active = np.array([True]*5 + [False]*5)
        w_partial = np.full(n, 0.10)
        w_partial[core_idx] = 0.55
        result = analyzer._project_to_feasible_simplex(
            w_partial, partial_active, core_idx, core_range, min_ind, max_ind
        )
        _check_constraints(result, partial_active, core_idx, core_range, min_ind, max_ind, "5-5")
        # 非アクティブはゼロ
        assert all(abs(result[i]) < _TOL_BOUND for i in range(5, 10)), "非アクティブがゼロでない"
        print(f"  ✓ sum={result.sum():.8f}, inactive=all zero")
    except Exception as e:
        print(f"  ✗ {e}")
        all_ok = False

    # ── ケース6: scale→clip→第2段階delta配分が発動するケース ────
    print("\n[5-6] scale→clip後の第2段階delta配分")
    try:
        # 合計が大きくずれたウェイトを投入
        w_skewed = np.full(n, 0.25)       # 合計=2.5（大幅超過）
        w_skewed[core_idx] = 0.55
        result = analyzer._project_to_feasible_simplex(
            w_skewed, all_active, core_idx, core_range, min_ind, max_ind
        )
        _check_constraints(result, all_active, core_idx, core_range, min_ind, max_ind, "5-6")
        print(f"  ✓ sum={result.sum():.8f}, core={result[core_idx]:.4f}")
    except Exception as e:
        print(f"  ✗ {e}")
        all_ok = False

    # ── ケース7: 負のウェイトが入力される場合 ──────────────────
    print("\n[5-7] 負のウェイト入力")
    try:
        w_neg = np.array([-0.5, 0.8, 0.3, 0.2, 0.1, 0.05, 0.02, 0.01, 0.01, 0.01])
        result = analyzer._project_to_feasible_simplex(
            w_neg, all_active, core_idx, core_range, min_ind, max_ind
        )
        _check_constraints(result, all_active, core_idx, core_range, min_ind, max_ind, "5-7")
        print(f"  ✓ sum={result.sum():.8f}, min={result.min():.6f}")
    except Exception as e:
        print(f"  ✗ {e}")
        all_ok = False

    # ── ケース8: アクティブが2本のみ（最小構成）──────────────
    # 可行性条件: core_max + max_individual >= 1.0 かつ core_min + min_individual <= 1.0
    # 2本構成ではサテライトが 1-core を全て担うため、max_individual を十分に大きくする。
    print("\n[5-8] 最小構成（アクティブ2本: コア+サテライト1本）")
    try:
        minimal_active = np.zeros(n, dtype=bool)
        minimal_active[0] = True   # コア
        minimal_active[1] = True   # サテライト1本
        w_min = np.array([0.60, 0.40] + [0.0]*8)
        _min_8 = 0.03
        _max_8 = 0.60  # サテライト1本に十分な上限
        result = analyzer._project_to_feasible_simplex(
            w_min, minimal_active, core_idx, core_range, _min_8, _max_8
        )
        _check_constraints(result, minimal_active, core_idx, core_range, _min_8, _max_8, "5-8")
        # 非アクティブはゼロ
        assert all(abs(result[i]) < _TOL_BOUND for i in range(2, 10)), "非アクティブがゼロでない"
        print(f"  ✓ sum={result.sum():.8f}, core={result[0]:.4f}, sat={result[1]:.4f}")
    except Exception as e:
        print(f"  ✗ {e}")
        all_ok = False

    if all_ok:
        print("\n✓ テスト5: 全8ケース合格")
    else:
        print("\n✗ テスト5: 一部ケース失敗")
    return all_ok


# ── テスト6: _cvxpy_clip_and_normalize 境界値テスト ───────────
def test_cvxpy_clip_boundary():
    """CVXPY出力のクリップ・正規化が全制約を保証するか検証。"""
    print("\n" + "=" * 60)
    print("テスト6: _cvxpy_clip_and_normalize 境界値テスト")
    print("=" * 60)

    analyzer = _make_analyzer(n_funds=10)
    n = 10
    core_idx = 0
    core_range = (0.50, 0.65)
    min_ind = 0.03
    max_ind = 0.20
    active = np.ones(n, dtype=bool)
    all_ok = True

    # ── ケース1: コアがbounds端に張り付き（deltaをコアで吸収不可）──
    print("\n[6-1] コアがbounds上端に張り付き")
    try:
        w_raw = np.full(n, 0.04)
        w_raw[core_idx] = 0.66  # 微小にbounds超過
        result = analyzer._cvxpy_clip_and_normalize(
            w_raw, active, core_idx, core_range, min_ind, max_ind
        )
        _check_constraints(result, active, core_idx, core_range, min_ind, max_ind, "6-1")
        print(f"  ✓ sum={result.sum():.8f}, core={result[core_idx]:.4f}")
    except Exception as e:
        print(f"  ✗ {e}")
        all_ok = False

    # ── ケース2: CLARABEL精度誤差の模擬（bounds微小逸脱）───────
    print("\n[6-2] CLARABEL精度誤差の模擬")
    try:
        w_raw = np.array([0.55, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05])
        w_raw[1] += 1e-8   # 微小逸脱
        w_raw[2] -= 1e-8
        result = analyzer._cvxpy_clip_and_normalize(
            w_raw, active, core_idx, core_range, min_ind, max_ind
        )
        _check_constraints(result, active, core_idx, core_range, min_ind, max_ind, "6-2")
        print(f"  ✓ sum={result.sum():.8f}")
    except Exception as e:
        print(f"  ✗ {e}")
        all_ok = False

    # ── ケース3: 非アクティブ銘柄に非ゼロ値 ──────────────────
    print("\n[6-3] 非アクティブ銘柄に非ゼロ値")
    try:
        partial_active = np.array([True]*6 + [False]*4)
        w_raw = np.array([0.55, 0.09, 0.09, 0.09, 0.09, 0.09, 0.01, 0.01, 0.0, 0.0])
        result = analyzer._cvxpy_clip_and_normalize(
            w_raw, partial_active, core_idx, core_range, min_ind, max_ind
        )
        _check_constraints(result, partial_active, core_idx, core_range, min_ind, max_ind, "6-3")
        print(f"  ✓ sum={result.sum():.8f}, inactive max={max(abs(result[6:])):.2e}")
    except Exception as e:
        print(f"  ✗ {e}")
        all_ok = False

    if all_ok:
        print("\n✓ テスト6: 全3ケース合格")
    else:
        print("\n✗ テスト6: 一部ケース失敗")
    return all_ok


# ── テスト7: 全7プロファイル E2E 制約充足テスト ─────────────────
def test_all_profiles_e2e():
    """実データで全7プロファイルを最適化し、制約充足を検証。"""
    print("\n" + "=" * 60)
    print("テスト7: 全7プロファイル E2E 制約充足テスト")
    print("=" * 60)

    if not os.path.exists(DATA_FILE):
        print(f"⚠ スキップ: データファイルが見つかりません ({DATA_FILE})")
        return True

    # データ準備（test_app.py と同一フロー）
    df = pd.read_excel(DATA_FILE)
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.set_index('Date').sort_index()
    df_3y = df.iloc[-37:]
    fund_cols = [c for c in df_3y.columns if not any(kw in c for kw in CURRENCY_KEYWORDS)]
    _df_pct = df_3y[fund_cols].pct_change(fill_method=None).iloc[1:]
    missing = _df_pct.isnull().sum() / len(_df_pct)
    valid = missing[missing == 0].index.tolist()
    returns = df_3y[valid].pct_change(fill_method=None).dropna()

    screener = FundScreener(returns, risk_free_rate=0.005)
    non_cash = screener.statistics[~screener.statistics['is_cash_fund']]
    core_fund = non_cash['シャープレシオ'].idxmax()
    selected = screener.screen_funds(core_fund, n_final=20)
    returns_sel = returns[selected]

    analyzer = PortfolioAnalyzer(returns_sel, risk_free_rate=0.005)
    core_idx = selected.index(core_fund)

    # 全プロファイル設定
    profiles = {
        "積極型":       {"core_range": (0.20, 0.35), "obj": "max_cagr",      "max": 0.30, "min": 0.03},
        "やや積極型":   {"core_range": (0.35, 0.50), "obj": "sharpe",        "max": 0.25, "min": 0.03},
        "バランス型":   {"core_range": (0.50, 0.65), "obj": "sharpe",        "max": 0.20, "min": 0.03},
        "やや保守型":   {"core_range": (0.65, 0.80), "obj": "risk_adjusted", "max": 0.15, "min": 0.03},
        "保守型":       {"core_range": (0.80, 0.95), "obj": "volatility",    "max": 0.10, "min": 0.02},
        "テールリスク": {"core_range": (0.70, 0.85), "obj": "min_cvar",      "max": 0.12, "min": 0.02},
        "リスクパリティ": {"core_range": (0.50, 0.65), "obj": "risk_parity", "max": 0.20, "min": 0.03},
    }

    n_sat = len(selected) - 1
    all_ok = True

    for pname, cfg in profiles.items():
        # 可行性チェック & min_individual 自動調整（本番ロジックと同一）
        _min = cfg["min"]
        if cfg["core_range"][0] + n_sat * _min > 1.0 + 1e-6:
            _min = max(0.0, (1.0 - cfg["core_range"][0]) / max(n_sat, 1) - 1e-6)

        try:
            w = analyzer.optimize_portfolio(
                core_idx,
                cfg["core_range"],
                cfg["obj"],
                cfg["max"],
                min_individual=_min,
            )
            stats = analyzer.calculate_portfolio_stats(w)

            # 制約検証
            assert abs(w.sum() - 1.0) < 1e-4, f"sum={w.sum():.8f}"
            assert all(w >= -1e-6), f"min_w={w.min():.8f}"
            core_w = w[core_idx]
            lo, hi = cfg["core_range"]
            assert lo - 1e-4 <= core_w <= hi + 1e-4, f"core={core_w:.4f}"
            assert np.isfinite(stats['年率リターン']), "CAGR is not finite"
            assert np.isfinite(stats['シャープレシオ']), "Sharpe is not finite"

            print(f"  ✓ {pname:12s} | ret={stats['年率リターン']*100:+6.2f}% "
                  f"SR={stats['シャープレシオ']:.3f} core={core_w*100:.1f}% sum={w.sum():.6f}")
        except Exception as e:
            print(f"  ✗ {pname:12s} | {e}")
            all_ok = False

    if all_ok:
        print("\n✓ テスト7: 全7プロファイル合格")
    else:
        print("\n✗ テスト7: 一部プロファイル失敗")
    return all_ok


# ── テスト8: 効率的フロンティア計算テスト ───────────────────────
def test_efficient_frontier():
    """効率的フロンティアの計算結果が数学的に妥当か検証。"""
    print("\n" + "=" * 60)
    print("テスト8: 効率的フロンティア計算テスト")
    print("=" * 60)

    analyzer = _make_analyzer(n_funds=10, n_months=60)
    all_ok = True

    try:
        ef = analyzer.calculate_efficient_frontier(n_points=20)

        # 基本検証
        assert len(ef) >= 2, f"フロンティア点数が不足: {len(ef)}"
        assert 'リターン' in ef.columns
        assert 'リターン_CAGR' in ef.columns
        assert 'ボラティリティ' in ef.columns

        # ボラティリティは非負
        assert (ef['ボラティリティ'] >= 0).all(), "負のボラティリティが存在"

        # ボラティリティ昇順ソート済み
        vols = ef['ボラティリティ'].values
        assert all(vols[i] <= vols[i+1] + 1e-8 for i in range(len(vols)-1)), "ボラ昇順でない"

        # リターン（算術平均）は単調非減少（上方フロンティア）
        rets = ef['リターン'].values
        assert all(rets[i] <= rets[i+1] + 1e-6 for i in range(len(rets)-1)), "リターン単調でない"

        # CAGR列にNaN以外の有限値が含まれる
        cagr_finite = ef['リターン_CAGR'].dropna()
        assert len(cagr_finite) > 0, "CAGR列が全てNaN"
        assert np.isfinite(cagr_finite.values).all(), "CAGR列に無限大"

        print(f"  ✓ {len(ef)}点のフロンティアを生成")
        print(f"    vol範囲: {vols[0]*100:.2f}% - {vols[-1]*100:.2f}%")
        print(f"    ret範囲: {rets[0]*100:.2f}% - {rets[-1]*100:.2f}%")
    except Exception as e:
        print(f"  ✗ {e}")
        all_ok = False

    if all_ok:
        print("\n✓ テスト8: 合格")
    else:
        print("\n✗ テスト8: 失敗")
    return all_ok


# ── テスト9: CAGR ガード回帰テスト（FIX-Ph1-REVIEW）──────────
def test_cagr_guard():
    """累積損失100%超の異常データで CAGR が 0.0 を返すことを確認。"""
    print("\n" + "=" * 60)
    print("テスト9: CAGR ガード回帰テスト (FIX-Ph1-REVIEW)")
    print("=" * 60)

    n_funds, n_months = 5, 36
    all_ok = True

    # ケース1: 正常データ
    print("\n[9-1] 正常データ")
    try:
        normal = pd.DataFrame(
            np.random.default_rng(42).normal(0.005, 0.03, (n_months, n_funds)),
            columns=[f'F{i}' for i in range(n_funds)],
        )
        analyzer = PortfolioAnalyzer(normal)
        w = np.array([0.5, 0.2, 0.15, 0.1, 0.05])
        stats = analyzer.calculate_portfolio_stats(w)
        assert np.isfinite(stats['年率リターン']), "正常データのCAGRがfiniteでない"
        print(f"  ✓ CAGR={stats['年率リターン']*100:.2f}% (finite)")
    except Exception as e:
        print(f"  ✗ {e}")
        all_ok = False

    # ケース2: 累積損失100%超（base <= 0）
    print("\n[9-2] 累積損失100%超（base <= 0）")
    try:
        extreme = pd.DataFrame(
            np.full((n_months, n_funds), -0.50),
            columns=[f'F{i}' for i in range(n_funds)],
        )
        extreme.iloc[0] = -1.5  # 1ヶ月目に-150%（異常データ）
        analyzer = PortfolioAnalyzer(extreme)
        w = np.array([0.5, 0.2, 0.15, 0.1, 0.05])
        stats = analyzer.calculate_portfolio_stats(w)
        assert stats['年率リターン'] == 0.0, f"期待値0.0、実際={stats['年率リターン']}"
        print(f"  ✓ CAGR=0.0 (guard triggered)")
    except Exception as e:
        print(f"  ✗ {e}")
        all_ok = False

    # ケース3: 3パスの整合性
    print("\n[9-3] 3パス整合性（__init__ / _calculate_statistics / calculate_portfolio_stats）")
    try:
        extreme2 = pd.DataFrame(
            np.full((n_months, n_funds), -0.50),
            columns=[f'F{i}' for i in range(n_funds)],
        )
        extreme2.iloc[0] = -1.5

        # パス1: __init__（mean_returns_geom）
        analyzer = PortfolioAnalyzer(extreme2)
        geom_init = analyzer.mean_returns_geom.values

        # パス2: _calculate_statistics
        screener = FundScreener(extreme2)
        geom_screener = screener.statistics['年率リターン'].values

        # パス3: calculate_portfolio_stats
        w_equal = np.ones(n_funds) / n_funds
        stats = analyzer.calculate_portfolio_stats(w_equal)
        geom_stats = stats['年率リターン']

        # 全て 0.0 であること
        assert all(v == 0.0 for v in geom_init), f"__init__ path: {geom_init}"
        assert all(v == 0.0 for v in geom_screener), f"_calculate_statistics path: {geom_screener}"
        assert geom_stats == 0.0, f"calculate_portfolio_stats path: {geom_stats}"
        print(f"  ✓ 3パス全て 0.0 で整合")
    except Exception as e:
        print(f"  ✗ {e}")
        all_ok = False

    if all_ok:
        print("\n✓ テスト9: 全3ケース合格")
    else:
        print("\n✗ テスト9: 一部ケース失敗")
    return all_ok


# ── テスト10: 負クォータガード回帰テスト（FIX-Ph2-REVIEW）──────
def test_quota_guard():
    """小 n_final で負のクォータが発生しないことを確認。"""
    print("\n" + "=" * 60)
    print("テスト10: 負クォータガード回帰テスト (FIX-Ph2-REVIEW)")
    print("=" * 60)

    # 合成データでスクリーニング
    rng = np.random.default_rng(42)
    n_funds, n_months = 30, 36
    returns = pd.DataFrame(
        rng.normal(0.005, 0.04, (n_months, n_funds)),
        columns=[f'Fund{i}' for i in range(n_funds)],
    )
    all_ok = True

    for n_final in [5, 8, 10, 15, 20]:
        try:
            screener = FundScreener(returns, risk_free_rate=0.005)
            selected = screener.screen_funds('Fund0', n_final=n_final)
            report = screener.screening_report
            # 全バケットの selected が非負か
            for bname, bstat in report['buckets'].items():
                sel_count = bstat.get('selected', 0)
                assert sel_count >= 0, f"n_final={n_final}, bucket={bname}: selected={sel_count} < 0"
            print(f"  ✓ n_final={n_final:2d}: {len(selected)}本選定, バケット全て>=0")
        except Exception as e:
            print(f"  ✗ n_final={n_final}: {e}")
            all_ok = False

    if all_ok:
        print("\n✓ テスト10: 全ケース合格")
    else:
        print("\n✗ テスト10: 一部ケース失敗")
    return all_ok


# ── メイン ────────────────────────────────────────────────────
def main():
    print("\n" + "=" * 60)
    print("射影関数・制約保証・全プロファイル 拡張テスト")
    print("=" * 60)

    results = {}
    results['T5 射影関数境界値']      = test_projection_boundary()
    results['T6 CVXPYクリップ境界値'] = test_cvxpy_clip_boundary()
    results['T7 全プロファイルE2E']   = test_all_profiles_e2e()
    results['T8 効率的フロンティア']   = test_efficient_frontier()
    results['T9 CAGRガード回帰']      = test_cagr_guard()
    results['T10 クォータガード回帰'] = test_quota_guard()

    print("\n" + "=" * 60)
    print("拡張テスト結果サマリー")
    print("=" * 60)
    all_pass = True
    for name, passed in results.items():
        status = "✓" if passed else "✗"
        print(f"  {status} {name}")
        if not passed:
            all_pass = False

    print()
    if all_pass:
        print("総合結果: ✓ 全テスト合格")
    else:
        print("総合結果: ✗ 一部テスト失敗")

    return all_pass


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
