import torch
from dataclasses import dataclass

# for IV calculation via root finding/gradient methods
from scipy import optimize

# these two imports are only to fix errors with py_vollib warning and
# too verbose garbage debug printing hard coded into the library
# TODO: fork py_vollib and fix everything to act nicer.
import numpy as np
import sys

# From https://github.com/vollib/py_vollib
# Uses numerical approximations to evalute the derivatives
# in basically two time steps.
# These are about 3.8x faster than using autograd from pytorch.
# Also, this is the only reasonable IV math we could find,
# so even when running the pytorch model, we still use
# option IV calculation from py_vollib.
import py_vollib.black_scholes.greeks.analytical as bs_ga
import py_vollib.black_scholes.implied_volatility as bs_iv

# Risk free interest rate. We don't expect many changes in our
# current environment. We could pull this from an API in the
# future if it ends up being more changey than we think.
# This is also a parameter to all functions, but this is
# a sane default if you don't want to scrape the fed funds
# rate website on each request.
# The higher the BASE_RATE (risk free return on capital), the larger
# the greeks will be (meaning: faster decays, etc) since there's
# more of a loaded holding cost tradeoff if you could just throw all your assets
# into a risk-free-return bucket instead of holding decaying risk contracts.

# For US calculations:
# https://www.newyorkfed.org/markets/reference-rates/effr
# Currently: target rate between 0.06% and 0.07%, so 0.0006 to 0.0007
BASE_RATE = 0.0007

# Tell numpy to be quiet when py_vollib does bad math
np.seterr(all="ignore")


def unwrap(t):
    """ Extract value from a pytorch tensor. """
    if isinstance(t, torch.Tensor):
        return t.item()

    return t


@dataclass
class Greeks:
    theta: float
    delta: float
    gamma: float  # TODO: put the second order greeks in a different dataclass?
    vega: float

    def __post_init__(self):
        self.theta = unwrap(self.theta)
        self.delta = unwrap(self.delta)
        self.gamma = unwrap(self.gamma)
        self.vega = unwrap(self.vega)


@dataclass
class Option:
    # "call" or "put", all lowercase
    kind: str

    # current stock price
    underlying: float

    # option strike price
    strike: float

    # option expiration expressed in fractions of a year
    # (e.g. 2 days to expiration is 2/365.25)
    expiry: float

    # iv of this option based on npv
    # (generated by model or provided by user if user doesn't have
    #  a current trade price to calculate the IV internally)
    iv: float = None

    # black-scholes calculated value of the option
    # - OR -
    # current NPV of the option if you are calculating the IV
    npv: float = None

    # first and second order derivatives of npv
    # (generated by model when requested)
    greeks: Greeks = None


# Implementation adapted from:
# https://github.com/mgroncki/IPythonScripts/blob/master/PricingPyTorch/PlainVanillaAndBarriersCPU.ipynb
# License BSD 3-Clause License

# Basic formula ref at https://www.macroption.com/black-scholes-formula/
def blackScholes_pyTorch(kind, S_0, strike, time_to_expiry, implied_vol, riskfree_rate):
    assert isinstance(kind, str), f"Why did you give me {kind}?"
    assert isinstance(S_0, torch.Tensor), f"Why did you give me {S_0}!"

    S = S_0
    K = strike
    dt = time_to_expiry
    sigma = implied_vol
    r = riskfree_rate
    Phi = torch.distributions.Normal(0, 1).cdf
    d_1 = (torch.log(S_0 / K) + (r + sigma ** 2 / 2) * dt) / (sigma * torch.sqrt(dt))
    d_2 = d_1 - sigma * torch.sqrt(dt)

    if kind[0].lower() == "c":  # kind can be just "c" or "call":
        return S * Phi(d_1) - K * torch.exp(-r * dt) * Phi(d_2)

    # else, is put
    return K * torch.exp(-r * dt) * Phi(-d_2) - S * Phi(-d_1)


def optionNPV(kind, s0, k, t, sigma, r=BASE_RATE):
    """Calculate theoretical value of option.

    s0: underlying price
    k: strike price
    t: time to expiry (in fractional years)
    sigma: implied volatility percentage (e.g. 30% = 0.30)
    r: risk free return rate
    """

    S_0 = torch.tensor([float(s0)], requires_grad=True)
    K = torch.tensor([float(k)], requires_grad=False)  # don't care
    T = torch.tensor([float(t)], requires_grad=True)
    Sigma = torch.tensor([float(sigma)], requires_grad=True)
    R = torch.tensor([float(r)], requires_grad=False)  # don't care

    return blackScholes_pyTorch(kind, S_0, K, T, Sigma, R)


