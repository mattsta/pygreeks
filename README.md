pygreeks: black-scholes greeks in python
----------------------------------------

pygreeks implements black-scholes and IV discovery in python using either exact
derivatives from `pytorch` autograd or a fast numerical approximation.


pygreeks operates in one of two modes:

- you provide the strike, put/call, underlying, expiration then one of:
    - `iv`
    - `npv`

If you provide `npv` (usually the current option bid/ask midpoint is a safe bet if bids exist), then `iv` will be calculated for the strike at current expiration + iv + underlying.

If you provide `iv`, then `npv` will be calculated for the current expiration + iv + underlying.

Here's exact figures using [derivatives](https://web.archive.org/web/20200110122246/http://docs.fincad.com/support/developerfunc/mathref/greeks.htm) to get the `iv` and all first order greeks for a current price:
```haskell
>>> pygreeks.optionGreeksAuto(pygreeks.Option(kind='call', underlying=48, strike=49, expiry=(2/365), npv=0.55))
Option(kind='call', underlying=48, strike=49, expiry=0.005479452054794521, iv=0.6766163408740353, npv=0.5499992370605469, greeks=Greeks(theta=-0.22239099442958832, delta=0.34953978657722473, gamma=0.1539958268404007, vega=0.013154408894479275))
```

Here's approximate figures using [two step numerical approximation](https://github.com/vollib/lets_be_rational):
```haskell
>>> pygreeks.optionGreeksFast(pygreeks.Option(kind='call', underlying=48, strike=49, expiry=(2/365), npv=0.55))
Option(kind='call', underlying=48, strike=49, expiry=0.005479452054794521, iv=0.6766160239953531, npv=0.5499992370605469, greeks=Greeks(theta=-0.22254317168663496, delta=0.3495396503168968, gamma=0.15399597226320086, vega=0.01315440614997891))
```

The approximate (`Fast`) version runs about 40x faster than the pytorch version for IV calculations.

## Usage

```python
import pygreeks
```

Define an option using `pygreeks.Option()` with parameters described in the examples above, then run one or more of:

- `pygreeks.optionGreeksAuto(option)` for autograd greeks and IV
- `pygreeks.optionGreeksFast(option)` for numerical approximation greeks and IV (but may fall back to autograd IV if the approximation IV fails to converge)


## License
`pytorch` implementation adapted from https://github.com/mgroncki/IPythonScripts/blob/master/PricingPyTorch/PlainVanillaAndBarriersCPU.ipynb (BSD)

numeric approximation is via [py_vollib](https://github.com/vollib/py_vollib) (MIT)

Any other features or improvements made available under Apache-2.0
