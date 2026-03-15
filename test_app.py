"""
ポートフォリオ最適化アプリのテストスクリプト
"""
import pandas as pd
import numpy as np
from portfolio_utils import PortfolioAnalyzer, FundScreener
import sys

def test_data_loading():
    """データ読み込みテスト"""
    print("=" * 60)
    print("テスト1: データ読み込み")
    print("=" * 60)
    
    try:
        df = pd.read_excel('frends202512.xlsx')
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.set_index('Date')
        
        print(f"✓ データ読み込み成功")
        print(f"  - データ期間: {df.index[0]} ～ {df.index[-1]}")
        print(f"  - データポイント数: {len(df)}")
        print(f"  - ファンド数: {len(df.columns)}")
        
        return df
    except Exception as e:
        print(f"✗ エラー: {e}")
        return None

def test_screening(df):
    """スクリーニングテスト"""
    print("\n" + "=" * 60)
    print("テスト2: ファンドスクリーニング")
    print("=" * 60)
    
    try:
        # 3年データに絞る
        df_3y = df.iloc[-36:]
        
        # ベンチマーク除外
        fund_cols = [col for col in df_3y.columns 
                    if any(col.startswith(p) for p in ['J', 'L', 'M', 'P', 'R', 'S'])]
        
        # 欠損チェック
        missing_rates = df_3y[fund_cols].isnull().sum() / len(df_3y)
        valid_funds = missing_rates[missing_rates < 0.2].index.tolist()
        
        print(f"✓ 有効ファンド数: {len(valid_funds)}")
        
        # リターン計算
        returns = df_3y[valid_funds].pct_change().dropna()
        
        # スクリーニング
        screener = FundScreener(returns)
        
        # コアファンドを仮選定（シャープレシオ上位）
        stats = screener.get_statistics()
        core_fund = stats['シャープレシオ'].idxmax()
        
        print(f"✓ コアファンド選定: {core_fund}")
        print(f"  - シャープレシオ: {stats.loc[core_fund, 'シャープレシオ']:.3f}")
        
        # スクリーニング実行
        selected_funds = screener.screen_funds(core_fund, n_final=20)
        
        print(f"✓ スクリーニング完了: {len(selected_funds)}本選定")
        
        return returns[selected_funds], core_fund, selected_funds
    
    except Exception as e:
        print(f"✗ エラー: {e}")
        import traceback
        traceback.print_exc()
        return None, None, None

def test_optimization(returns, core_fund, selected_funds):
    """最適化テスト"""
    print("\n" + "=" * 60)
    print("テスト3: ポートフォリオ最適化")
    print("=" * 60)
    
    try:
        analyzer = PortfolioAnalyzer(returns)
        core_idx = selected_funds.index(core_fund)
        
        # バランス型で最適化
        weights = analyzer.optimize_portfolio(
            core_idx,
            core_weight_range=(0.5, 0.6),
            objective_type='sharpe',
            max_individual=0.15
        )
        
        print(f"✓ 最適化成功")
        
        # 統計計算
        stats = analyzer.calculate_portfolio_stats(weights)
        
        print(f"\nポートフォリオ統計:")
        print(f"  - 年率リターン: {stats['年率リターン']*100:.2f}%")
        print(f"  - 年率ボラティリティ: {stats['年率ボラティリティ']*100:.2f}%")
        print(f"  - シャープレシオ: {stats['シャープレシオ']:.3f}")
        print(f"  - ソルティノレシオ: {stats['ソルティノレシオ']:.3f}")
        print(f"  - 最大ドローダウン: {stats['最大ドローダウン']*100:.2f}%")
        print(f"  - カルマー比率: {stats['カルマー比率']:.3f}")
        
        # 主要構成
        print(f"\n主要構成（上位5ファンド）:")
        weights_sorted = sorted(zip(selected_funds, weights), key=lambda x: x[1], reverse=True)
        for fund, w in weights_sorted[:5]:
            if w > 0.01:
                print(f"  - {fund[:40]}: {w*100:.1f}%")
        
        return True
    
    except Exception as e:
        print(f"✗ エラー: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """メインテスト実行"""
    print("\n" + "=" * 60)
    print("投資信託ポートフォリオ最適化アプリ - 動作確認テスト")
    print("=" * 60 + "\n")
    
    # テスト1: データ読み込み
    df = test_data_loading()
    if df is None:
        print("\n総合結果: ✗ 失敗")
        return False
    
    # テスト2: スクリーニング
    returns, core_fund, selected_funds = test_screening(df)
    if returns is None:
        print("\n総合結果: ✗ 失敗")
        return False
    
    # テスト3: 最適化
    success = test_optimization(returns, core_fund, selected_funds)
    
    # 総合結果
    print("\n" + "=" * 60)
    if success:
        print("総合結果: ✓ すべてのテストに合格")
        print("=" * 60)
        print("\nアプリは正常に動作します。")
        print("以下のコマンドで起動できます:")
        print("  ./run_app.sh")
        print("または")
        print("  streamlit run portfolio_optimizer_pro.py")
    else:
        print("総合結果: ✗ テストに失敗しました")
        print("=" * 60)
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