# More algo docs:
# https://docs.fincad.com/support/developerfunc/mathref/greeks.htm
# Note:
#  - theta is yearly, so we divide by 365.25
#  - vega is a percentage, so we divide by 100
#  - rho is a percentage, so we divide by 100 (if we care about _rho_ at all)

# If you want an accurate 'r', visit:
# http://www.treasury.gov/resource-center/data-chart-center/interest-rates/Pages/TextView.aspx?data=yield

# 'r' should be adjusted to be the interest rate at the expiration of the option, but these
# days interest rates are between 1.5% and -1.5% around the world.
# But, this doesn't count for other interest like people buying options with
# secured margin loans where they'll have 3% to 9% underlying costs.
def deriveGreeks1(kind, s0, k, t, sigma, r=BASE_RATE):
    """Calculate first-order greeks given parameters.

    s0: underlying price
    k: strike price
    t: time to expiry (in fractional years)
    sigma: implied volatility percentage (e.g. 30% = 0.30)
    r: risk free return rate
    """

    S_0 = torch.tensor([float(s0)], requires_grad=True)
    K = torch.tensor([float(k)], requires_grad=False)  # don't care
    T = torch.tensor([float(t)], requires_grad=True)
    Sigma = torch.tensor([float(sigma)], requires_grad=True)
    R = torch.tensor([float(r)], requires_grad=False)  # don't care

    npv = blackScholes_pyTorch(kind, S_0, K, T, Sigma, R)
    npv.backward()  # retain_graph=True)

    # dNPV / dT (change in time remaining, based on percentage of year)
    theta = -T.grad / 365.25

    # dNPV / dS_0 (change in underlying price)
    delta = S_0.grad

    # dNPV / dSigma (change in underlying iv)
    vega = Sigma.grad / 100

    # dNPV / dR (change in risk-free interest rate)
    # rho = R.grad / 100

    # Not relevant unless options have adjustable strike prices:
    # http://sfb649.wiwi.hu-berlin.de/fedc_homepage/xplore/tutorials/xlghtmlnode64.html#MDBOOK:200
    # digital = -K.grad  # ?

    return npv, theta, delta, vega


def deriveGreeks2(kind, s0, k, t, sigma, r=BASE_RATE, which=[0]):
    """Calculate second derivatives of npv with respect to each
    parameter.

    By default, we only return gamma (which=[0]).

    If you want more second order greeks,
    just supply 'which' with more index positions."""

    # yay second derivatives!

    # Note: this looks bad because it seems we're duplicating half our work
    #       each time, but the tensor variables get updated on each
    #       autograd run, so we can't reuse them across attempts.
    #       We could potentially vectorize it and run them all at once?
    #       Need to figure out more pytorch magic with tensors and gradients.
    def runForIdx(i):
        # Perf hack: we only need to retain the gradient on the variable
        # we will be differentiating with respect to.
        calculateAll = [
            torch.tensor([float(s0)], requires_grad=i == 0),  # gamma (d^2NPV / dS0^2)
            torch.tensor([float(k)], requires_grad=i == 1),
            torch.tensor([float(t)], requires_grad=i == 2),
            torch.tensor([float(sigma)], requires_grad=i == 3),  # vomma (d^2NPV / dσ^2)
            torch.tensor([float(r)], requires_grad=i == 4),
        ]

        npv = blackScholes_pyTorch(kind, *calculateAll)
        (gradient,) = torch.autograd.grad(npv, calculateAll[i], create_graph=True)

        gradient.backward()  # retain_graph=True)
        # npv is now differentiated with respect to value at index 'i'

        # Why we're diff'ing with respect to what:
        # https://en.wikipedia.org/wiki/Greeks_(finance)#Second-order_Greeks

        # gamma and vanna are simple
        if i == 0 or i == 3:
            return calculateAll[i].grad

        # charm (d^2 NPV / dt dS0)
        if i == 1:
            # Value is expressed as delta decay per day
            return calculateAll[2].grad / 365.25

        # veta (d^2 NPV / dt dSigma)
        if i == 2:
            # Value is expressed as percentage change per day
            return calculateAll[3].grad / (100 * 365.25)

        # vera (d^2 NPV / dSigma dr)
        if i == 4:
            return calculateAll[3].grad

    return [runForIdx(i) for i in which]


