"""Valorisation d un portefeuille sur la courbe retenue, agregats, limites, tranches."""
from __future__ import annotations
from dataclasses import dataclass
import datetime as dt
from .bdt import Titre, caracteristiques, prix_plein, coupon_couru, valoriser

LIMITES_DEFAUT = {
    "nominal": [("Nominal global", 0, 6_000_000_000), ("Nominal >= 1 an", 1, 5_700_000_000), ("Nominal >= 5 ans", 5, 3_200_000_000),
                ("Nominal >= 10 ans", 10, 500_000_000), ("Nominal >= 15 ans", 15, 300_000_000)],
    "sensi": [("Sensi globale", 0, 2_500_000), ("Sensi >= 1 an", 1, 2_300_000), ("Sensi >= 3 ans", 3, 2_200_000),
              ("Sensi >= 5 ans", 5, 1_600_000), ("Sensi >= 10 ans", 10, 582_000)],
}
TRANCHES = [("0 - 2 ans", 0, 2), ("2 - 5 ans", 2, 5), ("5 - 10 ans", 5, 10), ("10 - 15 ans", 10, 15), ("15 ans et +", 15, 99)]


@dataclass
class LignePtf:
    code: str
    libelle: str
    quantite: float
    nominal: float
    taux_facial: float
    echeance: dt.date
    maturite: float
    taux_courbe: float
    taux_actu: float
    prix_plein: float
    valeur_marche: float
    coupon_couru: float
    sensi: float
    duration: float
    pvbp: float
    sensi_nominale: float
    convexite: float
    regime: str
    note: str


def valoriser_portefeuille(positions: list, ref: dict, courbe, d: dt.date, methode: str = "lignes") -> list:
    """positions : liste de (code, quantite, spread_bps ou None)."""
    out = []
    for code, qte, spread in positions:
        code = str(code).strip()
        t = ref.get(code)
        if t is None or not qte:
            continue
        taux_courbe, note = courbe.taux_pour(t.echeance, d, methode)
        r = taux_courbe                                   # BDT : pas de spread
        v = valoriser(t, d, r)
        nominal = float(qte) * t.nominal
        vm = nominal * v.prix_plein / 100
        out.append(LignePtf(code, t.libelle, float(qte), nominal, t.taux_facial, t.echeance, (t.echeance - d).days / 365,
                            taux_courbe, r, v.prix_plein, vm, nominal * v.coupon_couru / 100, v.sensi, v.duration,
                            v.sensi * vm * 0.0001, nominal * v.sensi / 10000, v.convexite, v.regime, note))
    return out


def agregats(lignes: list) -> dict:
    vm = sum(l.valeur_marche for l in lignes)
    if vm <= 0:
        return dict(valeur_marche=0, nominal=0, coupon_couru=0, sensi=0, duration=0, pvbp=0, convexite=0, sensi_nominale=0, nb=0, poids_max=0)
    return dict(valeur_marche=vm, nominal=sum(l.nominal for l in lignes), coupon_couru=sum(l.coupon_couru for l in lignes),
                sensi=sum(l.sensi * l.valeur_marche for l in lignes) / vm, duration=sum(l.duration * l.valeur_marche for l in lignes) / vm,
                pvbp=sum(l.pvbp for l in lignes), convexite=sum(l.convexite * l.valeur_marche for l in lignes) / vm,
                sensi_nominale=sum(l.sensi_nominale for l in lignes), nb=len(lignes), poids_max=max(l.valeur_marche for l in lignes) / vm)


def limites(lignes: list, grille: dict | None = None) -> list:
    g = grille or LIMITES_DEFAUT
    out = []
    for nom, seuil, lim in g["nominal"]:
        c = sum(l.nominal for l in lignes if l.maturite >= seuil)
        out.append(dict(palier=nom, type="nominal", consommation=c, limite=lim, utilisation=c / lim if lim else 0, restant=lim - c,
                        statut="DEPASSEMENT" if c > lim else ("Vigilance" if lim and c / lim > 0.9 else "OK")))
    for nom, seuil, lim in g["sensi"]:
        c = sum(l.sensi_nominale for l in lignes if l.maturite >= seuil)
        out.append(dict(palier=nom, type="sensi", consommation=c, limite=lim, utilisation=c / lim if lim else 0, restant=lim - c,
                        statut="DEPASSEMENT" if c > lim else ("Vigilance" if lim and c / lim > 0.9 else "OK")))
    return out


def tranches(lignes: list) -> list:
    vm = sum(l.valeur_marche for l in lignes) or 1
    out = []
    for nom, a, b in TRANCHES:
        sel = [l for l in lignes if a <= l.maturite < b]
        v = sum(l.valeur_marche for l in sel)
        out.append(dict(tranche=nom, valeur=v, poids=v / vm, sensi_nominale=sum(l.sensi_nominale for l in sel), nb=len(sel)))
    return out
