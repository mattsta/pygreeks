pygreeks: black-scholes greeks in python
----------------------------------------

pygreeks implements black-scholes in python using either exact derivatives from `pytorch` autograd or
a two step numerical approximation.


Here's the exact figures using [derivatives](https://docs.fincad.com/support/developerfunc/mathref/greeks.htm):
```haskell
>>> pygreeks.optionGreeksAuto(pygreeks.Option("put", underlying=70.00, underlying_iv=0.90, strike=30.00, expiry=(820 / 365)))
Option(kind='put', underlying=70.0, underlying_iv=0.9, strike=30.0, expiry=2.2465753424657535, iv=0.8999999950626361, npv=8.27951431274414, greeks=Greeks(theta=-0.008868245407938957, delta=-0.09199449419975281, gamma=0.001747919013723731, vega=0.17317327857017517))
```

Here's approximate figures using [two step numerical approximation](https://github.com/vollib/lets_be_rational) (notice it's basically the same, but it still uses autograd for npv):
```haskell
>>> pygreeks.optionGreeksFast(pygreeks.Option("put", underlying=70.00, underlying_iv=0.90, strike=30.00, expiry=(820 / 365)))
Option(kind='put', underlying=70.0, underlying_iv=0.9, strike=30.0, expiry=2.2465753424657535, iv=0.8999999950626361, npv=8.27951431274414, greeks=Greeks(theta=-0.00887432080828571, delta=-0.09199451682418325, gamma=0.0017479191393343068, vega=0.17317329292221154))
```

The approximate version runs about 3.5x faster than the pytorch version too.

## Usage

```python
import pygreeks
```

Define an option using `pygreeks.Option()` with parameters described in the examples above, then run one or more of:

- `pygreeks.optionGreeksAuto(option)` for autograd greeks
- `pygreeks.optionGreeksFast(option)` for numerical approximation greeks


## License
`pytorch` implementation adapted from https://github.com/mgroncki/IPythonScripts/blob/master/PricingPyTorch/PlainVanillaAndBarriersCPU.ipynb (BSD)

numeric approximation is via [py_vollib](https://github.com/vollib/py_vollib) (MIT)

Any other features or improvements made available under Apache-2.0