def ivFromOptionAuto(option, guess: float = 0):
    def findIV(iv):
        """ Function to find a zero root for (parameterized by 'iv')"""
        npv = optionNPV(
            option.kind,
            option.underlying,
            option.strike,
            option.expiry,
            iv,
        ).item()

        return npv - option.npv

    # if given an approximate IV, search near it:
    if guess:
        # Fastest of the optimization approaches: ~3 ms
        # 3x to 4x faster than the brentq search if we
        # already have a known-good HV going into this.
        # Warning though: throws a hard failure if the initial
        # guess is too far off from the optimal result.
        option.iv = optimize.newton(findIV, guess)
    else:
        # else, use a wide search
        # ~10 ms, but doesn't need an input estimate.
        # yeah, this looks weird having a negative bracket,
        # but for deep ITM options, it needs the wider search
        # space for the excessive IV calculations.
        # Note: the 'width' of the ± range doesn't matter very
        #       much since it's a quick binary search down to
        #       the best zero-point anyway.
        try:
            option.iv = optimize.brentq(findIV, 0, 5000)
        except:
            # Sorry, couldn't figure it out, but we don't
            # want to throw an exception.
            option.iv = 0

    return option.iv


def ivFromOptionFast(option):
    try:
        # ~90 us (11x faster than ivFromOptionAuto doh!)
        option.iv = bs_iv.implied_volatility(
            option.npv,
            option.underlying,
            option.strike,
            option.expiry,
            BASE_RATE,
            option.kind[0].lower(),
        )
    except:
        # this can throw
        # "BelowIntrinsicException:
        #  ('The volatility is below the intrinsic value.',)"
        # but do we care? We'll just give it an error value.

        # The bs_iv library is very sensitive to edge conditions
        # and it doesn't seem to like deep ITM options, so we
        # just give them all default values here. It's not accurate,
        # but good enough.
        # It is still reasonably accurate for near-ITM options.
        # option.iv = 0.10

        # Actually, if the quick method fails, fall back to the Auto method!
        option.iv = ivFromOptionAuto(option)

    return option.iv


def optionGreeksAuto(option, calculateNPV=True):
    """Calculate exact greeks using derivatives.

    Populates 'option' with greeks and npv of option"""

    if not option.iv:
        assert (
            option.npv
        ), "If you don't provide 'iv' you need to provide current 'npv' to calculate 'iv'"

        ivFromOptionAuto(option)

    npv, theta, delta, vega = deriveGreeks1(
        option.kind,
        option.underlying,
        option.strike,
        option.expiry,
        option.iv,
    )

    (gamma,) = deriveGreeks2(
        option.kind,
        option.underlying,
        option.strike,
        option.expiry,
        option.iv,
    )

    greeks = Greeks(theta, delta, gamma, vega)

    if calculateNPV:
        # due to the pytorch usage we always calculate it anyway,
        # but we don't set it unless requested.
        option.npv = npv.item()

    option.greeks = greeks

    return option


def optionGreeksFast(option, calculateNPV=True):
    """Calculate approximate (but accurate) greeks using trickery.

    Note: other than 'npv' calculation, this uses py_vollib to caluclate
          greeks using fancy math workarounds. It's an estimation,
          but an accurate estimation."""

    if not option.iv:
        assert (
            option.npv
        ), "If you don't provide 'iv' you need to provide current 'npv' to calculate 'iv'"

        ivFromOptionFast(option)

    # We still calculate the NPV using pytorch
    if calculateNPV:
        try:
            npv = optionNPV(
                option.kind,
                option.underlying,
                option.strike,
                option.expiry,
                option.iv,
            )
            option.npv = npv.item()
        except:
            # Probably the torch error "ValueError: The value argument must be within the support"
            # because ???
            npv = None

    flag = option.kind[0].lower()

    assert (
        flag == "c" or flag == "p"
    ), f"Why did you give me {flag} instead of 'c' or 'p'?"

    # Greeks are calculated using numerical trickery
    # without actually evaluating derivatives.

    # ugh, this is annoying but there's a debug print in the pyvol upstream, so we
    # disable stdout for these so they don't print ugly things.
    origout = sys.stdout
    sys.stdout = None
    theta = bs_ga.theta(
        flag,
        option.underlying,
        option.strike,
        option.expiry,
        BASE_RATE,
        option.iv,
    )
    delta = bs_ga.delta(
        flag,
        option.underlying,
        option.strike,
        option.expiry,
        BASE_RATE,
        option.iv,
    )
    vega = bs_ga.vega(
        flag,
        option.underlying,
        option.strike,
        option.expiry,
        BASE_RATE,
        option.iv,
    )
    gamma = bs_ga.gamma(
        flag,
        option.underlying,
        option.strike,
        option.expiry,
        BASE_RATE,
        option.iv,
    )

    sys.stdout = origout

    greeks = Greeks(theta, delta, gamma, vega)
    option.greeks = greeks

    return option
