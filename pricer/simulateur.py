"""Simulateur de portefeuille : operations « et si », courbe a la main, horizon, sensibilites par tenor,
scenarios en reevaluation complete, VaR historique, suggestion de couverture."""
from __future__ import annotations
import datetime as dt
from .courbe import Courbe, Ligne, TENORS
from .portefeuille import valoriser_portefeuille, agregats, limites, tranches
from .bdt import valoriser, caracteristiques, date_excel

JOURS = [j for _, j, _ in TENORS]
SCENARIOS = [("Parallele +100", [100] * 9), ("Parallele +50", [50] * 9), ("Parallele +25", [25] * 9), ("Parallele -25", [-25] * 9), ("Parallele -50", [-50] * 9), ("Parallele -100", [-100] * 9),
             ("Pentification 2-10 +50", [0, 0, 0, 0, 25, 50, 50, 50, 50]), ("Aplatissement 2-10 -50", [0, 0, 0, 0, -25, -50, -50, -50, -50]),
             ("Court +50", [50, 50, 50, 25, 10, 0, 0, 0, 0]), ("Court -50", [-50, -50, -50, -25, -10, 0, 0, 0, 0]),
             ("Papillon ventre +25", [0, 0, 0, 0, 25, 0, 0, 0, 0]), ("Papillon ventre -25", [0, 0, 0, 0, -25, 0, 0, 0, 0]),
             ("Twist 5 ans", [-25, -25, -25, -15, 0, 15, 25, 25, 25]), ("Long +30", [0, 0, 0, 0, 0, 0, 30, 30, 30])]


def _choc_a(residuel_jours: int, chocs_bp: list) -> float:
    """Choc interpole (en decimal) au residuel, entre tenors ; plat aux extremites."""
    if residuel_jours <= JOURS[0]:
        return chocs_bp[0] / 1e4
    if residuel_jours >= JOURS[-1]:
        return chocs_bp[-1] / 1e4
    for k in range(8):
        if JOURS[k] <= residuel_jours <= JOURS[k + 1]:
            return (chocs_bp[k] + (chocs_bp[k + 1] - chocs_bp[k]) * (residuel_jours - JOURS[k]) / (JOURS[k + 1] - JOURS[k])) / 1e4
    return 0.0


def deformer(courbe: Courbe, chocs_bp: list, d: dt.date | None = None) -> Courbe:
    """Nouvelle courbe : tenors decales des chocs, lignes publiees decalees du choc interpole a leur residuel."""
    d = d or courbe.date
    taux = [t + c / 1e4 for t, c in zip(courbe.taux, chocs_bp)]
    lignes = [Ligne(l.echeance, l.taux + _choc_a((l.echeance - d).days, chocs_bp), l.code, l.libelle) for l in courbe.lignes]
    return Courbe(courbe.date, taux, lignes, courbe.source + " + chocs")


def appliquer_operations(positions: dict, operations: list, ref: dict) -> dict:
    """positions : code -> [quantite, spread]. operations : dict(sens, code, nominal)."""
    pos = {k: [v[0], v[1]] for k, v in positions.items()}
    for o in operations:
        t = ref.get(str(o.get("code", "")).strip())
        if not t or not o.get("nominal"):
            continue
        q = float(o["nominal"]) / t.nominal * (1 if str(o.get("sens", "Achat")).startswith("A") else -1)
        cur = pos.get(t.code, [0.0, ""]); cur[0] += q
        if abs(cur[0]) < 1e-9: pos.pop(t.code, None)
        else: pos[t.code] = cur
    return pos


def evaluer(positions: dict, ref: dict, courbe: Courbe, d: dt.date, methode: str, grille: dict) -> dict:
    lg = valoriser_portefeuille([(k, v[0], v[1]) for k, v in positions.items()], ref, courbe, d, methode)
    return dict(lignes=lg, agregats=agregats(lg), limites=limites(lg, grille), tranches=tranches(lg))


def krd(positions: dict, ref: dict, courbe: Courbe, d: dt.date) -> list:
    """Sensibilite par tenor (MAD par pb) : chaque noeud est releve de 1 pb, reevaluation complete par interpolation sur les tenors."""
    base = valoriser_portefeuille([(k, v[0], v[1]) for k, v in positions.items()], ref, courbe, d, "tenors")
    v0 = sum(l.valeur_marche for l in base)
    out = []
    for k in range(9):
        ch = [0] * 9; ch[k] = 1
        lg = valoriser_portefeuille([(k2, v[0], v[1]) for k2, v in positions.items()], ref, deformer(courbe, ch, d), d, "tenors")
        out.append(dict(tenor=TENORS[k][0], pvbp=-(sum(l.valeur_marche for l in lg) - v0)))
    return out


