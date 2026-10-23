# Glossary

Each technical term has one meaning in this repository. The ledger columns use these terms.

| Term | Meaning |
|---|---|
| 2x single-stock ETF | An exchange-traded fund that aims to return two times the daily return of one stock, before costs. |
| Daily reset | The fund sets its exposure back to the target leverage at each close. The next day starts again at 2x. |
| Total return | A return that includes cash payments. The engine reinvests a payment with ex-date t at the close of t. |
| Ex-date | The first session on which a buyer of the share does not receive the declared payment. |
| Distribution | A cash payment from a fund to its holders. |
| Layer | One of the reference series the engine builds from the stock: L0, L1, L2, B and L3. |
| L0 | The stock, on total return. |
| L1 | A frictionless fund that resets to the target leverage each day, with no costs. |
| L2 | L1 charged the fed funds rate on the borrowed part (one turn for a 2x fund). |
| B | Levered buy-and-hold: borrow once, buy 2x the stock, hold, pay fed funds, never rebalance. |
| L3 | The real fund, on total return. |
| Fed funds | The effective federal funds rate, the overnight rate between US banks (FRED series DFF). |
| Turn | One times the fund's own value. A 2x fund holds two turns of stock and borrows one turn. |
| Residual | The fund's return minus L2's return. A negative residual is a cost. |
| All-in cost | Minus the residual, as a yearly rate in log terms. The cost of the product beyond fed funds. It holds the expense ratio, the swap spread above fed funds, trading costs, missed targets and any change in the market premium between the first and last close. It equals Bessembinder's "frictional cost" with the sign reversed. |
| Compounding effect | L1's return minus two times the stock's return. The effect of the daily reset on multi-day returns. |
| Financing effect | L2's return minus L1's return. The cost of the borrowed turn at fed funds. |
| Rebalancing effect | L2's return minus B's return. What the daily reset adds or costs against a hold with the same borrowing. |
| Realized leverage | The slope of the fund's daily return on the stock's daily return (OLS). A 2x fund has a slope near 2. |
| Tracking error | The yearly standard deviation of the fund's daily return minus the target times the stock's return. |
| Capture ratio | The sum of fund returns divided by the sum of stock returns on days the stock rose (up) or fell (down). The ratio includes costs. |
| Realized volatility | The yearly standard deviation of daily returns, from closes. |
| Garman-Klass volatility | A volatility estimate that uses the open, high, low and close of each day. |
| Volatility drag | The compounding penalty of a 2x daily reset on a stock with volatility sigma: about sigma squared a year, in log terms. |
| Variance ratio | The variance of 10-day returns divided by 10 times the variance of daily returns. Above 1 means trend, below 1 means reversal. |
| Autocorrelation | The correlation of a day's return with the return of the day before (lag one). |
| Hurdle return | The yearly log return of the stock at which a 2x fund grows as fast as the stock, in log terms. |
| Kelly leverage | The leverage that maximizes the long-run growth rate of a position in the stock. |
| Tail index | The Hill estimate of how fast the left tail of daily returns thins. A lower value means more extreme losses. |
| Excess kurtosis | A measure of how fat the tails of daily returns are, relative to a normal distribution. |
| Drawdown | The fall from the highest value so far to the current value, in percent. |
| Underwater days | Calendar days since the fund's last peak. |
| Oracle return | The best entry-to-exit gain, or the worst entry-to-exit loss, inside a window. A bound no trader reaches. |
| Reverse split | The issuer merges shares, so the price per share rises and the share count falls. The value of a holding does not change. |
| Register | The tables of fund facts with sources: issuer, stock, inception, leverage and expense timelines, events. |
| Ranked | A fund with at least 126 sessions of history. Rankings use ranked funds only. |
| Cutoff | A time stamp. A run under a cutoff sees only raw files fetched before it. |
| Point in time | The rule that a run as of a past date uses only the data that existed then. |
| Manifest | A list of files with their SHA-256 hashes and fetch dates. |
| Window | A period with a start and an end session. Calendar years and trailing periods are windows. |
| Bootstrap | A method that draws blocks of daily returns many times to give an interval around an estimate. |
| Census | The full list of funds in the universe, with closed funds. The pilot is not a census. |
| Swap | A contract with a bank that gives the fund its exposure to the stock. The fund pays a rate above fed funds. |
| Spread | The rate the fund pays above fed funds for its exposure. |
| Expense ratio | The yearly fee the issuer states in the prospectus, in percent of assets. |
| AUM | Assets under management: the market value of the fund's assets. |
| Net flow | The cash that holders added to or withdrew from the fund over a period. |
| Pre-registered hypothesis | A claim with a test and a pass rule, put on record before the data that tests it exists. |
