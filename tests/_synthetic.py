"""Planted synthetic paths for the engine tests (no market data)."""
import numpy as np
import pandas as pd


def bdays(n, start="2020-01-02"):
    return pd.bdate_range(start, periods=n)


def gbm_prices(n, mu=0.10, sigma=0.30, seed=1, start="2020-01-02", s0=100.0, dt=1 / 252):
    """Lognormal daily prices with annual drift mu and volatility sigma; first price s0."""
    rng = np.random.default_rng(seed)
    z = rng.standard_normal(n - 1)
    log_r = (mu - 0.5 * sigma ** 2) * dt + sigma * np.sqrt(dt) * z
    px = s0 * np.exp(np.concatenate([[0.0], np.cumsum(log_r)]))
    return pd.Series(px, index=bdays(n, start), name="close")


def constant_rate(index, annual):
    return pd.Series(float(annual), index=index)