def scenarios(positions: dict, ref: dict, courbe: Courbe, d: dt.date, methode: str, liste=None) -> list:
    base = sum(l.valeur_marche for l in valoriser_portefeuille([(k, v[0], v[1]) for k, v in positions.items()], ref, courbe, d, methode))
    out = []
    for nom, ch in (liste or SCENARIOS):
        v = sum(l.valeur_marche for l in valoriser_portefeuille([(k, v2[0], v2[1]) for k, v2 in positions.items()], ref, deformer(courbe, ch, d), d, methode))
        out.append(dict(scenario=nom, chocs=ch, pnl=v - base))
    return out


def var_historique(positions: dict, ref: dict, courbe: Courbe, d: dt.date, courbes_hist: dict, methode: str) -> dict:
    """Chaque variation observee entre deux courbes consecutives est appliquee a la courbe du jour ; distribution des P&L."""
    dates = sorted(courbes_hist)
    if len(dates) < 2:
        return dict(ok=False, message="historique trop court")
    base = sum(l.valeur_marche for l in valoriser_portefeuille([(k, v[0], v[1]) for k, v in positions.items()], ref, courbe, d, methode))
    pnls = []
    for a, b in zip(dates[:-1], dates[1:]):
        ta, tb = courbes_hist[a][0], courbes_hist[b][0]
        ch = [(y - x) * 1e4 for x, y in zip(ta, tb)]
        v = sum(l.valeur_marche for l in valoriser_portefeuille([(k, v2[0], v2[1]) for k, v2 in positions.items()], ref, deformer(courbe, ch, d), d, methode))
        pnls.append(dict(de=a, a=b, pnl=v - base, jours=(b - a).days))
    tri = sorted(p["pnl"] for p in pnls)
    q = lambda p: tri[max(0, min(len(tri) - 1, int(round((1 - p) * (len(tri) - 1)))))]
    return dict(ok=True, n=len(pnls), pire=tri[0], meilleur=tri[-1], var95=q(0.95), var99=q(0.99), moyenne=sum(tri) / len(tri), detail=pnls)


def pnl_horizon(positions: dict, ref: dict, courbe_now: Courbe, courbe_h: Courbe, d: dt.date, dh: dt.date, methode: str, taux_fin: float) -> dict:
    """P&L attendu a l horizon : valeur a dh sur la courbe d horizon (roll-down inclus) + coupons encaisses - financement."""
    l0 = valoriser_portefeuille([(k, v[0], v[1]) for k, v in positions.items()], ref, courbe_now, d, methode)
    v0 = sum(l.valeur_marche for l in l0); c0 = sum(l.coupon_couru for l in l0)
    lh = valoriser_portefeuille([(k, v[0], v[1]) for k, v in positions.items()], ref, courbe_h, dh, methode)
    vh = sum(l.valeur_marche for l in lh); chh = sum(l.coupon_couru for l in lh)
    flux = 0.0
    for k, v in positions.items():
        t = ref.get(k)
        if not t: continue
        car = caracteristiques(t, d); an = car.premier_coupon.year
        if car.duree_initiale <= 366:
            if d < t.echeance <= dh: flux += v[0] * t.nominal * (1 + t.taux_facial * car.duree_initiale / 360)
            continue
        while True:
            dc = date_excel(an, t.echeance.month, t.echeance.day)
            if dc > t.echeance: break
            if d < dc <= dh:
                flux += v[0] * t.nominal * (t.taux_facial * ((car.premier_coupon - t.jouissance).days / car.base if dc == car.premier_coupon else 1) + (1 if dc == t.echeance else 0))
            an += 1
    fin = -v0 * taux_fin * (dh - d).days / 360
    carry = (chh - c0) + flux
    l_same = valoriser_portefeuille([(k, v[0], v[1]) for k, v in positions.items()], ref, courbe_now, dh, methode)
    roll = sum(l.valeur_marche for l in l_same) - v0 - carry
    total = (vh - v0) + flux + fin
    return dict(valeur_0=v0, valeur_h=vh, carry=carry, roll=roll, courbe=total - carry - roll - fin, financement=fin, total=total, jours=(dh - d).days)


def couverture(positions: dict, ref: dict, courbe: Courbe, d: dt.date, cible_tenor: int, candidats: list) -> list:
    """Nominal de chaque ligne candidate qui annule la sensibilite du tenor cible (signe : + acheter, - vendre)."""
    k = krd(positions, ref, courbe, d)[cible_tenor]["pvbp"]
    out = []
    for code in candidats:
        t = ref.get(code)
        if not t or t.echeance <= d: continue
        unit = {code: [1.0, ""]}
        s = krd(unit, ref, courbe, d)[cible_tenor]["pvbp"]      # pvbp d un titre
        if abs(s) < 1e-9: continue
        q = -k / s
        out.append(dict(code=code, libelle=t.libelle, nominal=q * t.nominal, sens="Achat" if q > 0 else "Vente", pvbp_titre=s))
    return sorted(out, key=lambda x: abs(x["nominal"]))
