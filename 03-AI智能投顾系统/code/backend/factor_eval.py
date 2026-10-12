import numpy as np
import pandas as pd
from scipy.stats import spearmanr
import statsmodels.api as sm

# ============================================================
# 1. IC / Rank IC
# ============================================================
def calc_ic(df, factor_col, return_col='next_return', date_col='date'):
    """
    日频横截面 Rank IC
    每个交易日，当日因子值 vs 下一期收益 做 Spearman 相关
    """
    records = []
    for date, g in df.groupby(date_col):
        g = g[[factor_col, return_col]].dropna()
        if len(g) < 30:
            continue
        ic, _ = spearmanr(g[factor_col], g[return_col])
        records.append({'date': date, 'ic': ic, 'n': len(g)})

    ic_df = pd.DataFrame(records)
    ic_mean = ic_df['ic'].mean()
    ic_std = ic_df['ic'].std()
    ic_ir = ic_mean / ic_std if ic_std else 0
    win_rate = (ic_df['ic'] > 0).mean()

    print(f"[IC] mean={ic_mean:.4f}  std={ic_std:.4f}  IR={ic_ir:.4f}  win_rate={win_rate:.2%}")
    return ic_df


# ============================================================
# 2. 分层收益
# ============================================================
def stratified_return(df, factor_col, return_col='next_return',
                      date_col='date', n_groups=5):
    """
    每期按因子值等分 n_groups 组，算各组下期平均收益
    返回 (summary_df, long_short, monotonic)
    """
    results = []
    for date, g in df.groupby(date_col):
        g = g[[factor_col, return_col]].dropna().copy()
        if len(g) < n_groups * 5:
            continue
        try:
            g['group'] = pd.qcut(g[factor_col], n_groups, labels=False, duplicates='drop')
        except ValueError:
            continue
        for grp in range(n_groups):
            sub = g[g['group'] == grp]
            if len(sub) < 3:
                continue
            results.append({'date': date, 'group': grp, 'ret': sub[return_col].mean()})

    tbl = pd.DataFrame(results)
    summary = tbl.groupby('group')['ret'].mean().reset_index()

    long_short = summary['ret'].iloc[-1] - summary['ret'].iloc[0]
    monotonic = all(summary['ret'].diff().dropna() >= 0)

    print(f"[分层] 多空收益={long_short:.5f}  单调性={'通过' if monotonic else '不通过'}")
    print(summary.to_string(index=False))
    return summary, long_short, monotonic


# ============================================================
# 3. 正交化（中性化）
# ============================================================
def orthogonalize(df, factor_col, neutralize_cols):
    """
    factor_col 对 neutralize_cols 做 OLS，返回残差作为纯净因子
    例如 neutralize_cols = ['log_mcap', 'ind_bank', 'ind_tech', ...]
    """
    sub = df[[factor_col] + neutralize_cols].dropna()
    y = sub[factor_col].values
    X = sm.add_constant(sub[neutralize_cols].values)
    resid = sm.OLS(y, X).fit().resid

    result = pd.Series(np.nan, index=df.index)
    result.loc[sub.index] = resid
    return result


# ============================================================
# 4. 完整评估流程
# ============================================================
def evaluate_factor(df, factor_col, return_col='next_return', date_col='date',
                    neutralize_cols=None, n_groups=5):
    """
    一步跑完：IC → 分层 → (可选)正交化后再 IC + 分层
    """
    print(f"========== [{factor_col}] 原始因子 ==========")
    calc_ic(df, factor_col, return_col, date_col)
    stratified_return(df, factor_col, return_col, date_col, n_groups)

    if neutralize_cols:
        print(f"\n========== [{factor_col}] 正交化后 ==========")
        df = df.copy()
        df[f'{factor_col}_orth'] = orthogonalize(df, factor_col, neutralize_cols)
        calc_ic(df, f'{factor_col}_orth', return_col, date_col)
        stratified_return(df, f'{factor_col}_orth', return_col, date_col, n_groups)
        return df

    return df


# ============================================================
# Demo
# ============================================================
if __name__ == '__main__':
    n_dates = 250
    n_stocks = 200
    np.random.seed(42)

    rows = []
    for i in range(n_dates):
        date = pd.Timestamp('2025-01-02') + pd.Timedelta(days=i)
        for j in range(n_stocks):
            true_alpha = np.random.randn() * 0.02
            factor_val = true_alpha + np.random.randn() * 0.98
            next_ret = true_alpha * 0.8 + np.random.randn() * 0.02
            rows.append({
                'date': date,
                'stock': j,
                'factor_value': factor_val,
                'next_return': next_ret,
                'log_mcap': np.random.randn() * 2 + 10,
                'ind_a': np.random.choice([0, 1]),
                'ind_b': np.random.choice([0, 1]),
            })

    df = pd.DataFrame(rows)

    evaluate_factor(
        df,
        factor_col='factor_value',
        return_col='next_return',
        date_col='date',
        neutralize_cols=['log_mcap', 'ind_a', 'ind_b'],
        n_groups=5,
    )
