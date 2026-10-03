"""P&L jour par jour entre deux dates : mark-to-market, carry, financement, operations."""
from __future__ import annotations
import datetime as dt
from .bdt import caracteristiques, valoriser, date_excel
from .portefeuille import valoriser_portefeuille


def _flux_titre(t, p: dt.date, d: dt.date) -> float:
    """Coupons et remboursement encaisses par titre (par unite de nominal 1) entre p exclu et d inclus."""
    flux = 0.0
    c = caracteristiques(t, p)
    if c.duree_initiale <= 366:
        if p < t.echeance <= d:
            flux += 1 + t.taux_facial * c.duree_initiale / 360
        return flux
    # coupons annuels aux anniversaires de l echeance, a partir du premier coupon (reporte)
    an = c.premier_coupon.year
    while True:
        dc = date_excel(an, t.echeance.month, t.echeance.day)
        if dc > t.echeance:
            break
        if p < dc <= d:
            if dc == c.premier_coupon:
                flux += t.taux_facial * (c.premier_coupon - t.jouissance).days / c.base
            else:
                flux += t.taux_facial
            if dc == t.echeance:
                flux += 1
        an += 1
    return flux


def pnl_journalier(store, ref: dict, d0: dt.date, d1: dt.date, methode: str, taux_fin: float, base: str = "operation") -> list:
    """Une ligne par date de courbe dans ]d0, d1] (d0 incluse comme point de depart). base : 'operation' ou 'valeur'."""
    dates = sorted(x for x in store.courbes() if d0 <= x <= d1)
    if len(dates) < 2:
        return []
    out = []
    for p, d in zip(dates[:-1], dates[1:]):
        cp, cd = store.courbe(p), store.courbe(d)
        pos_p, _ = store.positions_a(p, ref, base); pos_d, _ = store.positions_a(d, ref, base)
        lp = valoriser_portefeuille([(k, v[0], v[1]) for k, v in pos_p.items()], ref, cp, p, methode)
        ld = valoriser_portefeuille([(k, v[0], v[1]) for k, v in pos_d.items()], ref, cd, d, methode)
        l_pd = valoriser_portefeuille([(k, v[0], v[1]) for k, v in pos_p.items()], ref, cd, d, methode)   # positions d ouverture sur la courbe de d
        vm_p = sum(l.valeur_marche for l in lp); vm_d = sum(l.valeur_marche for l in ld); vm_pd = sum(l.valeur_marche for l in l_pd)
        couru_p = sum(l.coupon_couru for l in lp); couru_pd = sum(l.coupon_couru for l in l_pd)
        flux = sum(v[0] * ref[k].nominal * _flux_titre(ref[k], p, d) for k, v in pos_p.items() if k in ref)
        cash_ops = 0.0; nb_ops = 0
        for o in store.operations():
            if o.get("parent_id"):
                continue
            try:
                od = dt.date.fromisoformat(o.get("date_valeur") or o["date"]) if base == "valeur" else dt.date.fromisoformat(o["date"])
            except Exception:
                continue
            if p < od <= d and o.get("prix_plein"):
                t = ref.get(str(o["code"]).strip())
                if not t:
                    continue
                nominal = float(o["nominal"]) if o.get("nominal") else float(o["quantite"] or 0) * t.nominal
                montant = nominal * float(o["prix_plein"]) / 100
                cash_ops += -montant if o["sens"].lower().startswith("a") else montant
                nb_ops += 1
        financement = -vm_p * taux_fin * (d - p).days / 360
        carry = (couru_pd - couru_p) + flux - sum(v[0] * ref[k].nominal * 0 for k, v in pos_p.items())
        # titres echus entre p et d : leur valeur disparait, leur remboursement est dans flux ; on neutralise le couru qui disparait
        effet_courbe = (vm_pd - vm_p) + flux - carry
        trading = (vm_d - vm_pd) + cash_ops
        total = (vm_d - vm_p) + cash_ops + flux + financement
        out.append(dict(de=p, a=d, jours=(d - p).days, vm_debut=vm_p, vm_fin=vm_d, carry=carry, effet_courbe=effet_courbe, trading=trading,
                        financement=financement, total=total, flux_encaisses=flux, cash_operations=cash_ops, nb_operations=nb_ops,
                        controle=total - (carry + effet_courbe + trading + financement)))
    return out
