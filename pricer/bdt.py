"""Bons du Tresor marocains : conventions de la circulaire 02/04 (port fidele du classeur).

Taux et taux faciaux en decimal (0.025 = 2,50 %). Prix en pour cent du nominal.
"""
from __future__ import annotations
from dataclasses import dataclass
import datetime as dt
import calendar


def date_excel(an: int, mois: int, jour: int) -> dt.date:
    """Equivalent de DATE() d'Excel : un jour au-dela de la fin du mois deborde sur le mois suivant."""
    return dt.date(an, mois, 1) + dt.timedelta(days=jour - 1)


def base_annuelle(d: dt.date) -> int:
    return 366 if calendar.isleap(d.year) else 365


@dataclass
class Titre:
    code: str
    libelle: str
    nominal: float          # valeur nominale unitaire (MAD)
    taux_facial: float      # decimal
    jouissance: dt.date
    echeance: dt.date
    spread_bps: float = 0.0
    isin: str = ""


@dataclass
class Caracteristiques:
    duree_initiale: int     # F6 : echeance - jouissance (jours)
    residuel: int           # F7 : echeance - date (jours)
    base: int               # A
    premier_coupon: dt.date  # F10
    prochain_coupon: dt.date  # F9
    n: int                  # coupons restants
    correction: float       # Z : correction du premier coupon (en % du nominal)
    regime: str


def caracteristiques(t: Titre, d: dt.date) -> Caracteristiques:
    E, J = t.echeance, t.jouissance
    F6 = (E - J).days
    F7 = (E - d).days
    A = base_annuelle(d)
    # premier coupon : anniversaire de l echeance suivant la jouissance, reporte d un an si la periode fait moins de 360 j
    anniv_j = date_excel(J.year + (0 if date_excel(J.year, E.month, E.day) > J else 1), E.month, E.day)
    F10 = date_excel(anniv_j.year + 1, E.month, E.day) if (anniv_j - J).days < 360 else anniv_j
    anniv_d = date_excel(d.year + (0 if date_excel(d.year, E.month, E.day) > d else 1), E.month, E.day)
    F9 = max(anniv_d, F10)
    n = E.year - F9.year + 1
    ecart = (F10 - J).days / A - 1
    Z = t.taux_facial * 100 * ecart if (d < F10 and abs(ecart) > 0.02) else 0.0
    regime = "TCN court - formule (1)" if F6 <= 366 else ("Residuel court - formules (2)/(3)" if F7 <= 365 else "Actuariel - formule (4)")
    return Caracteristiques(F6, F7, A, F10, F9, n, Z, regime)


def prix_plein(t: Titre, d: dt.date, r: float, car: Caracteristiques | None = None) -> float:
    """Prix plein (coupon couru inclus), en % du nominal, au taux d actualisation r (decimal, spread inclus)."""
    c = car or caracteristiques(t, d)
    cp = t.taux_facial
    if c.duree_initiale <= 366:
        return 100 * (1 + cp * c.duree_initiale / 360) / (1 + r * c.residuel / 360)
    if c.residuel <= 365:
        return (100 * (1 + cp) + c.correction) / (1 + r * c.residuel / 360)
    f = (c.prochain_coupon - d).days / c.base
    if r == 0:
        corps = cp * 100 * c.n + 100 + c.correction
    else:
        corps = (cp * 100 * (1 - (1 + r) ** (-c.n)) / r) * (1 + r) + 100 * (1 + r) ** (-(c.n - 1)) + c.correction
    return corps * (1 + r) ** (-f)


def coupon_couru(t: Titre, d: dt.date, car: Caracteristiques | None = None) -> float:
    """Coupon couru en % du nominal."""
    c = car or caracteristiques(t, d)
    cp = t.taux_facial
    if c.duree_initiale <= 366:
        return cp * 100 * (c.duree_initiale - c.residuel) / 360
    if d < c.premier_coupon:
        return cp * 100 * (d - t.jouissance).days / c.base
    return cp * 100 * max(0.0, 1 - (c.prochain_coupon - d).days / c.base)


def taux_depuis_prix(t: Titre, d: dt.date, prix: float, plein: bool = True) -> float:
    """Taux de rendement (decimal) qui redonne le prix saisi ; dichotomie comme dans le classeur."""
    c = caracteristiques(t, d)
    P = prix if plein else prix + coupon_couru(t, d, c)
    if c.duree_initiale <= 366:
        return (100 * (1 + t.taux_facial * c.duree_initiale / 360) / P - 1) * 360 / c.residuel
    lo, hi = -0.05, 0.50
    for _ in range(100):
        mid = (lo + hi) / 2
        if prix_plein(t, d, mid, c) > P:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


@dataclass
class Valorisation:
    taux: float
    prix_plein: float
    coupon_couru: float
    prix_pied: float
    sensi: float
    duration: float
    convexite: float
    regime: str
    maturite_ans: float


def valoriser(t: Titre, d: dt.date, r: float) -> Valorisation:
    c = caracteristiques(t, d)
    P = prix_plein(t, d, r, c)
    Pm = prix_plein(t, d, r - 0.0001, c)
    Pp = prix_plein(t, d, r + 0.0001, c)
    sensi = -(Pp - Pm) / (2 * 0.0001 * P) if P else 0.0
    conv = (Pm + Pp - 2 * P) / (P * 1e-8) if P else 0.0
    cc = coupon_couru(t, d, c)
    return Valorisation(r, P, cc, P - cc, sensi, sensi * (1 + r), conv, c.regime, (t.echeance - d).days / 365)
